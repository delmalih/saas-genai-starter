import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from src.core.config import get_settings


class BlobStorage(Protocol):
    """Document blob storage — local disk in dev, GCS in production (SGS-041)."""

    async def save(self, path: str, data: bytes) -> None: ...
    async def load(self, path: str) -> bytes: ...
    async def delete(self, path: str) -> None: ...


class LocalDiskStorage:
    def __init__(self, root: Path):
        self._root = root

    def _resolve(self, path: str) -> Path:
        if not path.strip():
            raise ValueError("Empty storage path")
        resolved = (self._root / path).resolve()
        root = self._root.resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise ValueError("Path escapes the storage root")
        return resolved

    async def save(self, path: str, data: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)

    async def load(self, path: str) -> bytes:
        return await asyncio.to_thread(self._resolve(path).read_bytes)

    async def delete(self, path: str) -> None:
        target = self._resolve(path)
        await asyncio.to_thread(target.unlink, True)


class GCSStorage:
    """Google Cloud Storage driver — production. Auth via ADC (the Cloud Run
    runtime service account)."""

    def __init__(self, bucket_name: str):
        self._bucket_name = bucket_name
        self._bucket: Any = None

    def _get_bucket(self) -> Any:
        if self._bucket is None:
            import google.cloud.storage as gcs

            self._bucket = gcs.Client().bucket(self._bucket_name)
        return self._bucket

    async def save(self, path: str, data: bytes) -> None:
        blob = self._get_bucket().blob(path)
        await asyncio.to_thread(blob.upload_from_string, data)

    async def load(self, path: str) -> bytes:
        blob = self._get_bucket().blob(path)
        data = await asyncio.to_thread(blob.download_as_bytes)
        return bytes(data)

    async def delete(self, path: str) -> None:
        from google.cloud.exceptions import NotFound as GCSNotFound

        blob = self._get_bucket().blob(path)
        try:
            await asyncio.to_thread(blob.delete)
        except GCSNotFound:
            pass  # same semantics as LocalDiskStorage missing_ok


@lru_cache
def get_storage() -> BlobStorage:
    settings = get_settings()
    if settings.storage_backend == "gcs":
        if not settings.gcs_bucket:
            raise RuntimeError("STORAGE_BACKEND=gcs requires GCS_BUCKET")
        return GCSStorage(settings.gcs_bucket)
    return LocalDiskStorage(Path(settings.storage_dir))
