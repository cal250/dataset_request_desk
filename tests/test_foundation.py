"""Foundation checks: fixtures work and tests are isolated from each other."""

from sqlalchemy import select

from app.models.user import User


def test_role_fixtures_create_users(db_session, client_user, operator_user, admin_user) -> None:
    assert db_session.scalar(select(User).where(User.email == client_user.email)) is not None
    assert client_user.role.value == "client"
    assert operator_user.role.value == "operator"
    assert admin_user.role.value == "admin"


def test_db_isolation_between_tests(db_session) -> None:
    # The users created in other tests are rolled back; this starts empty.
    assert db_session.scalar(select(User).order_by(User.id).limit(1)) is None
