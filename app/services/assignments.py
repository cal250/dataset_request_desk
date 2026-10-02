"""Episode-to-request assignment (owns eligibility + race safety)."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import ensure_role
from app.models.assignment import Assignment
from app.models.episode import Episode, EpisodeQuality
from app.models.request import DatasetRequest, RequestStatus
from app.models.user import User, UserRole

# Delivered/accepted datasets are frozen; rejected returns to the pool.
ASSIGNABLE_STATUSES = frozenset(
    {RequestStatus.SUBMITTED, RequestStatus.IN_PROGRESS, RequestStatus.REJECTED}
)


def assign_episode(
    session: Session, request: DatasetRequest, episode: Episode, actor: User
) -> Assignment:
    """Operators/admins attach one eligible, unassigned episode to a request."""
    ensure_role(actor, UserRole.OPERATOR, UserRole.ADMIN)
    if request.status not in ASSIGNABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot assign to a {request.status.value} request",
        )
    if episode.quality == EpisodeQuality.BAD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only good or usable episodes can be assigned",
        )
    existing = session.scalar(
        select(Assignment).where(Assignment.episode_id == episode.id)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Episode is already assigned to a request",
        )
    assignment = Assignment(
        request_id=request.id,
        episode_id=episode.id,
        assigned_by=actor.id,
        assigned_at=datetime.now(UTC),
    )
    session.add(assignment)
    try:
        session.commit()
    except IntegrityError as exc:
        # The unique constraint closes the race between two operators
        # assigning the same episode at the same time: one wins, one 409s.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Episode is already assigned to a request",
        ) from exc
    session.refresh(assignment)
    return assignment
