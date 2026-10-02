from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.request import RequestStatus


class RequestCreate(BaseModel):
    task_name: str = Field(min_length=1, max_length=200)
    episodes_requested: int = Field(gt=0, le=100000)
    deadline: date
    notes: str | None = None

    @field_validator("task_name")
    @classmethod
    def _strip_task(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task name is required")
        return value


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    task_name: str
    episodes_requested: int
    deadline: date
    notes: str | None
    status: RequestStatus
    submitted_at: datetime
    delivered_at: datetime | None


class TransitionIn(BaseModel):
    status: RequestStatus
