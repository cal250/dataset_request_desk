import json
import queue
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth import get_operator_user
from app.models.user import User
from app.realtime import subscribe, unsubscribe

router = APIRouter(tags=["realtime"])


async def _stream():
    q = subscribe()
    try:
        yield 'event: connected\ndata: {"ok": true}\n\n'
        while True:
            try:
                # A thread hop: the bus is a thread-safe sync queue fed by
                # sync service code; 25s idle produces a heartbeat comment.
                item = await anyio.to_thread.run_sync(q.get, True, 25)
            except queue.Empty:
                yield ": ping\n\n"
                continue
            yield f"data: {json.dumps(item)}\n\n"
    finally:
        unsubscribe(q)


@router.get("/events")
async def events(user: Annotated[User, Depends(get_operator_user)]):
    """Live request feed for operators/admins (clients get 403)."""
    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
