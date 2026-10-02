"""Browser pages render for the right roles; JSON API behavior is unchanged."""

from fastapi.testclient import TestClient

from app.models.user import User

HTML = {"Accept": "text/html"}


def _login(client: TestClient, user: User) -> None:
    assert (
        client.post("/login", data={"email": user.email, "password": "password123"}).status_code
        == 200
    )


def test_login_page_renders() -> None:
    from app.main import app

    with TestClient(app) as anonymous:
        response = anonymous.get("/login", headers=HTML)
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_root_redirects_to_login_or_requests() -> None:
    from app.main import app

    with TestClient(app) as anonymous:
        assert anonymous.get("/", follow_redirects=False).status_code == 303


def test_client_request_pages(client: TestClient, client_user: User) -> None:
    _login(client, client_user)
    listing = client.get("/requests", headers=HTML)
    assert listing.status_code == 200
    assert "My requests" in listing.text

    form = client.get("/requests/new", headers=HTML)
    assert form.status_code == 200
    assert "Create request" in form.text

    created = client.post(
        "/requests/form",
        data={
            "task_name": "pick cup",
            "episodes_requested": "1",
            "deadline": "2026-12-31",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303, created.text
    detail = client.get(created.headers["location"], headers=HTML)
    assert detail.status_code == 200
    assert "pick cup" in detail.text


def test_operator_pages(client: TestClient, operator_user: User) -> None:
    _login(client, operator_user)
    assert client.get("/episodes", headers=HTML).status_code == 200
    analytics = client.get("/analytics", headers=HTML)
    assert analytics.status_code == 200
    assert "Episodes per day" in analytics.text
    # ...but the client creation form is client-only.
    assert client.get("/requests/new", headers=HTML).status_code == 403


def test_client_blocked_from_operator_and_admin_pages(
    client: TestClient, client_user: User
) -> None:
    _login(client, client_user)
    assert client.get("/episodes", headers=HTML).status_code == 403
    assert client.get("/analytics", headers=HTML).status_code == 403
    assert client.get("/users", headers=HTML).status_code == 403
    # /requests/new is the client creation form: allowed for clients...
    assert client.get("/requests/new", headers=HTML).status_code == 200


def test_htmx_partial_request_returns_filtered_html(
    client: TestClient, db_session, operator_user: User
) -> None:
    """HTMX sends HX-Request with Accept */*; the swap needs HTML, not JSON."""
    from datetime import UTC, datetime

    from app.models.episode import Episode, EpisodeQuality

    for i, quality in enumerate((EpisodeQuality.GOOD, EpisodeQuality.BAD)):
        db_session.add(
            Episode(
                episode_id=f"EP-H{i}",
                robot_id="arm-01",
                task_name="pick cup",
                recorded_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
                duration_seconds=60,
                operator_name="Tester",
                quality=quality,
            )
        )
    db_session.flush()
    _login(client, operator_user)
    response = client.get(
        "/episodes", params={"task_name": "pick cup"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert 'id="episodes-result"' in response.text
    # Counter travels inside the swapped region, so it stays truthful.
    assert "Showing 1–2 of 2." in response.text


def test_detail_shows_only_permitted_actions(
    client: TestClient, client_user: User, operator_user: User
) -> None:
    """Clients must not see operator buttons (and vice versa)."""
    _login(client, client_user)
    response = client.post(
        "/requests",
        json={"task_name": "pick cup", "episodes_requested": 1, "deadline": "2026-12-31"},
    )
    rid = response.json()["id"]

    mine = client.get(f"/requests/{rid}", headers=HTML).text
    assert "Start work" not in mine
    assert "Mark delivered" not in mine

    _login(client, operator_user)
    theirs = client.get(f"/requests/{rid}", headers=HTML).text
    assert "Start work" in theirs
    assert "Accept delivery" not in theirs


def test_form_transition_redirects_and_failed_repeat_rerenders(
    client: TestClient, db_session, client_user: User, operator_user: User
) -> None:
    """The browser form path must 303 on success and never 500 on failure."""
    from datetime import UTC, datetime

    from app.models.episode import Episode, EpisodeQuality

    _login(client, client_user)
    rid = client.post(
        "/requests",
        json={"task_name": "pick cup", "episodes_requested": 1, "deadline": "2026-12-31"},
    ).json()["id"]

    _login(client, operator_user)
    first = client.post(
        f"/requests/{rid}/transitions/form",
        data={"target_status": "in_progress"},
        follow_redirects=False,
    )
    assert first.status_code == 303, first.text

    episode = Episode(
        episode_id="EP-FORM1",
        robot_id="arm-01",
        task_name="pick cup",
        recorded_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
        duration_seconds=60,
        operator_name="Tester",
        quality=EpisodeQuality.GOOD,
    )
    db_session.add(episode)
    db_session.flush()
    client.post(f"/requests/{rid}/assignments", json={"episode_id": episode.id})
    delivered = client.post(
        f"/requests/{rid}/transitions/form",
        data={"target_status": "delivered"},
        follow_redirects=False,
    )
    assert delivered.status_code == 303, delivered.text

    repeat = client.post(
        f"/requests/{rid}/transitions/form", data={"target_status": "delivered"}
    )
    assert repeat.status_code == 200
    assert "Cannot move from delivered to delivered" in repeat.text


def test_json_list_still_returns_json(client: TestClient, client_user: User) -> None:
    _login(client, client_user)
    response = client.get("/requests")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
