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


def test_json_list_still_returns_json(client: TestClient, client_user: User) -> None:
    _login(client, client_user)
    response = client.get("/requests")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
