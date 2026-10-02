"""Shared Jinja setup + content-negotiation helpers for the HTMX UI."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")
