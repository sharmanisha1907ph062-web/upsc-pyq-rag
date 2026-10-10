"""Split the OCR text into small, page-aware chunks for later RAG stages."""

import json
import re
from pathlib import Path


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_FOLDER / "data" / "extracted_text.txt"
OUTPUT_FILE = PROJECT_FOLDER / "data" / "chunks.json"
TARGET_SIZE = 800
OVERLAP = 150
PAGE_MARKER = re.compile(r"^--- PAGE (\d+) ---\s*$", re.MULTILINE)


def split_at_word_boundary(text: str, start: int, target_end: int) -> int:
    """Choose a nearby whitespace boundary so chunks do not split words."""
    if target_end >= len(text):
        return len(text)

    lower_bound = start + max(1, TARGET_SIZE // 2)
    # Prefer the last whitespace before the target; if it is too early, use
    # the next whitespace after the target to keep chunks near the target size.
    boundary = text.rfind(" ", lower_bound, target_end + 1)
    if boundary <= start:
        boundary = text.find(" ", target_end)
    if boundary < 0:
        return len(text)
    return boundary


def make_chunks(page_text: str, page_number: int, source: str) -> list[dict]:
    """Chunk one page at a time and retain its marker and page metadata."""
    body = page_text.strip()
    marker = f"--- PAGE {page_number} ---"
    if not body:
        return [{"chunk_id": f"page-{page_number}-chunk-1", "text": marker,
                 "source": source, "page": page_number}]

    chunks = []
    start = 0
    part_number = 1
    while start < len(body):
        end = split_at_word_boundary(body, start, min(start + TARGET_SIZE, len(body)))
        piece = body[start:end].strip()
        if piece:
            chunks.append({
                "chunk_id": f"page-{page_number}-chunk-{part_number}",
                "text": f"{marker}\n{piece}",
                "source": source,
                "page": page_number,
            })
            part_number += 1
        if end >= len(body):
            break

        # Move forward by approximately TARGET_SIZE - OVERLAP characters,
        # backing up to whitespace to preserve both overlap and whole words.
        next_start = max(start + 1, end - OVERLAP)
        whitespace = body.rfind(" ", start + 1, next_start + 1)
        if whitespace > start:
            next_start = whitespace + 1
        start = next_start

    return chunks


def main() -> None:
    if not INPUT_FILE.is_file():
        raise SystemExit(f"OCR input was not found: {INPUT_FILE}")

    text = INPUT_FILE.read_text(encoding="utf-8")
    matches = list(PAGE_MARKER.finditer(text))
    if not matches:
        raise SystemExit("No page markers (--- PAGE n ---) were found in the OCR text.")

    source = INPUT_FILE.name
    chunks = []
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunks.extend(make_chunks(text[content_start:content_end], page_number, source))

    try:
        OUTPUT_FILE.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"Could not write chunks to {OUTPUT_FILE}: {error}") from error

    print(f"Total chunks: {len(chunks)}")
    print(f"Target chunk size: {TARGET_SIZE} characters; overlap: about {OVERLAP} characters")
    for chunk in chunks[:3]:
        print(f"\nChunk {chunk['chunk_id']} | source: {chunk['source']} | page: {chunk['page']} | characters: {len(chunk['text'])}")
        print(chunk["text"])
    print(f"\nSaved chunks to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
