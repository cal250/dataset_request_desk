"""Deterministic, idempotent CSV episode import.

Policy (PLAN.md): normalize formatting-only values, reject semantic guesses,
report every skipped row with its number and reason. Re-running the same file
never creates duplicates thanks to the unique canonical episode_id.
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import TextIOBase
from typing import TextIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.episode import Episode, EpisodeQuality

KNOWN_ROBOTS = frozenset({"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"})
MAX_DURATION_SECONDS = 3600
MAX_ERRORS_REPORTED = 100


@dataclass
class ImportRowError:
    row: int
    episode_id: str | None
    reason: str


@dataclass
class ImportReport:
    inserted: int = 0
    already_exists: int = 0
    skipped_invalid: int = 0
    skipped_conflict: int = 0
    errors: list[ImportRowError] = field(default_factory=list)

    def add_error(self, row: int, episode_id: str | None, reason: str) -> None:
        if self.row_failed(row):
            return
        if len(self.errors) < MAX_ERRORS_REPORTED:
            self.errors.append(ImportRowError(row=row, episode_id=episode_id, reason=reason))

    def row_failed(self, row: int) -> bool:
        return any(error.row == row for error in self.errors)


@dataclass
class _CleanRow:
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int
    operator_name: str
    quality: EpisodeQuality

    def identity(self) -> tuple:
        """Canonical fields compared for duplicate-vs-conflict decisions."""
        return (
            self.episode_id,
            self.robot_id,
            self.task_name,
            self.recorded_at.isoformat(),
            self.duration_seconds,
            self.operator_name,
            self.quality.value,
        )


def _parse_recorded_at(raw: str) -> datetime | None:
    """Accept explicit ISO-8601 only; ambiguous slash dates are rejected."""
    text = raw.strip()
    if not text or "/" in text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_duration(raw: str) -> int | None:
    text = raw.strip()
    if not re.fullmatch(r"\d+", text):
        return None
    value = int(text)
    return value if 1 <= value <= MAX_DURATION_SECONDS else None


def _clean_row_numbered(row_number: int, raw: dict[str, str | None]) -> _CleanRow | str:
    """Return a _CleanRow or the human-readable rejection reason."""

    def get(name: str) -> str:
        return (raw.get(name) or "").strip()

    episode_id = get("episode_id").upper()
    if not episode_id:
        return "episode_id is required"
    robot_id = get("robot_id").lower()
    if robot_id not in KNOWN_ROBOTS:
        return f"unknown robot_id {get('robot_id')!r}"
    task_name = " ".join(get("task_name").split()).lower()
    if not task_name:
        return "task_name is required"
    recorded_at = _parse_recorded_at(raw.get("recorded_at") or "")
    if recorded_at is None:
        return f"unparseable recorded_at {get('recorded_at')!r}"
    duration = _parse_duration(raw.get("duration_seconds") or "")
    if duration is None:
        return f"invalid duration_seconds {get('duration_seconds')!r}"
    operator_name = get("operator_name")
    if not operator_name:
        return "operator_name is required"
    quality_text = get("quality").lower()
    try:
        quality = EpisodeQuality(quality_text)
    except ValueError:
        return f"unknown quality {get('quality')!r}"
    return _CleanRow(
        episode_id=episode_id,
        robot_id=robot_id,
        task_name=task_name,
        recorded_at=recorded_at,
        duration_seconds=duration,
        operator_name=operator_name,
        quality=quality,
    )


def _same_episode(existing: Episode, clean: _CleanRow) -> bool:
    return (
        existing.robot_id == clean.robot_id
        and existing.task_name == clean.task_name
        and existing.recorded_at == clean.recorded_at
        and existing.duration_seconds == clean.duration_seconds
        and existing.operator_name == clean.operator_name
        and existing.quality == clean.quality
    )


def import_csv(session: Session, handle: TextIO | TextIOBase) -> ImportReport:
    """Parse, validate, and upsert episode rows idempotently (one commit)."""
    report = ImportReport()
    seen_in_file: dict[str, tuple] = {}
    reader = csv.DictReader(handle)
    for row_number, raw in enumerate(reader, start=2):  # header is row 1
        raw_id = (raw.get("episode_id") or "").strip() or None
        cleaned = _clean_row_numbered(row_number, raw)
        if isinstance(cleaned, str):
            report.skipped_invalid += 1
            report.add_error(row_number, raw_id, cleaned)
            continue
        identity = cleaned.identity()
        if cleaned.episode_id in seen_in_file:
            # Later file rows never overwrite the first valid occurrence.
            if seen_in_file[cleaned.episode_id] == identity:
                report.already_exists += 1
            else:
                report.skipped_conflict += 1
                report.add_error(
                    row_number, cleaned.episode_id, "episode_id conflicts with an earlier row"
                )
            continue
        seen_in_file[cleaned.episode_id] = identity

        existing = session.scalar(
            select(Episode).where(Episode.episode_id == cleaned.episode_id)
        )
        if existing is None:
            session.add(
                Episode(
                    episode_id=cleaned.episode_id,
                    robot_id=cleaned.robot_id,
                    task_name=cleaned.task_name,
                    recorded_at=cleaned.recorded_at,
                    duration_seconds=cleaned.duration_seconds,
                    operator_name=cleaned.operator_name,
                    quality=cleaned.quality,
                )
            )
            report.inserted += 1
        elif _same_episode(existing, cleaned):
            report.already_exists += 1
        else:
            # Never silently overwrite stored metadata; a human must decide.
            report.skipped_conflict += 1
            report.add_error(
                row_number,
                cleaned.episode_id,
                "episode_id already exists with different data",
            )
    session.commit()
    return report
