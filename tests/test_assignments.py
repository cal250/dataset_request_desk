"""Assignment rules: eligibility, ownership, race safety."""

from datetime import UTC, datetime

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.assignment import Assignment
from app.models.episode import Episode, EpisodeQuality
from app.models.user import User

_counter = {"n": 0}


def _login(client: TestClient, user: User) -> TestClient:
    assert (
        client.post("/login", data={"email": user.email, "password": "password123"}).status_code
        == 200
    )
    return client


def _episode(db_session, quality: EpisodeQuality = EpisodeQuality.GOOD) -> Episode:
    _counter["n"] += 1
    episode = Episode(
        episode_id=f"EP-A{_counter['n']}",
        robot_id="arm-01",
        task_name="pick cup",
        recorded_at=datetime.now(UTC),
        duration_seconds=60,
        operator_name="Tester",
        quality=quality,
    )
    db_session.add(episode)
    db_session.flush()
    return episode


def _request(client: TestClient, n: int = 1) -> int:
    response = client.post(
        "/requests",
        json={"task_name": "pick cup", "episodes_requested": n, "deadline": "2026-12-31"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_operator_assigns_eligible_episode(
    client: TestClient, db_session, client_user: User, operator_user: User
) -> None:
    _login(client, client_user)
    rid = _request(client)
    episode = _episode(db_session)

    _login(client, operator_user)
    response = client.post(f"/requests/{rid}/assignments", json={"episode_id": episode.id})
    assert response.status_code == 201, response.text
    assert response.json()["request_id"] == rid

    listing = client.get(f"/requests/{rid}/assignments")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_bad_episode_cannot_be_assigned(
    client: TestClient, db_session, client_user: User, operator_user: User
) -> None:
    _login(client, client_user)
    rid = _request(client)
    bad = _episode(db_session, EpisodeQuality.BAD)

    _login(client, operator_user)
    response = client.post(f"/requests/{rid}/assignments", json={"episode_id": bad.id})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_episode_cannot_be_assigned_twice(
    client: TestClient, db_session, client_user: User, operator_user: User
) -> None:
    _login(client, client_user)
    first = _request(client)
    second = _request(client)
    episode = _episode(db_session)

    _login(client, operator_user)
    assert (
        client.post(f"/requests/{first}/assignments", json={"episode_id": episode.id}).status_code
        == 201
    )
    response = client.post(f"/requests/{second}/assignments", json={"episode_id": episode.id})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert db_session.scalar(select(Assignment).where(Assignment.episode_id == episode.id))


def test_client_cannot_assign(
    client: TestClient, db_session, client_user: User
) -> None:
    _login(client, client_user)
    rid = _request(client)
    episode = _episode(db_session)
    response = client.post(f"/requests/{rid}/assignments", json={"episode_id": episode.id})
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_assign_to_delivered_is_frozen(
    client: TestClient, db_session, client_user: User, operator_user: User
) -> None:
    _login(client, client_user)
    rid = _request(client, n=1)

    _login(client, operator_user)
    first = _episode(db_session)
    assert (
        client.post(f"/requests/{rid}/assignments", json={"episode_id": first.id}).status_code
        == 201
    )
    client.post(f"/requests/{rid}/transitions", json={"status": "in_progress"})
    client.post(f"/requests/{rid}/transitions", json={"status": "delivered"})

    extra = _episode(db_session)
    response = client.post(f"/requests/{rid}/assignments", json={"episode_id": extra.id})
    assert response.status_code == status.HTTP_409_CONFLICT


def test_client_lists_own_assignments_but_not_others(
    client: TestClient, db_session, client_user: User, operator_user: User
) -> None:
    from app.models.user import UserRole
    from tests.conftest import _make_user

    _login(client, client_user)
    rid = _request(client)
    _login(client, operator_user)
    episode = _episode(db_session)
    client.post(f"/requests/{rid}/assignments", json={"episode_id": episode.id})

    _login(client, client_user)
    assert len(client.get(f"/requests/{rid}/assignments").json()) == 1

    other = _make_user(db_session, UserRole.CLIENT)
    _login(client, other)
    assert client.get(f"/requests/{rid}/assignments").status_code == 404
