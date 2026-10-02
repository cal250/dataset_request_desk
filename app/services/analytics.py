"""Date-range analytics, aggregated in PostgreSQL (never in Python loops)."""

from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.episode import Episode, EpisodeQuality
from app.models.request import DatasetRequest

MAX_RANGE_DAYS = 366


def validate_range(start: date, end: date) -> tuple[datetime, datetime]:
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start must be on or before end",
        )
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Date range must not exceed {MAX_RANGE_DAYS} days",
        )
    # Half-open [start_day, end_day + 1) keeps the end day inclusive with no
    # time-of-day edge cases; recorded_at is UTC-aware so naive bounds compare
    # cleanly against timestamptz.
    start_at = datetime(start.year, start.month, start.day)
    end_at = datetime.fromordinal(end.toordinal() + 1)
    return start_at, end_at


def episodes_per_day_robot(
    session: Session, start_at: datetime, end_at: datetime
) -> list[dict]:
    """Recordings grouped by day and robot, straight from the database."""
    day = func.date_trunc("day", Episode.recorded_at).label("day")
    rows = session.execute(
        select(day, Episode.robot_id, func.count().label("count"))
        .where(Episode.recorded_at >= start_at, Episode.recorded_at < end_at)
        .group_by(day, Episode.robot_id)
        .order_by(day, Episode.robot_id)
    ).all()
    return [
        {"day": row.day.date().isoformat(), "robot_id": row.robot_id, "count": row.count}
        for row in rows
    ]


def requests_by_status(session: Session, start_at: datetime, end_at: datetime) -> list[dict]:
    """Requests submitted in range, counted per status."""
    rows = session.execute(
        select(DatasetRequest.status, func.count().label("count"))
        .where(
            DatasetRequest.submitted_at >= start_at, DatasetRequest.submitted_at < end_at
        )
        .group_by(DatasetRequest.status)
        .order_by(DatasetRequest.status)
    ).all()
    return [{"status": row.status.value, "count": row.count} for row in rows]


def median_fulfilment_seconds(
    session: Session, start_at: datetime, end_at: datetime
) -> float | None:
    """Median submitted->delivered seconds via percentile_cont (single query)."""
    seconds = func.extract("epoch", DatasetRequest.delivered_at - DatasetRequest.submitted_at)
    median = func.percentile_cont(0.5).within_group(seconds)
    return session.scalar(
        select(median).where(
            DatasetRequest.submitted_at >= start_at,
            DatasetRequest.submitted_at < end_at,
            DatasetRequest.delivered_at.is_not(None),
        )
    )


def top_good_tasks(session: Session, start_at: datetime, end_at: datetime) -> list[dict]:
    """Five most frequent task names among good episodes."""
    rows = session.execute(
        select(Episode.task_name, func.count().label("count"))
        .where(
            Episode.recorded_at >= start_at,
            Episode.recorded_at < end_at,
            Episode.quality == EpisodeQuality.GOOD,
        )
        .group_by(Episode.task_name)
        .order_by(func.count().desc(), Episode.task_name)
        .limit(5)
    ).all()
    return [{"task_name": row.task_name, "count": row.count} for row in rows]
