import json
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(message)s")


async def structured_request_log(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started_at = time.perf_counter()
    response = await call_next(request)
    logging.getLogger("app.request").info(
        json.dumps(
            {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "user_id": getattr(request.state, "user_id", None),
            }
        )
    )
    return response

