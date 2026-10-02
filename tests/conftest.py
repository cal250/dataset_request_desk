"""Shared pytest foundation: isolated Postgres test DB, rollback, role fixtures."""

import os
from collections.abc import Generator
from urllib.parse import urlparse, urlunparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  # Register all models on Base.metadata.
from app.db import Base, get_db_session
from app.main import app
from app.models.user import User, UserRole
from app.security import hash_password


def _resolve_test_database_url() -> str:
    """Derive a `_test` database URL from the runtime DATABASE_URL.

    Keeps the host/credentials (works both inside Compose where the host is
    `db` and on a developer host where it is `localhost`), only swapping the
    database name so tests never touch dev data.
    """
    if os.getenv("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    base = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://desk:desk-local-password@db:5432/dataset_request_desk",
    )
    parsed = urlparse(base)
    db_name = parsed.path.lstrip("/") or "dataset_request_desk"
    if not db_name.endswith("_test"):
        db_name = f"{db_name}_test"
    return urlunparse(parsed._replace(path=f"/{db_name}"))


TEST_DATABASE_URL = _resolve_test_database_url()


def _ensure_test_database_exists() -> None:
    """Create the test database on the Postgres server if it is missing."""
    parsed = urlparse(TEST_DATABASE_URL)
    db_name = parsed.path.lstrip("/")
    # Connect to the maintenance `postgres` database to issue CREATE DATABASE.
    maintenance_url = urlunparse(parsed._replace(path="/postgres"))
    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    engine.dispose()


@pytest.fixture(scope="session")
def _test_engine():
    _ensure_test_database_exists()
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    # Fresh schema for the test session; models are the single source of truth
    # until later migrations exist (then switch this to `alembic upgrade head`).
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(_test_engine) -> Generator[Session, None, None]:
    """Function-scoped session inside a rolled-back transaction (test isolation)."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    TestingSession = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with the app's DB dependency pointed at the isolated session."""

    def _override_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


_counter = {"n": 0}


def _make_user(session: Session, role: UserRole) -> User:
    _counter["n"] += 1
    user = User(
        email=f"{role.value}{_counter['n']}@example.com",
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
        name=f"Test {role.value} {_counter['n']}",
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture()
def client_user(db_session: Session) -> User:
    return _make_user(db_session, UserRole.CLIENT)


@pytest.fixture()
def operator_user(db_session: Session) -> User:
    return _make_user(db_session, UserRole.OPERATOR)


@pytest.fixture()
def admin_user(db_session: Session) -> User:
    return _make_user(db_session, UserRole.ADMIN)
