import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Protocol

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
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root.resolve()):
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


@lru_cache
def get_storage() -> BlobStorage:
    return LocalDiskStorage(Path(get_settings().storage_dir))
