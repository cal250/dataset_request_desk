import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.auth import ensure_role
from app.models.user import User, UserRole


def test_login_success_sets_cookie_and_me(client: TestClient, client_user: User) -> None:
    response = client.post(
        "/login", data={"email": client_user.email, "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == client_user.email
    assert "desk_session" in response.cookies

    me = client.get("/me")
    assert me.status_code == 200
    assert me.json()["role"] == "client"


def test_login_email_is_case_insensitive(client: TestClient, client_user: User) -> None:
    response = client.post(
        "/login",
        data={"email": f"  {client_user.email.upper()}  ", "password": "password123"},
    )
    assert response.status_code == 200


def test_login_wrong_password_is_401(client: TestClient, client_user: User) -> None:
    response = client.post(
        "/login", data={"email": client_user.email, "password": "wrong-password"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_unknown_email_is_401(client: TestClient) -> None:
    response = client.post(
        "/login", data={"email": "nobody@example.com", "password": "password123"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_me_without_cookie_is_401(client: TestClient) -> None:
    assert client.get("/me").status_code == status.HTTP_401_UNAUTHORIZED


def test_inactive_user_is_blocked(client: TestClient, db_session, client_user: User) -> None:
    client_user.is_active = False
    db_session.flush()

    response = client.post(
        "/login", data={"email": client_user.email, "password": "password123"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout_clears_session(client: TestClient, client_user: User) -> None:
    client.post("/login", data={"email": client_user.email, "password": "password123"})
    assert client.get("/me").status_code == 200

    assert client.post("/logout").status_code == 204
    assert client.get("/me").status_code == status.HTTP_401_UNAUTHORIZED


def test_operator_guard_allows_operator_and_admin(operator_user: User, admin_user: User) -> None:
    assert ensure_role(operator_user, UserRole.OPERATOR, UserRole.ADMIN) is operator_user
    assert ensure_role(admin_user, UserRole.OPERATOR, UserRole.ADMIN) is admin_user


def test_client_is_forbidden_from_operator_actions(client_user: User) -> None:
    with pytest.raises(Exception) as exc_info:
        ensure_role(client_user, UserRole.OPERATOR, UserRole.ADMIN)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
