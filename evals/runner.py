"""RAG eval harness — runs the REAL pipeline (ingestion, pgvector retrieval,
agent with tools) against the fixture corpus, then scores each answer with an
LLM judge (faithfulness + citation correctness, 0-1).

Run from the repo root with `make evals` (requires ANTHROPIC_API_KEY and
VOYAGE_API_KEY in apps/api/.env, plus the local postgres from docker compose).

Results land in evals/results/<git-sha>.json.
"""

import argparse
import asyncio
import time
import json
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

EVALS_DIR = Path(__file__).resolve().parent

# Imported lazily after sys.path is set by the Makefile (PYTHONPATH=apps/api).
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.db import Base  # noqa: E402
from src.core.storage import LocalDiskStorage  # noqa: E402
from src.core.tenancy import TenantContext  # noqa: E402
from src.domains.chat.agent import AgentToolbox, run_agent  # noqa: E402
from src.domains.documents.ingestion import ingest_document  # noqa: E402
from src.domains.documents.models import Document  # noqa: E402
from src.domains.documents.retrieval import RetrievalService  # noqa: E402
from src.domains.tenants.models import Membership, Organization  # noqa: E402
from src.domains.usage.service import UsageService  # noqa: E402
from src.llm.anthropic_provider import AnthropicProvider  # noqa: E402
from src.llm.provider import EmbeddingProvider  # noqa: E402
from src.llm.resilience import ResilientEmbeddingProvider, RetryPolicy  # noqa: E402
from src.llm.types import Message  # noqa: E402
from src.llm.voyage_provider import VoyageEmbeddingProvider  # noqa: E402

JUDGE_MODEL = "claude-sonnet-4-6"
AGENT_MODEL = "claude-sonnet-4-6"

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "faithfulness": {
            "type": "number",
            "description": "0-1. 1 = answer states the expected facts with nothing fabricated.",
        },
        "citation_correctness": {
            "type": "number",
            "description": "0-1. 1 = citations point at the correct source document.",
        },
        "reasoning": {"type": "string", "description": "One short sentence."},
    },
    "required": ["faithfulness", "citation_correctness", "reasoning"],
    "additionalProperties": False,
}

JUDGE_PROMPT = """You are grading the answer of a RAG system. Be strict and consistent.

<question>{question}</question>
{expectation}
<answer>{answer}</answer>
<citations>{citations}</citations>

Scoring rules:
- faithfulness: 1.0 if the answer conveys the expected facts (wording may differ)
  with no fabricated or contradicting claims; 0.0 if wrong or fabricated; use
  intermediate values for partially correct answers.
- citation_correctness: 1.0 if at least one citation points to the expected source
  document; 0.0 if there are no citations or they point to the wrong document.

Special case — when the expectation says the corpus does NOT contain the answer:
- faithfulness: 1.0 only if the answer clearly says the information is not
  available, without inventing anything.
- citation_correctness: 1.0 if the answer presents no misleading citations as
  support for a fabricated claim (an empty citation list is correct here).
"""


class PacedEmbedder:
    """Client-side throttle: at most one embedding request per interval."""

    def __init__(self, inner: EmbeddingProvider, min_interval: float = 21.0):
        self._inner = inner
        self._min_interval = min_interval
        self._last_call = 0.0

    async def embed(self, texts: list[str], input_type: str = "document") -> Any:
        wait = self._last_call + self._min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await self._inner.embed(texts, input_type)
        finally:
            self._last_call = time.monotonic()


@dataclass
class CaseResult:
    case_id: str
    faithfulness: float
    citation_correctness: float
    reasoning: str
    answer: str

    @property
    def overall(self) -> float:
        return round((self.faithfulness + self.citation_correctness) / 2, 3)


def require_keys() -> tuple[str, str]:
    settings = get_settings()
    if not settings.anthropic_api_key or not settings.voyage_api_key:
        sys.exit(
            "evals require ANTHROPIC_API_KEY and VOYAGE_API_KEY in apps/api/.env "
            "(real ingestion + agent + judge calls)."
        )
    return settings.anthropic_api_key, settings.voyage_api_key


def evals_database_url() -> str:
    # Same server as dev, dedicated database — recreated on every run.
    return get_settings().database_url.rsplit("/", 1)[0] + "/app_evals"


async def setup_database() -> Any:
    admin = create_async_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        exists = await connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'app_evals'")
        )
        if exists.scalar_one_or_none() is None:
            await connection.execute(text("CREATE DATABASE app_evals"))
    await admin.dispose()

    engine = create_async_engine(evals_database_url())
    async with engine.begin() as connection:
        await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    return engine


async def ingest_corpus(
    session_factory: Any,
    storage: LocalDiskStorage,
    embedder: EmbeddingProvider,
    tenant: TenantContext,
    documents: list[str],
) -> None:
    async with session_factory() as db:
        organization = Organization(id=tenant.organization_id, name="Evals")
        organization.memberships = [Membership(user_id="evals", role="owner")]
        db.add(organization)
        await db.commit()

        for relative_path in documents:
            path = EVALS_DIR / relative_path
            document = Document(
                tenant_id=tenant.organization_id,
                name=path.name,
                mime_type="text/markdown",
                size_bytes=path.stat().st_size,
                created_by="evals",
                storage_path=path.name,
            )
            db.add(document)
            await db.flush()
            await storage.save(path.name, path.read_bytes())
            # chat_provider=None: skip metadata extraction, save tokens.
            await ingest_document(db, storage, embedder, tenant, document.id)
            print(f"  ingested {path.name}")


