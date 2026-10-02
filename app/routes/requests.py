from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db_session
from app.models.request import DatasetRequest
from app.models.user import User, UserRole
from app.schemas.request import RequestCreate, RequestOut, TransitionIn
from app.services.requests import create_request, get_request_or_404, transition_request

router = APIRouter(tags=["requests"])


@router.post("/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: RequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DatasetRequest:
    return create_request(
        session,
        client=user,
        task_name=payload.task_name,
        episodes_requested=payload.episodes_requested,
        deadline=payload.deadline,
        notes=payload.notes,
    )


@router.get("/requests", response_model=list[RequestOut])
def list_requests(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[DatasetRequest]:
    """Clients see only their own; operators/admins see everything."""
    query = select(DatasetRequest).order_by(DatasetRequest.id.desc())
    if user.role == UserRole.CLIENT:
        query = query.where(DatasetRequest.client_id == user.id)
    return list(session.scalars(query).all())


@router.get("/requests/{request_id}", response_model=RequestOut)
def detail(
    request_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DatasetRequest:
    return get_request_or_404(session, user, request_id)


@router.post("/requests/{request_id}/transitions", response_model=RequestOut)
def transition(
    request_id: int,
    payload: TransitionIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DatasetRequest:
    request = get_request_or_404(session, user, request_id)
    return transition_request(session, request, payload.status, actor=user)
