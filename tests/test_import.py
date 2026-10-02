"""Import fidelity: messy rows are reported, reruns never duplicate."""

import io

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.episode import Episode
from app.models.user import User
from app.services.import_episodes import import_csv

HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality"


def _login(client: TestClient, user: User) -> TestClient:
    assert (
        client.post("/login", data={"email": user.email, "password": "password123"}).status_code
        == 200
    )
    return client


def _run(db_session, text: str):
    return import_csv(db_session, io.StringIO(HEADER + "\n" + text))


def test_normalization_is_canonical(db_session) -> None:
    report = _run(
        db_session,
        " ep-00099 ,arm-01,  Pick Cup ,2026-08-13T23:51:00,111,Eric,USABLE\n",
    )
    assert report.inserted == 1
    episode = db_session.scalar(select(Episode).where(Episode.episode_id == "EP-00099"))
    assert episode.task_name == "pick cup"
    assert episode.quality.value == "usable"
    assert episode.robot_id == "arm-01"


def test_invalid_rows_are_reported_with_reasons(db_session) -> None:
    report = _run(
        db_session,
        "\n".join(
            [
                ",humanoid-01,fold towel,2026-08-13T06:59:00,82,Patrick,good",
                "EP-BAD1,arm-01,stack blocks,2026-08-13T08:55:00,66,Jeanne,excellent",
                "EP-BAD2,arm-99,place cup on shelf,2026-09-09T12:33:00,88,Eric,usable",
                "EP-BAD3,arm-02,pour water,not a date,71,Aline,good",
                "EP-BAD4,arm-03,open drawer,14/08/2026 09:15,34,Kevin,good",
                "EP-BAD5,arm-01,wipe table,2026-08-11T18:10:00,45.5,Patrick,good",
                "EP-BAD6,arm-01,fold towel,2026-08-22T09:00:00,N/A,Aline,good",
                "EP-BAD7,arm-01,fold towel,2026-08-22T09:05:00,999999,Aline,good",
                "EP-BAD8,,place cup on shelf,2026-08-13T09:19:00,103,Jeanne,usable",
                "EP-BAD9,arm-02,open drawer,2026-08-20T10:00:00,30",
            ]
        )
        + "\n",
    )
    assert report.inserted == 0
    assert report.skipped_invalid == 10
    assert len(report.errors) == 10
    assert all(error.row >= 2 and error.reason for error in report.errors)


def test_duplicate_and_conflict_policy(db_session) -> None:
    row = "EP-DUP1,arm-01,pick cup,2026-08-30T10:25:00,102,Diane,good\n"
    assert _run(db_session, row).inserted == 1

    rerun = _run(db_session, row)
    assert rerun.inserted == 0
    assert rerun.already_exists == 1

    conflict = _run(
        db_session, "EP-DUP1,arm-01,pick cup,2026-08-30T10:25:00,999,Diane,good\n"
    )
    assert conflict.skipped_conflict == 1
    assert "different data" in conflict.errors[0].reason
    # Stored metadata is untouched by the conflict.
    assert (
        db_session.scalar(select(Episode).where(Episode.episode_id == "EP-DUP1"))
        .duration_seconds
        == 102
    )


def test_seed_file_imports_twice_without_duplicates(db_session) -> None:
    from pathlib import Path

    seed = Path("/app/seed/episodes.csv")
    if not seed.exists():  # host-side checkout without the container mount
        seed = Path("seed/episodes.csv")
    with seed.open(encoding="utf-8-sig", newline="") as handle:
        first = import_csv(db_session, handle)
    assert first.inserted > 100, first
    total = db_session.scalar(select(func.count()).select_from(Episode))

    with seed.open(encoding="utf-8-sig", newline="") as handle:
        second = import_csv(db_session, handle)
    assert second.inserted == 0
    # The seed file itself contains 2 exact intra-file duplicates, counted as
    # already_exists on the first pass and again against the DB on the rerun.
    assert second.already_exists == first.inserted + first.already_exists
    assert second.skipped_invalid + second.skipped_conflict > 0
    assert db_session.scalar(select(func.count()).select_from(Episode)) == total


def test_import_endpoint_requires_operator(
    client: TestClient, client_user: User, operator_user: User
) -> None:
    _login(client, client_user)
    response = client.post(
        "/episodes/import",
        files={"file": ("ep.csv", HEADER + "\n", "text/csv")},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    _login(client, operator_user)
    response = client.post(
        "/episodes/import",
        files={
            "file": (
                "ep.csv",
                HEADER + "\nEP-EP1,arm-01,pick cup,2026-08-30T10:25:00,60,Aline,good\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["inserted"] == 1


def test_episode_list_filters(
    client: TestClient, db_session, operator_user: User, client_user: User
) -> None:
    _run(
        db_session,
        "EP-F1,arm-01,pick cup,2026-08-30T10:25:00,60,Aline,good\n"
        "EP-F2,arm-01,pick cup,2026-08-30T11:25:00,60,Aline,bad\n",
    )
    _login(client, operator_user)
    assert len(client.get("/episodes", params={"task_name": "pick cup"}).json()) == 2
    assert len(client.get("/episodes", params={"quality": "good"}).json()) == 1

    _login(client, client_user)
    assert client.get("/episodes").status_code == status.HTTP_403_FORBIDDEN
