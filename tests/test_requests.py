from datetime import UTC, datetime

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.assignment import Assignment
from app.models.episode import Episode, EpisodeQuality
from app.models.request import StatusHistory
from app.models.user import User

_counter = {"n": 0}


def _login(client: TestClient, user: User, password: str = "password123") -> TestClient:
    response = client.post("/login", data={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return client


def _create(client: TestClient, **overrides) -> dict:
    payload = {
        "task_name": "pick cup",
        "episodes_requested": 2,
        "deadline": "2026-12-31",
        "notes": "test",
    }
    payload.update(overrides)
    response = client.post("/requests", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _move(client: TestClient, request_id: int, target: str):
    return client.post(f"/requests/{request_id}/transitions", json={"status": target})


def _make_episode(db_session, tag: str) -> Episode:
    _counter["n"] += 1
    episode = Episode(
        episode_id=f"EP-T{tag}-{_counter['n']}",
        robot_id="arm-01",
        task_name="pick cup",
        recorded_at=datetime.now(UTC),
        duration_seconds=60,
        operator_name="Tester",
        quality=EpisodeQuality.GOOD,
    )
    db_session.add(episode)
    db_session.flush()
    return episode


def _assign(db_session, request_id: int, episode: Episode, by: User) -> None:
    db_session.add(
        Assignment(
            request_id=request_id,
            episode_id=episode.id,
            assigned_by=by.id,
            assigned_at=datetime.now(UTC),
        )
    )
    db_session.flush()


def test_client_creates_request_and_history(client: TestClient, db_session, client_user) -> None:
    _login(client, client_user)
    body = _create(client)

    assert body["status"] == "submitted"
    assert body["client_id"] == client_user.id
    history = db_session.scalars(select(StatusHistory)).all()
    assert len(history) == 1
    assert history[0].from_status is None
    assert history[0].to_status.value == "submitted"
    assert history[0].changed_by == client_user.id


def test_operator_cannot_create_requests(client: TestClient, operator_user) -> None:
    _login(client, operator_user)
    response = client.post(
        "/requests",
        json={"task_name": "pick cup", "episodes_requested": 1, "deadline": "2026-12-31"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_unauthenticated_create_is_401(client: TestClient) -> None:
    response = client.post(
        "/requests",
        json={"task_name": "pick cup", "episodes_requested": 1, "deadline": "2026-12-31"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_client_lists_only_own(
    client: TestClient, db_session, client_user, operator_user
) -> None:
    _login(client, client_user)
    _create(client)
    assert len(client.get("/requests").json()) == 1

    # Another client's request exists but stays invisible (plus operator sees all).
    from app.models.user import UserRole
    from tests.conftest import _make_user

    other = _make_user(db_session, UserRole.CLIENT)
    _login(client, other)
    _create(client, task_name="other task")
    assert len(client.get("/requests").json()) == 1

    _login(client, operator_user)
    assert len(client.get("/requests").json()) == 2


def test_client_cannot_view_another_clients_request(
    client: TestClient, db_session, client_user
) -> None:
    from app.models.user import UserRole
    from tests.conftest import _make_user

    _login(client, client_user)
    mine = _create(client)["id"]

    other = _make_user(db_session, UserRole.CLIENT)
    _login(client, other)
    assert client.get(f"/requests/{mine}").status_code == status.HTTP_404_NOT_FOUND


def test_operator_moves_submitted_to_in_progress(
    client: TestClient, db_session, client_user, operator_user
) -> None:
    _login(client, client_user)
    rid = _create(client)["id"]

    _login(client, operator_user)
    response = _move(client, rid, "in_progress")
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert db_session.scalar(select(func.count()).select_from(StatusHistory)) == 2


def test_client_cannot_do_operator_transition(
    client: TestClient, client_user
) -> None:
    _login(client, client_user)
    rid = _create(client)["id"]
    assert _move(client, rid, "in_progress").status_code == status.HTTP_403_FORBIDDEN


def test_invalid_pair_is_422(client: TestClient, client_user, operator_user) -> None:
    _login(client, client_user)
    rid = _create(client)["id"]

    _login(client, operator_user)
    response = _move(client, rid, "delivered")  # must go via in_progress first
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_delivery_needs_enough_assignments(
    client: TestClient, db_session, client_user, operator_user
) -> None:
    _login(client, client_user)
    rid = _create(client, episodes_requested=2)["id"]

    _login(client, operator_user)
    assert _move(client, rid, "in_progress").status_code == 200
    assert _move(client, rid, "delivered").status_code == status.HTTP_409_CONFLICT

    _assign(db_session, rid, _make_episode(db_session, "a"), operator_user)
    assert _move(client, rid, "delivered").status_code == status.HTTP_409_CONFLICT

    _assign(db_session, rid, _make_episode(db_session, "b"), operator_user)
    delivered = _move(client, rid, "delivered")
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["delivered_at"] is not None


def test_owner_accepts_operator_cannot(
    client: TestClient, db_session, client_user, operator_user
) -> None:
    _login(client, client_user)
    rid = _create(client, episodes_requested=1)["id"]

    _login(client, operator_user)
    assert _move(client, rid, "in_progress").status_code == 200
    _assign(db_session, rid, _make_episode(db_session, "c"), operator_user)
    assert _move(client, rid, "delivered").status_code == 200

    # Operator (and admin power) cannot decide for the client.
    assert _move(client, rid, "accepted").status_code == status.HTTP_403_FORBIDDEN

    _login(client, client_user)
    accepted = _move(client, rid, "accepted")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    # Terminal: nothing leaves accepted.
    assert _move(client, rid, "in_progress").status_code in (403, 422)


def test_rejected_returns_to_in_progress(
    client: TestClient, db_session, client_user, operator_user
) -> None:
    _login(client, client_user)
    rid = _create(client, episodes_requested=1)["id"]

    _login(client, operator_user)
    _move(client, rid, "in_progress")
    _assign(db_session, rid, _make_episode(db_session, "d"), operator_user)
    _move(client, rid, "delivered")

    _login(client, client_user)
    assert _move(client, rid, "rejected").status_code == 200

    _login(client, operator_user)
    rework = _move(client, rid, "in_progress")
    assert rework.status_code == 200
