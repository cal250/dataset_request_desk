from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_operator_user
from app.db import get_db_session
from app.models.episode import Episode, EpisodeQuality
from app.models.user import User
from app.services.import_episodes import ImportReport, import_csv

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


@router.get("/episodes", response_model=list[EpisodeOut])
def list_episodes(
    user: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
    task_name: str | None = None,
    quality: EpisodeQuality | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Episode]:
    """Operator episode search with task/quality filters (paginated from day one)."""
    query = select(Episode).order_by(Episode.id)
    if task_name and task_name.strip():
        query = query.where(Episode.task_name == " ".join(task_name.split()).lower())
    if quality is not None:
        query = query.where(Episode.quality == quality)
    query = query.offset(max(offset, 0)).limit(min(max(limit, 1), 200))
    return list(session.scalars(query).all())


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
    user: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
    file: Annotated[UploadFile, File(...)],
) -> ImportReportOut:
    import io

    content = file.file.read().decode("utf-8-sig")
    report = import_csv(session, io.StringIO(content))
    return _report_out(report)