async def answer_case(
    db: Any,
    tenant: TenantContext,
    chat: AnthropicProvider,
    embedder: EmbeddingProvider,
    question: str,
) -> tuple[str, list[dict[str, Any]]]:
    retrieval = RetrievalService(db, tenant, embedder)
    toolbox = AgentToolbox(db, tenant, retrieval)
    usage = UsageService(db, tenant)
    final: dict[str, Any] = {}
    async for event in run_agent(
        chat, usage, toolbox, tenant, [Message(role="user", content=question)], use_rag=True
    ):
        if event["type"] == "final":
            final = event
    return final.get("text", ""), final.get("citations", [])


async def judge_case(
    judge: AnthropicProvider, case: dict[str, Any], answer: str, citations: list[dict[str, Any]]
) -> CaseResult:
    if case.get("expect_no_answer"):
        expectation = (
            "<expectation>The corpus does NOT contain the answer. "
            "A correct response says so.</expectation>"
        )
    else:
        facts = "; ".join(case["expected_facts"])
        expectation = (
            f"<expectation>Expected facts: {facts}. "
            f"Expected source document: {case['source_document']}.</expectation>"
        )
    citations_text = (
        json.dumps([{"document": c["document_name"], "page": c["page"]} for c in citations])
        if citations
        else "none"
    )
    prompt = JUDGE_PROMPT.format(
        question=case["question"],
        expectation=expectation,
        answer=answer or "(empty)",
        citations=citations_text,
    )
    completion = await judge.complete(
        [Message(role="user", content=prompt)], json_schema=JUDGE_SCHEMA, max_tokens=300
    )
    verdict = json.loads(completion.text)
    return CaseResult(
        case_id=case["id"],
        faithfulness=float(verdict["faithfulness"]),
        citation_correctness=float(verdict["citation_correctness"]),
        reasoning=verdict["reasoning"],
        answer=answer,
    )


def git_sha() -> str:
    try:
        return subprocess.check_output(  # noqa: S603, S607 — fixed argv
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--dataset", default=str(EVALS_DIR / "dataset.yaml"))
    args = parser.parse_args()

    anthropic_key, voyage_key = require_keys()
    dataset = yaml.safe_load(Path(args.dataset).read_text())

    chat = AnthropicProvider(anthropic_key, AGENT_MODEL)
    judge = AnthropicProvider(anthropic_key, JUDGE_MODEL)
    # Voyage free tier allows ~3 requests/minute: pace proactively
    # (1 call / 21s) instead of fighting the limiter, retries as backstop.
    embedder: EmbeddingProvider = PacedEmbedder(
        ResilientEmbeddingProvider(
            VoyageEmbeddingProvider(voyage_key, "voyage-3.5"),
            policy=RetryPolicy(max_attempts=6, base_delay=10.0, max_delay=30.0),
        )
    )
    print("note: embedding calls are paced for the Voyage free tier — "
          "a full run takes ~7 minutes.")
    tenant = TenantContext(organization_id=uuid.uuid4(), user_id="evals", role="owner")

    print("Setting up eval database...")
    engine = await setup_database()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalDiskStorage(Path(tmp))
        print("Ingesting fixture corpus...")
        await ingest_corpus(session_factory, storage, embedder, tenant, dataset["documents"])

        results: list[CaseResult] = []
        print(f"Running {len(dataset['cases'])} cases...")
        async with session_factory() as db:
            for case in dataset["cases"]:
                answer, citations = await answer_case(db, tenant, chat, embedder, case["question"])
                result = await judge_case(judge, case, answer, citations)
                results.append(result)
                print(
                    f"  {result.case_id:<24} faith={result.faithfulness:.2f} "
                    f"cite={result.citation_correctness:.2f} overall={result.overall:.2f}"
                )
            await db.commit()
    await engine.dispose()

    mean = round(sum(r.overall for r in results) / len(results), 3)
    mean_faith = round(sum(r.faithfulness for r in results) / len(results), 3)
    mean_cite = round(sum(r.citation_correctness for r in results) / len(results), 3)
    print("-" * 64)
    print(f"faithfulness={mean_faith}  citations={mean_cite}  OVERALL={mean}")

    sha = git_sha()
    results_dir = EVALS_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    output = {
        "git_sha": sha,
        "agent_model": AGENT_MODEL,
        "judge_model": JUDGE_MODEL,
        "overall": mean,
        "faithfulness": mean_faith,
        "citation_correctness": mean_cite,
        "cases": [
            {
                "id": r.case_id,
                "faithfulness": r.faithfulness,
                "citation_correctness": r.citation_correctness,
                "overall": r.overall,
                "reasoning": r.reasoning,
            }
            for r in results
        ],
    }
    out_path = results_dir / f"{sha}.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n")
    print(f"wrote {out_path.relative_to(EVALS_DIR.parent)}")

    if args.min_score and mean < args.min_score:
        sys.exit(f"FAIL: overall {mean} < required {args.min_score}")


if __name__ == "__main__":
    asyncio.run(main())
