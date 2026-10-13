# UPSC PYQ RAG Assistant Portfolio

A static HTML, CSS, and JavaScript project portfolio for the UPSC PYQ RAG Assistant. It is suitable for GitHub Pages and does not require a Python backend. The interactive RAG application is a separate project component: its Python backend has been tested locally, while public deployment is pending. This portfolio does not accept questions or generate answers.

## Preview locally

From the repository root, start a simple static file server with Python:

```powershell
py -m http.server 8001 --directory portfolio
```

Then open <http://127.0.0.1:8001>. Stop the server with `Ctrl+C`. Alternatively, open `portfolio/index.html` directly in a browser.

## Publish with GitHub Pages

1. Push this repository to GitHub when you are ready. The workflow at `.github/workflows/pages.yml` publishes only `portfolio/index.html`, `portfolio/style.css`, and `portfolio/script.js`; the portfolio README and all files outside that allowlist are excluded. If your default branch is not named `main`, change the workflow's branch filter before pushing.
2. On the repository page, open **Settings → Pages**.
3. Under **Build and deployment**, choose **GitHub Actions** as the source.
4. Push the workflow and portfolio files to the configured branch, or run **Publish portfolio to GitHub Pages** from the **Actions** tab using **Run workflow**.
5. Wait for the workflow to finish. The project site URL will be `https://sharmanish1907ph062-web.github.io/upsc-pyq-rag/` for this repository.

All local links and asset references are relative, so the page works from the repository subpath. The GitHub repository link is external and opens in a new tab.

## Customize before or after publishing

- Replace the labeled screenshot placeholders in `index.html` with real screenshots and use relative image paths, for example `screenshots/question-interface.png`.
- Replace the contact placeholder only with contact information you choose to publish.
- The screenshots and contact area intentionally contain no fabricated personal or project details.

## Files

- `index.html` — accessible page structure and project content.
- `style.css` — responsive dark visual design, diagrams, and reduced-motion handling.
- `script.js` — mobile navigation and subtle section reveal effects; it does not implement question answering.
