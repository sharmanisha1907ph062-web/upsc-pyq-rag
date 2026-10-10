"""Persist precomputed UPSC question paper embeddings in ChromaDB."""

import json
from pathlib import Path

import chromadb


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_FOLDER / "data" / "embeddings.json"
DATABASE_FOLDER = PROJECT_FOLDER / "data" / "chroma_db"
COLLECTION_NAME = "upsc_pyq"
BATCH_SIZE = 500


def main() -> None:
    if not INPUT_FILE.is_file():
        raise SystemExit(f"Embeddings input was not found: {INPUT_FILE}")

    try:
        records = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not read valid embeddings from {INPUT_FILE}: {error}") from error

    if not isinstance(records, list):
        raise SystemExit("Expected data/embeddings.json to contain a JSON array.")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise SystemExit(f"Embedding record {index} must be a JSON object.")
        required = ("chunk_id", "embedding", "text", "source", "page")
        if any(field not in record for field in required):
            raise SystemExit(f"Embedding record {index} is missing one or more required fields: {required}")

    client = chromadb.PersistentClient(path=str(DATABASE_FOLDER))
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    # Upsert makes reruns idempotent: each chunk_id identifies one record.
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        if not batch:
            continue
        collection.upsert(
            ids=[record["chunk_id"] for record in batch],
            embeddings=[record["embedding"] for record in batch],
            documents=[record["text"] for record in batch],
            metadatas=[{"source": record["source"], "page": record["page"]} for record in batch],
        )

    stored_count = collection.count()
    if stored_count != len(records):
        raise SystemExit(
            f"Collection count verification failed: {stored_count} records stored, {len(records)} expected."
        )

    first_id = records[0]["chunk_id"] if records else None
    first_metadata = None
    if first_id is not None:
        first = collection.get(ids=[first_id], include=["metadatas"])
        if not first["ids"]:
            raise SystemExit(f"Could not read back first stored record: {first_id}")
        first_metadata = first["metadatas"][0]

    print(f"Collection name: {COLLECTION_NAME}")
    print(f"Number of records stored: {stored_count}")
    print(f"First stored ID: {first_id if first_id is not None else 'N/A'}")
    print(f"First stored metadata: {first_metadata if first_metadata is not None else 'N/A'}")
    print(f"Verified count matches embeddings.json: {stored_count == len(records)}")
    print(f"Persistent database location: {DATABASE_FOLDER}")


if __name__ == "__main__":
    main()
