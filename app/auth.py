"""Signed-cookie session auth + server-side role guards."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db_session
from app.models.user import User, UserRole

SESSION_COOKIE = "desk_session"
SESSION_SALT = "desk-session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 3600


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt=SESSION_SALT)


def create_session_token(user_id: int) -> str:
    return _signer().dumps({"uid": user_id})


def read_session_user_id(token: str) -> int | None:
    try:
        data = _signer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return uid if isinstance(uid, int) else None


def ensure_role(user: User, *allowed: UserRole) -> User:
    """Pure role check so guards are unit-testable without HTTP."""
    if user.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user


def get_current_user(
    request: Request, session: Annotated[Session, Depends(get_db_session)]
) -> User:
    """Resolve the signed-cookie user against live DB state.

    Deactivation takes effect immediately; inactive/unknown users get a
    generic 401 so we never leak which emails exist.
    """
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session_user_id(token) if token else None
    user = session.scalar(select(User).where(User.id == user_id)) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    request.state.user_id = user.id
    return user


def get_operator_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Operators and admins (admins inherit all operator powers)."""
    return ensure_role(user, UserRole.OPERATOR, UserRole.ADMIN)


def get_admin_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    return ensure_role(user, UserRole.ADMIN)
