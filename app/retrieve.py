"""Search UPSC PYQs, personal study material, or both in ChromaDB."""

import argparse
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATABASE_FOLDER = PROJECT_FOLDER / "data" / "chroma_db"
COLLECTIONS = {"pyq": "upsc_pyq", "study": "study_material"}
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
RESULT_LIMIT = 3
DEFAULT_QUESTION = "What is the importance of Ashokan inscriptions for Mauryan history?"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find relevant UPSC PYQ and study-material passages.")
    parser.add_argument("question", nargs="*", help="Search question (omit it to use a default question).")
    parser.add_argument(
        "--source",
        choices=("all", "pyq", "study"),
        default="all",
        help="Collection to search (default: both collections).",
    )
    args = parser.parse_args()
    args.question = " ".join(args.question).strip() if args.question else DEFAULT_QUESTION
    if not args.question:
        parser.error("search question cannot be empty")
    return args


def search_chunks(question: str, result_limit: int = RESULT_LIMIT, source: str = "all") -> list[dict]:
    """Embed a question and return the closest records from selected collections."""
    question = question.strip() if isinstance(question, str) else ""
    if not question:
        raise ValueError("search question cannot be empty")
    if result_limit < 1:
        raise ValueError("result_limit must be at least 1")
    if source not in {"all", "pyq", "study"}:
        raise ValueError("source must be 'all', 'pyq', or 'study'")
    if not DATABASE_FOLDER.is_dir():
        raise SystemExit(f"ChromaDB database was not found: {DATABASE_FOLDER}")

    client = chromadb.PersistentClient(path=str(DATABASE_FOLDER))
    available = {item.name for item in client.list_collections()}
    selected = list(COLLECTIONS) if source == "all" else [source]
    selected = [kind for kind in selected if COLLECTIONS[kind] in available]
    if not selected:
        return []

    collections = [(kind, client.get_collection(COLLECTIONS[kind])) for kind in selected]
    if not any(collection.count() for _, collection in collections):
        return []

    model = SentenceTransformer(MODEL_NAME)
    question_embedding = model.encode(question).tolist()
    matches = []
    for kind, collection in collections:
        count = collection.count()
        if not count:
            continue
        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=min(result_limit, count),
            include=["documents", "metadatas", "distances"],
        )
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for index, chunk_id in enumerate(ids):
            matches.append({
                "chunk_id": chunk_id,
                "text": documents[index] if index < len(documents) and documents[index] else "",
                "metadata": (metadatas[index] or {}) if index < len(metadatas) else {},
                "distance": distances[index] if index < len(distances) else None,
                "collection": kind,
            })

    matches.sort(key=lambda item: item["distance"] if item["distance"] is not None else float("inf"))
    return matches[:result_limit]


def main() -> None:
    args = parse_args()
    results = search_chunks(args.question, source=args.source)
    print(f"Question: {args.question}")
    print(f"Source: {args.source} | results: {len(results)}")
    if not results:
        print("No matching passages found in the selected collections.")
        return

    for index, result in enumerate(results, start=1):
        metadata = result["metadata"]
        page = metadata.get("page")
        page_label = f"Page: {page}" if page is not None else "Page: unavailable (text source)"
        print(f"\nRank: {index} | Distance: {result['distance'] if result['distance'] is not None else 'unavailable'}")
        print(f"Collection: {result['collection']} | Chunk ID: {result['chunk_id']}")
        print(f"Source: {metadata.get('source', 'unknown')} | {page_label}")
        print("Text:")
        print(result["text"] or "[No document text stored]")


if __name__ == "__main__":
    main()
