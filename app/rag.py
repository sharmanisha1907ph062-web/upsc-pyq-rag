"""Answer UPSC questions using retrieved project context and Groq."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from retrieve import DEFAULT_QUESTION, search_chunks


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_FOLDER / ".env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Answer a UPSC question using retrieved PYQ and study-material context with Groq."
    )
    parser.add_argument("question", nargs="*", help="Question to search for (defaults to a sample question).")
    parser.add_argument(
        "--source",
        choices=("all", "pyq", "study"),
        default="all",
        help="Search both collections or restrict retrieval to one (default: all).",
    )
    parser.add_argument(
        "--passages",
        choices=("before", "after"),
        default="before",
        help="Display retrieved passages before or after the generated answer (default: before).",
    )
    args = parser.parse_args()
    args.question = " ".join(args.question).strip() if args.question else DEFAULT_QUESTION
    if not args.question:
        parser.error("question cannot be empty")
    return args


def display_passages(results: list[dict]) -> None:
    """Print retrieved records with collection, source, page, and chunk references."""
    if not results:
        print("No passages were retrieved.")
        return
    print("\nRetrieved passages:")
    for rank, result in enumerate(results, start=1):
        metadata = result["metadata"]
        page = metadata.get("page")
        page_label = f"page {page}" if page is not None else "page unavailable (TXT source)"
        print(f"\nPassage {rank} | collection: {result['collection']} | distance: {result['distance']}")
        print(f"Source: {metadata.get('source', 'unknown')} | {page_label}")
        print(f"Chunk ID: {result.get('chunk_id', 'unavailable')}")
        print(result["text"] or "[No document text stored]")


def generate_answer(question: str, results: list[dict], api_key: str, model: str) -> str:
    """Generate a context-grounded answer and require source-page citations."""
    passages = []
    for result in results:
        metadata = result["metadata"]
        source = metadata.get("source", "unknown")
        page = metadata.get("page")
        page_reference = f", page {page}" if page is not None else ""
        passages.append(
            f"[Source: {source}{page_reference}; collection {result['collection']}; "
            f"chunk {result['chunk_id']}]\n{result['text']}"
        )

    context = "\n\n---\n\n".join(passages)
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an assistant for UPSC preparation. Answer using only the supplied retrieved context. "
                    "Do not add outside facts or fill gaps from memory. If the context does not adequately answer "
                    "the question, begin the response with the exact label 'Insufficient context:' and identify "
                    "what information is missing. Never guess. Cite factual statements with the source filename "
                    "and, when available, page number, "
                    "for example [Source: filename, p. N]. For TXT sources cite the filename without a page."
                ),
            },
            {
                "role": "user",
                "content": f"Question:\n{question}\n\nRetrieved context:\n{context}",
            },
        ],
        temperature=0.2,
    )
    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise RuntimeError("Groq returned an empty answer.")
    return answer.strip()


def main() -> None:
    args = parse_args()
    # Resolve .env from the project path above, independent of the terminal cwd.
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    results = search_chunks(args.question, result_limit=3, source=args.source)
    collection_label = {
        "study": "study material",
        "pyq": "PYQ",
        "all": "study material and PYQ",
    }[args.source]
    print(f"Question: {args.question}")
    print(f"Collections searched: {collection_label}")
    print(f"Retrieved passages: {len(results)}")

    if args.passages == "before":
        display_passages(results)

    if not results:
        print("\nAnswer: The retrieved context is insufficient because no passages were found.")
        if args.passages == "after":
            display_passages(results)
        return

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()
    if not api_key or not model:
        missing = []
        if not api_key:
            missing.append("GROQ_API_KEY")
        if not model:
            missing.append("GROQ_MODEL")
        print("\nAnswer generation is not configured.")
        print(f"Set {', '.join(missing)} in the project-root .env file to enable Groq answers.")
        if args.passages == "after":
            display_passages(results)
        return

    try:
        answer = generate_answer(args.question, results, api_key, model)
    except Exception as error:
        # Never include credentials in diagnostics; SDK exceptions normally omit them,
        # but redact the configured key defensively before displaying the message.
        safe_error = str(error).replace(api_key, "[REDACTED]") if api_key else str(error)
        print(f"\nGroq answer generation failed: {safe_error}")
        raise SystemExit(1) from None

    print("\nAnswer (grounded in retrieved context):")
    print(answer)
    if args.passages == "after":
        display_passages(results)


if __name__ == "__main__":
    main()
