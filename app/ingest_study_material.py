"""Extract, chunk, embed, and store PDFs/TXT files in a separate collection."""

import hashlib
from pathlib import Path

import chromadb
import pymupdf
import pytesseract
from PIL import Image
from sentence_transformers import SentenceTransformer

from ingest import DPI, TESSERACT_EXE


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
STUDY_FOLDER = PROJECT_FOLDER / "data" / "study_material"
DATABASE_FOLDER = PROJECT_FOLDER / "data" / "chroma_db"
COLLECTION_NAME = "study_material"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
BATCH_SIZE = 128


def split_text(text: str) -> list[str]:
    """Split text into overlapping chunks while preferring whitespace boundaries."""
    text = text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = max(text.rfind(" ", start + CHUNK_SIZE // 2, end),
                           text.rfind("\n", start + CHUNK_SIZE // 2, end))
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        next_start = max(start + 1, end - CHUNK_OVERLAP)
        boundary = max(text.rfind(" ", start + 1, next_start + 1),
                       text.rfind("\n", start + 1, next_start + 1))
        start = boundary + 1 if boundary > start else next_start
    return chunks


def extract_source(path: Path) -> list[tuple[str, int | None]]:
    """Return extracted text and optional page number for each logical page."""
    if path.suffix.lower() == ".pdf":
        try:
            with pymupdf.open(path) as document:
                pages = []
                for page_number, page in enumerate(document, start=1):
                    text = page.get_text("text").strip()
                    if not text:
                        if not TESSERACT_EXE.is_file():
                            raise ValueError(
                                f"Page {page_number} of {path.name} is scanned, but Tesseract was not found at "
                                f"{TESSERACT_EXE}."
                            )
                        pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
                        scale = DPI / 72
                        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                        text = pytesseract.image_to_string(image, lang="eng").strip()
                    pages.append((text, page_number))
                return pages
        except Exception as error:
            raise ValueError(f"Could not extract PDF {path.name}: {error}") from error
    try:
        return [(path.read_text(encoding="utf-8-sig"), None)]
    except UnicodeDecodeError as error:
        raise ValueError(f"Text file {path.name} is not valid UTF-8; save it as UTF-8 and retry.") from error


def main() -> None:
    STUDY_FOLDER.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in STUDY_FOLDER.iterdir()
                   if path.is_file() and path.suffix.lower() in {".pdf", ".txt"})
    if not files:
        print(f"No PDF or TXT study files found in {STUDY_FOLDER}")
        print("Add a PDF or UTF-8 TXT file there and run this script again.")
        return

    client = chromadb.PersistentClient(path=str(DATABASE_FOLDER))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "l2"},
    )
    pending = []
    changed_sources = []
    for path in files:
        source = path.name
        source_pages = extract_source(path)
        source_records = []
        file_key = hashlib.sha256(source.casefold().encode("utf-8")).hexdigest()[:12]
        for page_text, page_number in source_pages:
            for chunk_number, text in enumerate(split_text(page_text), start=1):
                page_key = f"p{page_number:04d}" if page_number is not None else "text"
                chunk_id = f"study-{file_key}-{page_key}-c{chunk_number:04d}"
                metadata = {"source": source, "material_type": "study_material"}
                if page_number is not None:
                    metadata["page"] = page_number
                source_records.append({"id": chunk_id, "text": text, "metadata": metadata})

        pending.extend(source_records)
        changed_sources.append((source, {record["id"] for record in source_records}))
        print(f"Extracted {len(source_records)} chunks from {source}")

    if pending:
        model = SentenceTransformer(MODEL_NAME)
        texts = [record["text"] for record in pending]
        vectors = model.encode(texts, show_progress_bar=True, batch_size=32)
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start:start + BATCH_SIZE]
            collection.upsert(
                ids=[record["id"] for record in batch],
                embeddings=[vector.tolist() for vector in vectors[start:start + BATCH_SIZE]],
                documents=[record["text"] for record in batch],
                metadatas=[record["metadata"] for record in batch],
            )

    # Remove superseded chunks only after all current source chunks were upserted.
    for source, current_ids in changed_sources:
        existing = collection.get(where={"source": source}, include=["metadatas"])
        stale_ids = [item_id for item_id in existing["ids"] if item_id not in current_ids]
        if stale_ids:
            collection.delete(ids=stale_ids)

    print(f"Collection: {COLLECTION_NAME}")
    print(f"Study-material files processed: {len(files)}")
    print(f"Chunks upserted this run: {len(pending)}")
    print(f"Total study-material records: {collection.count()}")
    print(f"Persistent database: {DATABASE_FOLDER}")


if __name__ == "__main__":
    main()
