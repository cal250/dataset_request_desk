from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_operator_user
from app.db import get_db_session
from app.models.assignment import Assignment
from app.models.episode import Episode
from app.models.request import DatasetRequest
from app.models.user import User
from app.schemas.assignment import AssignmentCreate, AssignmentOut
from app.services.assignments import assign_episode
from app.services.requests import get_request_or_404

router = APIRouter(tags=["assignments"])


def _episode_or_404(session: Session, episode_id: int) -> Episode:
    episode = session.scalar(select(Episode).where(Episode.id == episode_id))
    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return episode


@router.post(
    "/requests/{request_id}/assignments",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    request_id: int,
    payload: AssignmentCreate,
    actor: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> Assignment:
    request = session.scalar(select(DatasetRequest).where(DatasetRequest.id == request_id))
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    episode = _episode_or_404(session, payload.episode_id)
    return assign_episode(session, request, episode, actor)


@router.post("/requests/{request_id}/assignments/form", status_code=status.HTTP_303_SEE_OTHER)
def create_assignment_form(
    request_id: int,
    request: Request,
    actor: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
    episode_id: Annotated[int, Form()],
):
    from app.routes.requests import _detail_page

    row = session.scalar(select(DatasetRequest).where(DatasetRequest.id == request_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    episode = _episode_or_404(session, episode_id)
    try:
        assign_episode(session, row, episode, actor)
    except HTTPException as exc:
        session.rollback()
        return _detail_page(request, actor, session, row, error=str(exc.detail))
    return RedirectResponse(
        url=f"/requests/{request_id}?toast=Episode+assigned",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/requests/{request_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(
    request_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[Assignment]:
    """Operators see any request's assignments; clients only their own."""
    request = get_request_or_404(session, user, request_id)
    return list(
        session.scalars(
            select(Assignment).where(Assignment.request_id == request.id).order_by(Assignment.id)
        ).all()
    )
