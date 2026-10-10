"""Read-only status check for study-material files and Chroma records."""

from pathlib import Path

import chromadb


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
STUDY_FOLDER = PROJECT_FOLDER / "data" / "study_material"
DATABASE_FOLDER = PROJECT_FOLDER / "data" / "chroma_db"
COLLECTION_NAME = "study_material"
SUPPORTED_EXTENSIONS = {".pdf", ".txt"}
PAGE_SIZE = 1000


def main() -> None:
    files = (
        [path for path in STUDY_FOLDER.iterdir()
         if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
        if STUDY_FOLDER.is_dir()
        else []
    )
    print(f"Study-material folder exists: {STUDY_FOLDER.is_dir()}")
    print(f"PDF/TXT files present: {len(files)}")

    if not DATABASE_FOLDER.is_dir():
        print(f'Collection "{COLLECTION_NAME}" exists: False')
        print("Indexed source files: 0")
        print("Indexed chunks: 0")
        return

    client = chromadb.PersistentClient(path=str(DATABASE_FOLDER))
    available = {item.name for item in client.list_collections()}
    if COLLECTION_NAME not in available:
        print(f'Collection "{COLLECTION_NAME}" exists: False')
        print("Indexed source files: 0")
        print("Indexed chunks: 0")
        return

    collection = client.get_collection(COLLECTION_NAME)
    count = collection.count()
    indexed_sources = set()
    for offset in range(0, count, PAGE_SIZE):
        batch = collection.get(limit=PAGE_SIZE, offset=offset, include=["metadatas"])
        for metadata in batch["metadatas"] or []:
            if metadata and metadata.get("source"):
                indexed_sources.add(metadata["source"])

    print(f'Collection "{COLLECTION_NAME}" exists: True')
    print(f"Indexed source files: {len(indexed_sources)}")
    print(f"Indexed chunks: {count}")
    print("Note contents and environment variables were not read or displayed.")


if __name__ == "__main__":
    main()
