"""Small live retrieval/Groq check for the Ashokan study note.

Run with: ``.\\venv\\Scripts\\python.exe app\\test_rag.py``
This makes four Groq chat-completion requests and never prints credentials.
"""

import os

from dotenv import load_dotenv

from rag import ENV_FILE, generate_answer
from retrieve import search_chunks


SUPPORTED_CASES = [
    (
        "What forms do Ashokan inscriptions take?",
        ("rock", "pillar", "cave"),
    ),
    (
        "Which languages and scripts appear in Ashoka's inscriptions?",
        ("prakrit", "brahmi", "kharosthi"),
    ),
    (
        "What ethical principles did Ashoka promote through Dhamma?",
        ("respect for parents", "compassion", "different sects"),
    ),
]
UNSUPPORTED_CASE = "What exact annual land-tax rate did Ashoka impose on rice farmers?"
def visible_source_names(results: list[dict]) -> set[str]:
    return {result["metadata"].get("source", "") for result in results}


def main() -> None:
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()
    if not api_key or not model:
        missing = [name for name, value in (("GROQ_API_KEY", api_key), ("GROQ_MODEL", model)) if not value]
        raise SystemExit(f"Missing {', '.join(missing)} in the project-root .env; no credentials were displayed.")

    cases_passed = 0
    for index, (question, expected_terms) in enumerate(SUPPORTED_CASES, start=1):
        results = search_chunks(question, result_limit=3, source="study")
        if not results:
            raise SystemExit(f"FAIL supported case {index}: no study passages retrieved.")
        if "ashokan_inscriptions.txt" not in visible_source_names(results):
            raise SystemExit(f"FAIL supported case {index}: retrieved source was not the Ashokan note.")
        retrieved_text = "\n".join(result["text"] for result in results).casefold()
        missing_terms = [term for term in expected_terms if term.casefold() not in retrieved_text]
        if missing_terms:
            raise SystemExit(
                f"FAIL supported case {index}: retrieved passages lacked expected topic terms "
                f"{missing_terms}; no expected answer text is embedded in app/rag.py."
            )
        try:
            answer = generate_answer(question, results, api_key, model)
        except Exception as error:
            message = str(error).replace(api_key, "[REDACTED]")
            raise SystemExit(f"FAIL supported case {index}: Groq request failed: {message}") from None
        if not answer.strip():
            raise SystemExit(f"FAIL supported case {index}: Groq returned an empty answer.")
        if "ashokan_inscriptions.txt" not in answer.casefold():
            raise SystemExit(
                f"FAIL supported case {index}: generated answer did not cite the retrieved Ashokan note."
            )
        print(
            f"PASS supported case {index}: relevant note passages retrieved and answer cites the source file."
        )
        cases_passed += 1

    unsupported_results = search_chunks(UNSUPPORTED_CASE, result_limit=3, source="study")
    if not unsupported_results:
        raise SystemExit("FAIL unsupported case: no study passages retrieved to assess sufficiency.")
    try:
        unsupported_answer = generate_answer(UNSUPPORTED_CASE, unsupported_results, api_key, model)
    except Exception as error:
        message = str(error).replace(api_key, "[REDACTED]")
        raise SystemExit(f"FAIL unsupported case: Groq request failed: {message}") from None

    if not unsupported_answer.startswith("Insufficient context:"):
        raise SystemExit(
            "FAIL unsupported case: response did not begin with 'Insufficient context:'. "
            "Review the answer and refine the grounding instruction if needed."
        )
    print("PASS unsupported case: Groq explicitly reported insufficient context.")
    print(f"\nRAG checks passed: {cases_passed + 1}/4")


if __name__ == "__main__":
    main()
