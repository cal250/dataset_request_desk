from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db_session
from app.models.assignment import Assignment
from app.models.episode import Episode
from app.models.request import DatasetRequest, RequestStatus, StatusHistory
from app.models.user import User, UserRole
from app.schemas.request import RequestCreate, RequestOut, TransitionIn
from app.services.requests import create_request, get_request_or_404, transition_request
from app.ui import templates, wants_html

router = APIRouter(tags=["requests"])

_TRANSITION_LABELS = {
    "in_progress": "Start work",
    "delivered": "Mark delivered",
    "accepted": "Accept delivery",
    "rejected": "Request rework",
}

# Valid next steps per status; the service still enforces roles server-side.
_NEXT = {
    RequestStatus.SUBMITTED: [RequestStatus.IN_PROGRESS],
    RequestStatus.IN_PROGRESS: [RequestStatus.DELIVERED],
    RequestStatus.DELIVERED: [RequestStatus.ACCEPTED, RequestStatus.REJECTED],
    RequestStatus.REJECTED: [RequestStatus.IN_PROGRESS],
    RequestStatus.ACCEPTED: [],
}


def _counts(session: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = session.execute(
        select(Assignment.request_id, func.count().label("count"))
        .where(Assignment.request_id.in_(ids))
        .group_by(Assignment.request_id)
    ).all()
    return {row.request_id: row.count for row in rows}


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


@router.post("/requests/form", status_code=status.HTTP_303_SEE_OTHER)
def create_form(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    task_name: Annotated[str, Form()],
    episodes_requested: Annotated[int, Form()],
    deadline: Annotated[date, Form()],
    notes: Annotated[str, Form()] = "",
):
    """Browser form baseline: same service, redirect back to the list/detail."""
    try:
        created = create_request(
            session,
            client=user,
            task_name=task_name,
            episodes_requested=episodes_requested,
            deadline=deadline,
            notes=notes or None,
        )
    except Exception:
        return templates.TemplateResponse(
            request,
            "request_new.html",
            {
                "user": user,
                "active": "requests",
                "error": "Could not create the request. Check the values and try again.",
                "form": {
                    "task_name": task_name,
                    "episodes_requested": episodes_requested,
                    "deadline": str(deadline),
                    "notes": notes,
                },
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return RedirectResponse(
        url=f"/requests/{created.id}?toast=Request+created",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/requests", response_model=list[RequestOut])
def list_requests(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    """Clients see only their own; operators/admins see everything."""
    query = select(DatasetRequest).order_by(DatasetRequest.id.desc())
    if user.role == UserRole.CLIENT:
        query = query.where(DatasetRequest.client_id == user.id)
    rows = list(session.scalars(query).all())
    if wants_html(request):
        chips: dict[str, int] = {}
        for row in rows:
            chips[row.status.value] = chips.get(row.status.value, 0) + 1
        return templates.TemplateResponse(
            request,
            "requests.html",
            {
                "user": user,
                "active": "requests",
                "requests": rows,
                "counts": _counts(session, [r.id for r in rows]),
                "status_counts": [
                    {"label": label.replace("_", " "), "count": count}
                    for label, count in sorted(chips.items())
                ],
            },
        )
    return rows


@router.get("/requests/new")
def new_form(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
):
    from fastapi import HTTPException

    if user.role != UserRole.CLIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return templates.TemplateResponse(
        request, "request_new.html", {"user": user, "active": "requests", "form": {}}
    )


@router.get("/requests/{request_id}", response_model=RequestOut)
def detail(
    request_id: int,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
):
    row = get_request_or_404(session, user, request_id)
    if wants_html(request):
        assigned = list(
            session.scalars(
                select(Assignment).where(Assignment.request_id == row.id).order_by(Assignment.id)
            ).all()
        )
        episodes = {
            e.id: e
            for e in session.scalars(
                select(Episode).where(
                    Episode.id.in_([a.episode_id for a in assigned]) if assigned else False
                )
            ).all()
        }
        history = list(
            session.scalars(
                select(StatusHistory)
                .where(StatusHistory.request_id == row.id)
                .order_by(StatusHistory.id)
            ).all()
        )
        tasks = list(
            session.scalars(select(Episode.task_name).distinct().order_by(Episode.task_name)).all()
        )
        return templates.TemplateResponse(
            request,
            "request_detail.html",
            {
                "user": user,
                "active": "requests",
                "req": row,
                "assigned": assigned,
                "episodes": episodes,
                "history": history,
                "transitions": _NEXT[row.status],
                "labels": _TRANSITION_LABELS,
                "eligible": _eligible(session, row)[:20],
                "tasks": tasks,
            },
        )
    return row


def _eligible(
    session: Session, row: DatasetRequest, task_name: str | None = None
) -> list[Episode]:
    assigned_ids = select(Assignment.episode_id)
    query = (
        select(Episode)
        .where(Episode.quality != "bad", Episode.id.not_in(assigned_ids))
        .order_by(Episode.id)
    )
    if task_name and task_name.strip():
        query = query.where(Episode.task_name == " ".join(task_name.split()).lower())
    return list(session.scalars(query.limit(50)).all())


@router.get("/requests/{request_id}/eligible")
def eligible_rows(
    request_id: int,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    task_name: str | None = None,
    quality: str | None = None,
):
    """HTMX fragment: unassigned good/usable episodes for the assign panel."""
    row = get_request_or_404(session, user, request_id)
    from fastapi import HTTPException

    if user.role not in (UserRole.OPERATOR, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    candidates = _eligible(session, row, task_name)
    if quality in ("good", "usable"):
        candidates = [e for e in candidates if e.quality.value == quality]
    return templates.TemplateResponse(
        request, "eligible_rows.html", {"req": row, "eligible": candidates[:20]}
    )


@router.post("/requests/{request_id}/transitions", response_model=RequestOut)
def transition(
    request_id: int,
    payload: TransitionIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DatasetRequest:
    row = get_request_or_404(session, user, request_id)
    return transition_request(session, row, payload.status, actor=user)


@router.post("/requests/{request_id}/transitions/form", status_code=status.HTTP_303_SEE_OTHER)
def transition_form(
    request_id: int,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    status: Annotated[RequestStatus, Form()],
):
    row = get_request_or_404(session, user, request_id)
    transition_request(session, row, status, actor=user)
    return RedirectResponse(
        url=f"/requests/{request_id}?toast=Status+updated",
        status_code=status.HTTP_303_SEE_OTHER,
    )
