from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_operator_user
from app.db import get_db_session
from app.models.episode import Episode, EpisodeQuality
from app.models.user import User
from app.services.import_episodes import ImportReport, import_csv
from app.ui import templates, wants_html

router = APIRouter(tags=["episodes"])


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int
    operator_name: str
    quality: EpisodeQuality


class ImportErrorOut(BaseModel):
    row: int
    episode_id: str | None
    reason: str


class ImportReportOut(BaseModel):
    inserted: int
    already_exists: int
    skipped_invalid: int
    skipped_conflict: int
    errors: list[ImportErrorOut]


def _report_out(report: ImportReport) -> ImportReportOut:
    return ImportReportOut(
        inserted=report.inserted,
        already_exists=report.already_exists,
        skipped_invalid=report.skipped_invalid,
        skipped_conflict=report.skipped_conflict,
        errors=[
            ImportErrorOut(row=e.row, episode_id=e.episode_id, reason=e.reason)
            for e in report.errors
        ],
    )


PER_PAGE_OPTIONS = (10, 25, 50, 100)


def _parse_quality(raw: str | None) -> EpisodeQuality | None:
    """Empty string means Any; anything else must be a known quality."""
    if raw is None or not raw.strip():
        return None
    try:
        return EpisodeQuality(raw.strip().lower())
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown quality {raw!r}",
        ) from err


def _filtered_query(task_name: str | None, quality: EpisodeQuality | None):
    query = select(Episode).order_by(Episode.id)
    if task_name and task_name.strip():
        query = query.where(Episode.task_name == " ".join(task_name.split()).lower())
    if quality is not None:
        query = query.where(Episode.quality == quality)
    return query


def _page_context(
    *,
    rows: list[Episode],
    total: int,
    page: int,
    per_page: int,
    task_name: str,
    quality: str,
    report=None,
    user=None,
):
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(max(page, 1), total_pages)
    start = (page - 1) * per_page + 1 if total else 0
    return {
        "user": user,
        "active": "episodes",
        "episodes": rows,
        "total": total,
        "task_name": task_name,
        "quality": quality,
        "report": report,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "range_start": start,
        "range_end": min(page * per_page, total),
        "per_page_options": PER_PAGE_OPTIONS,
    }


@router.get("/episodes", response_model=list[EpisodeOut])
def list_episodes(
    request: Request,
    user: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
    task_name: str | None = None,
    quality: str | None = None,
    page: int = 1,
    per_page: int = 50,
    limit: int | None = None,  # legacy JSON params, still honored
    offset: int | None = None,
):
    """Operator episode search with task/quality filters and pagination."""
    parsed_quality = _parse_quality(quality)
    query = _filtered_query(task_name, parsed_quality)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    if limit is not None or offset is not None:  # legacy API-style paging
        page_limit = min(max(limit or 50, 1), 200)
        page_offset = max(offset or 0, 0)
        rows = list(session.scalars(query.offset(page_offset).limit(page_limit)).all())
        if wants_html(request):
            page = page_offset // page_limit + 1
            return templates.TemplateResponse(
                request,
                "episodes.html",
                _page_context(
                    rows=rows,
                    total=total,
                    page=page,
                    per_page=page_limit,
                    task_name=(task_name or "").strip(),
                    quality=parsed_quality.value if parsed_quality else "",
                    user=user,
                ),
            )
        return rows
    per_page = min(max(per_page, 1), 100)
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(max(page, 1), total_pages)
    rows = list(
        session.scalars(query.offset((page - 1) * per_page).limit(per_page)).all()
    )
    if wants_html(request):
        return templates.TemplateResponse(
            request,
            "episodes.html",
            _page_context(
                rows=rows,
                total=total,
                page=page,
                per_page=per_page,
                task_name=(task_name or "").strip(),
                quality=parsed_quality.value if parsed_quality else "",
                user=user,
            ),
        )
    return rows


@router.get("/episodes/count", response_model=int)
def count_episodes(
    user: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> int:
    return session.scalar(select(func.count()).select_from(Episode))


@router.post(
    "/episodes/import", response_model=ImportReportOut, status_code=status.HTTP_200_OK
)
def import_upload(
    request: Request,
    user: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
    file: Annotated[UploadFile, File(...)],
):
    import io

    content = file.file.read().decode("utf-8-sig")
    report = import_csv(session, io.StringIO(content))
    if wants_html(request):
        rows = list(session.scalars(select(Episode).order_by(Episode.id).limit(50)).all())
        total = session.scalar(select(func.count()).select_from(Episode))
        return templates.TemplateResponse(
            request,
            "episodes.html",
            _page_context(
                rows=rows,
                total=total,
                page=1,
                per_page=50,
                task_name="",
                quality="",
                report=_report_out(report),
                user=user,
            ),
        )
    return _report_out(report)
