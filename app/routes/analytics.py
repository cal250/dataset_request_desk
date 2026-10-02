from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_operator_user
from app.db import get_db_session
from app.models.user import User
from app.services import analytics as service

router = APIRouter(tags=["analytics"])


class DayRobotOut(BaseModel):
    day: str
    robot_id: str
    count: int


class StatusCountOut(BaseModel):
    status: str
    count: int


class TaskCountOut(BaseModel):
    task_name: str
    count: int


class AnalyticsOut(BaseModel):
    start: date
    end: date
    episodes_per_day_robot: list[DayRobotOut]
    requests_by_status: list[StatusCountOut]
    median_submitted_to_delivered_seconds: float | None
    top_tasks_by_good_episodes: list[TaskCountOut]


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(
    user: Annotated[User, Depends(get_operator_user)],
    session: Annotated[Session, Depends(get_db_session)],
    start: date,
    end: date,
) -> AnalyticsOut:
    """Operational aggregates for a bounded date range (operators/admins only)."""
    start_at, end_at = service.validate_range(start, end)
    return AnalyticsOut(
        start=start,
        end=end,
        episodes_per_day_robot=service.episodes_per_day_robot(session, start_at, end_at),
        requests_by_status=service.requests_by_status(session, start_at, end_at),
        median_submitted_to_delivered_seconds=service.median_fulfilment_seconds(
            session, start_at, end_at
        ),
        top_tasks_by_good_episodes=service.top_good_tasks(session, start_at, end_at),
    )
