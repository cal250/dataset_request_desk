from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, create_session_token, get_current_user
from app.config import get_settings
from app.db import get_db_session
from app.models.user import User
from app.schemas.user import UserOut
from app.security import verify_password
from app.ui import templates, wants_html

router = APIRouter(tags=["auth"])


def _session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(user.id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=get_settings().session_https_only,
        samesite="lax",
        path="/",
    )


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None, "email": ""})


@router.post("/login")
def login(
    request: Request,
    response: Response,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_db_session)],
):
    """Verify credentials; JSON for API clients, redirect for browser forms."""
    normalized = email.strip().lower()
    user = session.scalar(select(User).where(User.email == normalized))
    # Generic failure: never reveal whether the email exists or the account is off.
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        if wants_html(request):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid email or password", "email": normalized},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if wants_html(request):
        redirect = RedirectResponse(url="/requests", status_code=status.HTTP_303_SEE_OTHER)
        _session_cookie(redirect, user)
        return redirect
    _session_cookie(response, user)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    if wants_html(request):
        redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        redirect.delete_cookie(key=SESSION_COOKIE, path="/")
        return redirect
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return None


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
