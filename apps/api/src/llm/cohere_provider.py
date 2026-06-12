import httpx

from src.llm.errors import ProviderBadRequest, ProviderUnavailable, RateLimited
from src.llm.types import EmbeddingResult

COHERE_API_URL = "https://api.cohere.com/v2/embed"

_INPUT_TYPES = {"document": "search_document", "query": "search_query"}


class CohereEmbeddingProvider:
    """Cohere v2 embeddings — embed-v4.0 supports a configurable output
    dimension, pinned to the schema's vector size."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int = 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._transport = transport

    async def embed(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> EmbeddingResult:
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            try:
                response = await client.post(
                    COHERE_API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "texts": texts,
                        "input_type": _INPUT_TYPES.get(input_type, "search_document"),
                        "embedding_types": ["float"],
                        "output_dimension": self._dimensions,
                    },
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(str(exc)) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimited(retry_after=float(retry_after) if retry_after else None)
        if response.status_code >= 500:
            raise ProviderUnavailable(f"Cohere API returned {response.status_code}")
        if response.status_code >= 400:
            raise ProviderBadRequest(
                f"Cohere API returned {response.status_code}: {response.text[:500]}"
            )

        payload = response.json()
        return EmbeddingResult(
            embeddings=payload["embeddings"]["float"],  # returned in input order
            model=self._model,
            input_tokens=int(
                (payload.get("meta") or {}).get("billed_units", {}).get("input_tokens", 0)
            ),
        )
