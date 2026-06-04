"""Locate the built SPA and decide whether it is available.

The SPA is an optional build artifact. When it is missing (Node not run),
the app keeps working with the legacy HTMX UI.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse, FileResponse

WEB_DIR = Path(__file__).parent
SPA_DIR = WEB_DIR / "spa"
SPA_INDEX = SPA_DIR / "index.html"

_MISSING_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Meeting Processor</title></head><body style='font-family:sans-serif;"
    "max-width:40rem;margin:4rem auto;line-height:1.5'>"
    "<h1>SPA build ausente</h1>"
    "<p>O frontend novo ainda nao foi compilado. Rode:</p>"
    "<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>"
    "<p>Enquanto isso, a interface classica esta em "
    "<a href='/dashboard'>/dashboard</a>.</p>"
    "</body></html>"
)


def spa_built() -> bool:
    return SPA_INDEX.exists()


def spa_index_response():
    """Serve the SPA shell (or a build hint if it is missing)."""
    if spa_built():
        return FileResponse(SPA_INDEX)
    return HTMLResponse(_MISSING_HTML, status_code=200)
