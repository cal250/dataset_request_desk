from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
