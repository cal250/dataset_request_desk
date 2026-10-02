"""Request creation + status-transition service (owns the workflow rules)."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import ensure_role
from app.models.assignment import Assignment
from app.models.request import DatasetRequest, RequestStatus, StatusHistory
from app.models.user import User, UserRole
from app.realtime import publish as publish_event

# (from, to) -> owner of that step. Delivery additionally needs the threshold.
_OPERATOR_STEPS = {
    (RequestStatus.SUBMITTED, RequestStatus.IN_PROGRESS),
    (RequestStatus.REJECTED, RequestStatus.IN_PROGRESS),
}
_OPERATOR_DELIVERY_STEP = (RequestStatus.IN_PROGRESS, RequestStatus.DELIVERED)
_CLIENT_STEPS = {
    (RequestStatus.DELIVERED, RequestStatus.ACCEPTED),
    (RequestStatus.DELIVERED, RequestStatus.REJECTED),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _assignment_count(session: Session, request_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(Assignment).where(Assignment.request_id == request_id)
    )


def create_request(
    session: Session,
    client: User,
    task_name: str,
    episodes_requested: int,
    deadline,
    notes: str | None,
) -> DatasetRequest:
    """Clients create requests; every creation writes its history row too."""
    ensure_role(client, UserRole.CLIENT)
    task_name = task_name.strip()
    if not task_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Task name is required"
        )
    if episodes_requested <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="episodes_requested must be positive",
        )
    request = DatasetRequest(
        client_id=client.id,
        task_name=task_name,
        episodes_requested=episodes_requested,
        deadline=deadline,
        notes=notes.strip() if notes and notes.strip() else None,
        status=RequestStatus.SUBMITTED,
        submitted_at=_now(),
    )
    session.add(request)
    session.flush()
    session.add(
        StatusHistory(
            request_id=request.id,
            from_status=None,
            to_status=RequestStatus.SUBMITTED,
            changed_by=client.id,
            changed_at=_now(),
        )
    )
    session.commit()
    session.refresh(request)
    publish_event("request.created", request.id, request.status.value, client.id)
    return request


def get_request_or_404(session: Session, user: User, request_id: int) -> DatasetRequest:
    """Ownership check: other clients get 404 so we never leak existence."""
    request = session.scalar(select(DatasetRequest).where(DatasetRequest.id == request_id))
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if user.role == UserRole.CLIENT and request.client_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return request


def transition_request(
    session: Session, request: DatasetRequest, target: RequestStatus, actor: User
) -> DatasetRequest:
    """Validate role + pair + delivery threshold, then move + audit in one commit."""
    pair = (request.status, target)
    if pair in _OPERATOR_STEPS or pair == _OPERATOR_DELIVERY_STEP:
        ensure_role(actor, UserRole.OPERATOR, UserRole.ADMIN)
        if pair == _OPERATOR_DELIVERY_STEP:
            assigned = _assignment_count(session, request.id)
            if assigned < request.episodes_requested:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Need {request.episodes_requested} episodes assigned, have {assigned}",
                )
    elif pair in _CLIENT_STEPS:
        # Only the owning client decides; operators/admins cannot accept/reject.
        if actor.role != UserRole.CLIENT or actor.id != request.client_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Cannot move from {request.status.value} to {target.value}",
        )

    from_status = request.status
    request.status = target
    if target == RequestStatus.DELIVERED:
        request.delivered_at = _now()
    session.add(
        StatusHistory(
            request_id=request.id,
            from_status=from_status,
            to_status=target,
            changed_by=actor.id,
            changed_at=_now(),
        )
    )
    session.commit()
    session.refresh(request)
    publish_event("request.updated", request.id, request.status.value, actor.id)
    return request
