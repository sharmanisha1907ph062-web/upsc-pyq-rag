"""Small local web interface for the existing UPSC RAG pipeline."""

import argparse
from collections import deque
import html
import math
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from dotenv import load_dotenv
from markdown_it import MarkdownIt

if __package__:
    from .rag import ENV_FILE, generate_answer
    from .retrieve import search_chunks
else:
    # Keep `python app/web.py` working for local Windows use.
    APP_FOLDER = Path(__file__).resolve().parent
    if str(APP_FOLDER) not in sys.path:
        sys.path.insert(0, str(APP_FOLDER))
    from rag import ENV_FILE, generate_answer
    from retrieve import search_chunks


PROJECT_FOLDER = Path(__file__).resolve().parent.parent
MARKDOWN = MarkdownIt("default", {"html": False, "linkify": False, "typographer": False})
ALLOWED_MARKDOWN_TAGS = {
    "a", "blockquote", "br", "code", "del", "em", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "li", "ol", "p", "pre", "s", "strong", "table", "tbody", "td", "th", "thead", "tr", "ul",
}
VOID_MARKDOWN_TAGS = {"br", "hr"}
RATE_LIMIT_WINDOW_SECONDS = 60 * 60
RATE_LIMIT_MAX_QUESTIONS = 20
_question_timestamps: deque[float] = deque()
_question_timestamps_lock = Lock()


def claim_question_slot() -> int | None:
    """Apply a process-wide rolling limit; return retry seconds when full."""
    now = monotonic()
    with _question_timestamps_lock:
        while _question_timestamps and now - _question_timestamps[0] >= RATE_LIMIT_WINDOW_SECONDS:
            _question_timestamps.popleft()
        if len(_question_timestamps) >= RATE_LIMIT_MAX_QUESTIONS:
            return max(1, math.ceil(RATE_LIMIT_WINDOW_SECONDS - (now - _question_timestamps[0])))
        _question_timestamps.append(now)
    return None


