"""Analytics are SQL aggregates over a bounded range (operator-only)."""

from datetime import UTC, datetime

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.episode import Episode, EpisodeQuality
from app.models.request import DatasetRequest, RequestStatus
from app.models.user import User


def _login(client: TestClient, user: User) -> None:
    assert (
        client.post("/login", data={"email": user.email, "password": "password123"}).status_code
        == 200
    )


def _episode(
    db_session: Session,
    episode_id: str,
    robot: str,
    task: str,
    day: int,
    quality: EpisodeQuality = EpisodeQuality.GOOD,
) -> None:
    db_session.add(
        Episode(
            episode_id=episode_id,
            robot_id=robot,
            task_name=task,
            recorded_at=datetime(2026, 9, day, 10, 0, tzinfo=UTC),
            duration_seconds=60,
            operator_name="Tester",
            quality=quality,
        )
    )
    db_session.flush()


def _request(
    db_session: Session,
    client_user: User,
    req_status: RequestStatus,
    submitted_day: int,
    delivered_hours_later: float | None = None,
) -> None:
    submitted = datetime(2026, 9, submitted_day, 8, 0, tzinfo=UTC)
    db_session.add(
        DatasetRequest(
            client_id=client_user.id,
            task_name="pick cup",
            episodes_requested=1,
            deadline=datetime(2026, 12, 31).date(),
            notes=None,
            status=req_status,
            submitted_at=submitted,
            delivered_at=(
                submitted + _hours(delivered_hours_later)
                if delivered_hours_later is not None
                else None
            ),
        )
    )
    db_session.flush()


def _hours(value: float) -> object:
    from datetime import timedelta

    return timedelta(hours=value)


def _seed(db_session: Session, client_user: User) -> None:
    _episode(db_session, "EP-N1", "arm-01", "pick cup", 10)
    _episode(db_session, "EP-N2", "arm-01", "pick cup", 10)
    _episode(db_session, "EP-N3", "arm-02", "open drawer", 11, EpisodeQuality.USABLE)
    _episode(db_session, "EP-N4", "arm-01", "open drawer", 11, EpisodeQuality.BAD)
    _request(db_session, client_user, RequestStatus.SUBMITTED, 10)
    _request(db_session, client_user, RequestStatus.IN_PROGRESS, 11)
    _request(db_session, client_user, RequestStatus.DELIVERED, 10, delivered_hours_later=48)
    _request(db_session, client_user, RequestStatus.ACCEPTED, 11, delivered_hours_later=24)


def test_analytics_aggregates_in_sql(
    client: TestClient, db_session: Session, client_user: User, operator_user: User
) -> None:
    _seed(db_session, client_user)
    _login(client, operator_user)

    response = client.get("/analytics", params={"start": "2026-09-01", "end": "2026-09-30"})
    assert response.status_code == 200, response.text
    body = response.json()

    per_day = {
        (row["day"], row["robot_id"]): row["count"]
        for row in body["episodes_per_day_robot"]
    }
    assert per_day[("2026-09-10", "arm-01")] == 2
    assert per_day[("2026-09-11", "arm-02")] == 1
    assert per_day[("2026-09-11", "arm-01")] == 1

    by_status = {row["status"]: row["count"] for row in body["requests_by_status"]}
    assert by_status == {"submitted": 1, "in_progress": 1, "delivered": 1, "accepted": 1}

    # Median of 48h and 24h fulfilments = 36h = 129600s.
    assert body["median_submitted_to_delivered_seconds"] == 129600.0

    top = body["top_tasks_by_good_episodes"]
    assert top[0] == {"task_name": "pick cup", "count": 2}
    assert all(row["task_name"] != "open drawer" or row["count"] == 0 for row in top)


def test_analytics_empty_range_has_null_median(
    client: TestClient, operator_user: User
) -> None:
    _login(client, operator_user)
    body = client.get("/analytics", params={"start": "2020-01-01", "end": "2020-01-31"}).json()
    assert body["episodes_per_day_robot"] == []
    assert body["requests_by_status"] == []
    assert body["median_submitted_to_delivered_seconds"] is None
    assert body["top_tasks_by_good_episodes"] == []


def test_analytics_rejects_bad_range(client: TestClient, operator_user: User) -> None:
    _login(client, operator_user)
    assert (
        client.get("/analytics", params={"start": "2026-10-01", "end": "2026-09-01"}).status_code
        == 422
    )
    assert (
        client.get(
            "/analytics", params={"start": "2020-01-01", "end": "2022-01-01"}
        ).status_code
        == 422
    )


def test_analytics_forbidden_for_clients(client: TestClient, client_user: User) -> None:
    _login(client, client_user)
    response = client.get("/analytics", params={"start": "2026-09-01", "end": "2026-09-30"})
    assert response.status_code == status.HTTP_403_FORBIDDEN
