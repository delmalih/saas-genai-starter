from dataclasses import dataclass

import pymupdf


@dataclass(frozen=True)
class Page:
    number: int | None  # 1-based; None for formats without pages
    text: str


@dataclass(frozen=True)
class Chunk:
    page: int | None
    position: int
    content: str


def extract_pages(data: bytes, mime_type: str) -> list[Page]:
    if mime_type == "application/pdf":
        with pymupdf.open(stream=data, filetype="pdf") as document:
            return [
                Page(number=index + 1, text=page.get_text()) for index, page in enumerate(document)
            ]
    return [Page(number=None, text=data.decode("utf-8", errors="replace"))]


# Word-based approximation of the ~512-token / ~64-token-overlap target
# (roughly 0.75 words per token). Good enough for retrieval; an exact
# tokenizer would add a heavy dependency for marginal gain.
TARGET_WORDS = 380
OVERLAP_WORDS = 48
MIN_CHUNK_WORDS = 20


def chunk_pages(pages: list[Page]) -> list[Chunk]:
    chunks: list[Chunk] = []
    position = 0
    for page in pages:
        words = page.text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            window = words[start : start + TARGET_WORDS]
            is_tail = start + TARGET_WORDS >= len(words)
            if chunks and is_tail and len(window) < MIN_CHUNK_WORDS:
                # Tiny tail: merge into the previous chunk instead of
                # emitting a fragment with no retrieval value.
                previous = chunks[-1]
                chunks[-1] = Chunk(
                    page=previous.page,
                    position=previous.position,
                    content=previous.content + " " + " ".join(window),
                )
                break
            chunks.append(Chunk(page=page.number, position=position, content=" ".join(window)))
            position += 1
            if is_tail:
                break
            start += TARGET_WORDS - OVERLAP_WORDS
    return chunks
