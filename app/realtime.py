"""In-process Server-Sent Events bus for live operator updates.

Single-process broadcast: each SSE subscriber gets a bounded queue; publishing
with no subscribers is a no-op, and a slow subscriber drops (never blocks the
request path). Multi-worker deployments would need Redis pub/sub instead —
documented in NOTES.md, out of scope for this internal tool.
"""

import queue
from datetime import UTC, datetime

MAX_QUEUE = 100

_subscribers: set[queue.Queue] = set()


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=MAX_QUEUE)
    _subscribers.add(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    _subscribers.discard(q)


def publish(event: str, request_id: int, status_value: str, actor_id: int) -> None:
    """Fire-and-forget: never raises, never blocks the mutating request."""
    if not _subscribers:
        return
    payload = {
        "event": event,
        "request_id": request_id,
        "status": status_value,
        "actor_id": actor_id,
        "at": datetime.now(UTC).isoformat(),
    }
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except queue.Full:
            continue
