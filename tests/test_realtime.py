"""Real-time feed: auth guards, bus delivery, live UI hook."""

from fastapi import status
from fastapi.testclient import TestClient

from app.models.user import User
from app.realtime import _subscribers, publish, subscribe, unsubscribe


def _login(client: TestClient, user: User) -> None:
    assert (
        client.post("/login", data={"email": user.email, "password": "password123"}).status_code
        == 200
    )


def test_events_require_operator(client: TestClient, client_user: User) -> None:
    assert client.get("/events").status_code == status.HTTP_401_UNAUTHORIZED
    _login(client, client_user)
    assert client.get("/events").status_code == status.HTTP_403_FORBIDDEN


def test_bus_delivers_to_subscribers_only() -> None:
    assert publish("request.created", 1, "submitted", 9) is None  # no subscribers: no-op
    q = subscribe()
    try:
        publish("request.updated", 7, "delivered", 3)
        item = q.get(timeout=2)
        assert item["event"] == "request.updated"
        assert item["request_id"] == 7
        assert item["status"] == "delivered"
        assert item["actor_id"] == 3
        assert item["at"]
    finally:
        unsubscribe(q)
    assert q not in _subscribers


def test_stream_delivers_published_event() -> None:
    """Drive the SSE generator directly: connected frame, then the live event."""
    import asyncio

    from app.routes.realtime import _stream

    async def main() -> str:
        gen = _stream()
        try:
            first = await gen.__anext__()
            assert first.startswith("event: connected")
            publish("request.created", 42, "submitted", 9)
            return await asyncio.wait_for(gen.__anext__(), timeout=5)
        finally:
            await gen.aclose()

    second = asyncio.run(main())
    assert '"request_id": 42' in second
    assert len(_subscribers) == 0  # generator close unsubscribed cleanly


def test_operator_list_shows_live_dot(client: TestClient, operator_user: User) -> None:
    _login(client, operator_user)
    html = client.get("/requests", headers={"Accept": "text/html"}).text
    assert 'new EventSource("/events")' in html
    assert "Live" in html
