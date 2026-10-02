"""Shared Jinja setup + content-negotiation helpers for the HTMX UI."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def wants_html(request: Request) -> bool:
    # HTMX partial requests (HX-Request) expect HTML even though XHR sends
    # Accept: */*; otherwise the table swap receives JSON and blanks out.
    return (
        "text/html" in request.headers.get("accept", "")
        or request.headers.get("hx-request") == "true"
    )
