"""Admin user management: create, role change, deactivation (admin-only)."""

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.user import User, UserRole


def _login(client: TestClient, user: User) -> None:
    assert (
        client.post("/login", data={"email": user.email, "password": "password123"}).status_code
        == 200
    )


def test_admin_creates_user(
    client: TestClient, db_session, admin_user: User
) -> None:
    _login(client, admin_user)
    response = client.post(
        "/users",
        data={
            "email": "new-op@example.com",
            "name": "New Op",
            "role": "operator",
            "password": "password123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    created = db_session.scalar(select(User).where(User.email == "new-op@example.com"))
    assert created is not None
    assert created.role == UserRole.OPERATOR
    assert created.password_hash != "password123"  # Argon2 hash, never plaintext


def test_admin_changes_role_and_deactivates(
    client: TestClient, db_session, admin_user: User, client_user: User
) -> None:
    _login(client, admin_user)
    assert (
        client.post(
            f"/users/{client_user.id}/role", data={"role": "operator"}, follow_redirects=False
        ).status_code
        == 303
    )
    db_session.refresh(client_user)
    assert client_user.role == UserRole.OPERATOR

    assert (
        client.post(f"/users/{client_user.id}/deactivate", follow_redirects=False).status_code
        == 303
    )
    db_session.refresh(client_user)
    assert client_user.is_active is False


def test_admin_cannot_deactivate_self(client: TestClient, admin_user: User) -> None:
    _login(client, admin_user)
    response = client.post(f"/users/{admin_user.id}/deactivate", follow_redirects=False)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_non_admin_blocked(client: TestClient, operator_user: User, client_user: User) -> None:
    _login(client, operator_user)
    assert client.get("/users").status_code == status.HTTP_403_FORBIDDEN
    assert (
        client.post(
            "/users",
            data={
                "email": "x@example.com",
                "name": "X",
                "role": "client",
                "password": "password123",
            },
        ).status_code
        == status.HTTP_403_FORBIDDEN
    )
    _login(client, client_user)
    assert (
        client.post(
            f"/users/{operator_user.id}/deactivate", follow_redirects=False
        ).status_code
        == status.HTTP_403_FORBIDDEN
    )
