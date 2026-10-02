"""Shared Jinja setup + content-negotiation helpers for the HTMX UI."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

# auto_reload: template edits show up without restarting the dev server
# (uvicorn --reload only watches .py files; Jinja caches parsed templates).
templates = Jinja2Templates(directory="app/templates", auto_reload=True)


def wants_html(request: Request) -> bool:
    # HTMX partial requests (HX-Request) expect HTML even though XHR sends
    # Accept: */*; otherwise the table swap receives JSON and blanks out.
    return (
        "text/html" in request.headers.get("accept", "")
        or request.headers.get("hx-request") == "true"
    )
