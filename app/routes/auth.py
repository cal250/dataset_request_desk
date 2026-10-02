from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, create_session_token, get_current_user
from app.config import get_settings
from app.db import get_db_session
from app.models.user import User
from app.schemas.user import UserOut
from app.security import verify_password

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(
    response: Response,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_db_session)],
) -> User:
    """Verify credentials and set a signed, HTTP-only session cookie."""
    normalized = email.strip().lower()
    user = session.scalar(select(User).where(User.email == normalized))
    # Generic failure: never reveal whether the email exists or the account is off.
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(user.id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=get_settings().session_https_only,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