class MarkdownHTMLSanitizer(HTMLParser):
    """Rebuild renderer HTML using a small safe tag/attribute allowlist."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []

    @staticmethod
    def _safe_href(value: str) -> bool:
        parsed = urlsplit(value.strip())
        return parsed.scheme.lower() in {"http", "https", "mailto"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_MARKDOWN_TAGS:
            return
        rendered_attrs = ""
        if tag == "a":
            values = dict(attrs)
            href = values.get("href")
            if href and self._safe_href(href):
                rendered_attrs = f' href="{html.escape(href, quote=True)}" rel="nofollow noopener noreferrer"'
            title = values.get("title")
            if title:
                rendered_attrs += f' title="{html.escape(title, quote=True)}"'
        self.parts.append(f"<{tag}{rendered_attrs}>")
        if tag not in VOID_MARKDOWN_TAGS:
            self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_MARKDOWN_TAGS or tag in VOID_MARKDOWN_TAGS or tag not in self.open_tags:
            return
        while self.open_tags:
            opened = self.open_tags.pop()
            self.parts.append(f"</{opened}>")
            if opened == tag:
                break

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data))

    def finish(self) -> str:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts)


def render_markdown_safely(markdown: str) -> str:
    """Render common Markdown, then sanitize the HTML with an explicit allowlist."""
    rendered = MARKDOWN.render(markdown)
    sanitizer = MarkdownHTMLSanitizer()
    sanitizer.feed(rendered)
    sanitizer.close()
    return sanitizer.finish()


def render_page(question: str = "", source: str = "all", placement: str = "after", output: str = "") -> bytes:
    """Return a complete, escaped HTML page for the query form and response."""
    question_value = html.escape(question, quote=True)
    selected_source = {key: "selected" if source == key else "" for key in ("all", "study", "pyq")}
    selected_placement = {key: "checked" if placement == key else "" for key in ("before", "after")}
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UPSC Study Assistant</title>
  <style>
    :root {{ color-scheme: light; --ink:#17233b; --muted:#60708a; --line:#d9e1ed; --blue:#2457c5; --paper:#fff; }}
    * {{ box-sizing:border-box }} body {{ margin:0; background:#f3f6fb; color:var(--ink); font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif }}
    header {{ background:#142746; color:#fff; padding:28px max(22px,calc((100% - 900px)/2)) }} header h1 {{ margin:0 0 4px; font-size:1.55rem }} header p {{ margin:0; color:#d4deee }}
    main {{ max-width:900px; margin:28px auto; padding:0 18px }} section {{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:22px; margin-bottom:18px; box-shadow:0 5px 20px #1427460b }}
    label {{ display:block; font-weight:650; margin-bottom:7px }} textarea,select {{ width:100%; border:1px solid #bdc9da; border-radius:9px; padding:12px; color:var(--ink); font:inherit; background:#fff }} textarea {{ min-height:110px; resize:vertical }}
    .row {{ display:flex; gap:18px; align-items:end; margin-top:16px; flex-wrap:wrap }} .row > div {{ flex:1; min-width:200px }} .radios {{ display:flex; gap:16px; padding:8px 0 }} .radios label {{ font-weight:450; margin:0 }} input[type=radio] {{ accent-color:var(--blue) }}
    button {{ border:0; border-radius:9px; background:var(--blue); color:#fff; font:inherit; font-weight:650; padding:12px 20px; cursor:pointer }} button:hover {{ background:#1946a6 }}
    h2 {{ font-size:1.15rem; margin:0 0 12px }} h3 {{ font-size:1rem; margin:0 0 8px }} .answer-markdown {{ overflow-wrap:anywhere }} .answer-markdown h1,.answer-markdown h2,.answer-markdown h3,.answer-markdown h4 {{ margin:1em 0 .45em }} .answer-markdown p {{ margin:.55em 0 }} .answer-markdown table {{ border-collapse:collapse; display:block; max-width:100%; overflow-x:auto; margin:1em 0 }} .answer-markdown th,.answer-markdown td {{ border:1px solid var(--line); padding:7px 10px; text-align:left }} .answer-markdown th {{ background:#eef3fb }} .answer-markdown blockquote {{ border-left:3px solid #aab9d1; margin:1em 0; padding-left:14px; color:var(--muted) }} .answer-markdown pre {{ white-space:pre-wrap; background:#f3f6fb; border-radius:7px; padding:12px }} .answer-markdown a {{ color:var(--blue) }} .passage {{ border-top:1px solid var(--line); padding:14px 0 }} .passage:first-of-type {{ border-top:0 }} .meta {{ color:var(--muted); font-size:.9rem; margin:0 0 8px }} .text {{ white-space:pre-wrap; overflow-wrap:anywhere }}
    .notice {{ border-left:4px solid #dc9b20; background:#fff8e7; padding:12px 14px; border-radius:5px }} footer {{ color:var(--muted); font-size:.86rem; text-align:center; padding:8px 0 28px }}
  </style>
</head>
<body><header><h1>UPSC Study Assistant</h1><p>Ask a question and review the passages used to answer it.</p></header>
<main>
  <section><form method="post" action="/">
    <label for="question">Your question</label><textarea id="question" name="question" required maxlength="2000" placeholder="For example: What do Ashokan inscriptions tell us about Mauryan administration?">{question_value}</textarea>
    <div class="row"><div><label for="source">Search collections</label><select id="source" name="source"><option value="all" {selected_source['all']}>Study material and PYQ</option><option value="study" {selected_source['study']}>Study material</option><option value="pyq" {selected_source['pyq']}>PYQ</option></select></div>
    <div><label>Show passages</label><div class="radios"><label><input type="radio" name="placement" value="before" {selected_placement['before']}> Before answer</label><label><input type="radio" name="placement" value="after" {selected_placement['after']}> After answer</label></div></div>
    <button type="submit">Ask question</button></div>
  </form></section>
  {output}
</main><footer>Answers use retrieved project material. Check the cited passages.</footer></body></html>"""
    return page.encode("utf-8")


