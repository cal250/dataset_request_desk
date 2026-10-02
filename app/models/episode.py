from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.user import enum_values


class EpisodeQuality(StrEnum):
    GOOD = "good"
    USABLE = "usable"
    BAD = "bad"


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (CheckConstraint("duration_seconds > 0", name="episode_duration_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    robot_id: Mapped[str] = mapped_column(String(100), index=True)
    task_name: Mapped[str] = mapped_column(String(200), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    operator_name: Mapped[str] = mapped_column(String(200))
    quality: Mapped[EpisodeQuality] = mapped_column(
        Enum(EpisodeQuality, name="episode_quality", values_callable=enum_values), index=True
    )

