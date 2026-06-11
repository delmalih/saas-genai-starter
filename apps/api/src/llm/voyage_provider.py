import httpx

from src.llm.errors import ProviderBadRequest, ProviderUnavailable, RateLimited
from src.llm.types import EmbeddingResult

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"


class VoyageEmbeddingProvider:
    """Voyage AI embeddings (Claude has no embeddings API)."""

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    async def embed(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> EmbeddingResult:
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    VOYAGE_API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": texts, "input_type": input_type},
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(str(exc)) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimited(retry_after=float(retry_after) if retry_after else None)
        if response.status_code >= 500:
            raise ProviderUnavailable(f"Voyage API returned {response.status_code}")
        if response.status_code >= 400:
            raise ProviderBadRequest(f"Voyage API returned {response.status_code}: {response.text}")

        payload = response.json()
        # Results can arrive out of order — sort by index before assembling.
        ordered = sorted(payload["data"], key=lambda item: item["index"])
        return EmbeddingResult(
            embeddings=[item["embedding"] for item in ordered],
            model=payload["model"],
            input_tokens=payload.get("usage", {}).get("total_tokens", 0),
        )