def render_results(question: str, source: str, placement: str) -> str:
    source_name = {"all": "study material and PYQ", "study": "study material", "pyq": "PYQ"}[source]
    result_html = [
        '<section><h2>Results</h2>',
        f'<p class="meta">Searched: {html.escape(source_name)} · Retrieved passages: {len(results := search_chunks(question, result_limit=3, source=source))}</p>',
    ]

    def add_passages() -> None:
        if not results:
            result_html.append('<p class="notice">No passages were found. The available context is insufficient to answer this question.</p>')
            return
        result_html.append("<h3>Retrieved passages</h3>")
        for rank, item in enumerate(results, start=1):
            metadata = item.get("metadata") or {}
            filename = html.escape(str(metadata.get("source", "unknown")))
            page = metadata.get("page")
            page_label = f"Page {html.escape(str(page))}" if page is not None else "Page unavailable (TXT source)"
            chunk_id = html.escape(str(item.get("chunk_id", "unavailable")))
            body = html.escape(item.get("text") or "[No document text stored]")
            collection = html.escape(str(item.get("collection", "unknown")))
            distance = html.escape(str(item.get("distance", "unavailable")))
            result_html.append(
                f'<article class="passage"><h3>Passage {rank}</h3>'
                f'<p class="meta">{filename} · {page_label} · Chunk {chunk_id} · {collection} · distance {distance}</p>'
                f'<div class="text">{body}</div></article>'
            )

    if placement == "before":
        add_passages()
    if not results:
        result_html.append('<h3>Answer</h3><p class="answer">Insufficient context: no passages were retrieved.</p>')
    else:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        model = os.getenv("GROQ_MODEL", "").strip()
        if not api_key or not model:
            missing = [name for name, value in (("GROQ_API_KEY", api_key), ("GROQ_MODEL", model)) if not value]
            result_html.append(
                '<p class="notice">Answer generation is not configured. Set '
                + html.escape(", ".join(missing))
                + ' in the project-root .env file.</p>'
            )
        else:
            try:
                answer = generate_answer(question, results, api_key, model)
                safe_answer_html = render_markdown_safely(answer)
                result_html.append(f'<h3>Answer (grounded in retrieved context)</h3><div class="answer-markdown">{safe_answer_html}</div>')
            except Exception as error:
                safe_error = str(error).replace(api_key, "[REDACTED]")
                result_html.append(f'<p class="notice">Answer generation failed: {html.escape(safe_error)}</p>')
    if placement == "after":
        add_passages()
    result_html.append("</section>")
    return "".join(result_html)


class RAGRequestHandler(BaseHTTPRequestHandler):
    def send_html(self, body: bytes, status: int = 200, retry_after: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self.send_html(render_page())

    def do_POST(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_html(render_page(output='<p class="notice">Invalid form submission.</p>'), 400)
            return
        if length < 1 or length > 16_384:
            self.send_html(render_page(output='<p class="notice">Form submission must be under 16 KB.</p>'), 400)
            return
        fields = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"), max_num_fields=10)
        question = fields.get("question", [""])[0].strip()
        source = fields.get("source", ["all"])[0]
        placement = fields.get("placement", ["after"])[0]
        if not question or len(question) > 2000 or source not in {"all", "study", "pyq"} or placement not in {"before", "after"}:
            output = '<p class="notice">Enter a question (up to 2,000 characters) and choose a valid source and passage position.</p>'
            self.send_html(render_page(question, source if source in {"all", "study", "pyq"} else "all", placement if placement in {"before", "after"} else "after", output), 400)
            return
        retry_after = claim_question_slot()
        if retry_after is not None:
            output = (
                '<section><p class="notice">This demo has reached its limit of 20 questions per hour. '
                'Please try again later.</p></section>'
            )
            self.send_html(render_page(question, source, placement, output), 429, retry_after=retry_after)
            return
        try:
            output = render_results(question, source, placement)
        except Exception as error:
            output = f'<section><p class="notice">Search failed: {html.escape(str(error))}</p></section>'
        self.send_html(render_page(question, source, placement, output))

    def log_message(self, format: str, *args: object) -> None:
        # Keep the local console concise and avoid echoing submitted question text.
        print(f"{self.log_date_time_string()} {self.command} {self.path} {args[1] if len(args) > 1 else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local UPSC-PYQ-RAG web interface.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only).")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve on (default: 8000).")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    server = ThreadingHTTPServer((args.host, args.port), RAGRequestHandler)
    print(f"UPSC-PYQ-RAG is available at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
