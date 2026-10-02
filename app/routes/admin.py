from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_admin_user
from app.db import get_db_session
from app.models.user import User, UserRole
from app.security import hash_password
from app.ui import templates

router = APIRouter(tags=["users"])


@router.get("/users")
def users_page(
    request: Request,
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    users = list(session.scalars(select(User).order_by(User.id)).all())
    return templates.TemplateResponse(
        request, "users.html", {"user": admin, "active": "users", "users": users}
    )


@router.post("/users", status_code=status.HTTP_303_SEE_OTHER)
def create_user(
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[Session, Depends(get_db_session)],
    email: Annotated[str, Form()],
    name: Annotated[str, Form()],
    role: Annotated[UserRole, Form()],
    password: Annotated[str, Form(min_length=8)],
):
    normalized = email.strip().lower()
    if session.scalar(select(User).where(User.email == normalized)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is taken")
    session.add(
        User(
            email=normalized,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            name=name.strip(),
        )
    )
    session.commit()
    return RedirectResponse(url="/users?toast=User+created", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/role", status_code=status.HTTP_303_SEE_OTHER)
def change_role(
    user_id: int,
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[Session, Depends(get_db_session)],
    role: Annotated[UserRole, Form()],
):
    target = session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    target.role = role
    session.commit()
    return RedirectResponse(url="/users?toast=Role+updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/deactivate", status_code=status.HTTP_303_SEE_OTHER)
def deactivate(
    user_id: int,
    admin: Annotated[User, Depends(get_admin_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    target = session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="You cannot deactivate your own account",
        )
    target.is_active = False
    session.commit()
    return RedirectResponse(
        url="/users?toast=User+deactivated", status_code=status.HTTP_303_SEE_OTHER
    )
