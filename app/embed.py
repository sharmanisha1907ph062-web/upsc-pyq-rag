"""Generate local semantic embeddings for the project's text chunks."""

import json
from pathlib import Path

from sentence_transformers import SentenceTransformer


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_FOLDER / "data" / "chunks.json"
OUTPUT_FILE = PROJECT_FOLDER / "data" / "embeddings.json"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    if not INPUT_FILE.is_file():
        raise SystemExit(f"Chunks input was not found: {INPUT_FILE}")

    try:
        chunks = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not read valid chunks from {INPUT_FILE}: {error}") from error

    if not isinstance(chunks, list):
        raise SystemExit("Expected data/chunks.json to contain a JSON array.")
    if any(not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str) for chunk in chunks):
        raise SystemExit('Every chunk must be an object with a string "text" field.')

    model = SentenceTransformer(MODEL_NAME)
    vectors = model.encode([chunk["text"] for chunk in chunks], show_progress_bar=True)

    embeddings = []
    for chunk, vector in zip(chunks, vectors):
        embeddings.append({
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "source": chunk["source"],
            "page": chunk["page"],
            "embedding": vector.tolist(),
        })

    if len(embeddings) != len(chunks):
        raise SystemExit(f"Embedding count mismatch: {len(embeddings)} embeddings for {len(chunks)} chunks.")

    try:
        OUTPUT_FILE.write_text(json.dumps(embeddings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"Could not write embeddings to {OUTPUT_FILE}: {error}") from error

    # Read back the file and verify the saved record count and vector dimensions.
    try:
        saved = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not verify saved embeddings at {OUTPUT_FILE}: {error}") from error
    if len(saved) != len(chunks) or any(
        not isinstance(item.get("embedding"), list) or not item["embedding"] for item in saved
    ):
        raise SystemExit("Saved embeddings failed count or vector validation.")

    first = saved[0] if saved else None
    dimension = len(first["embedding"]) if first else model.get_sentence_embedding_dimension()
    print(f"Chunks embedded: {len(saved)}")
    print(f"Embedding vector dimension: {dimension}")
    print(f"First chunk ID: {first['chunk_id'] if first else 'N/A'}")
    print(f"First 5 embedding values: {first['embedding'][:5] if first else []}")
    print(f"Saved and verified embeddings at: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
