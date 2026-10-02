"""Create the Dataset Request Desk core schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

user_role = postgresql.ENUM("client", "operator", "admin", name="user_role", create_type=False)
episode_quality = postgresql.ENUM("good", "usable", "bad", name="episode_quality", create_type=False)
request_status = postgresql.ENUM(
    "submitted",
    "in_progress",
    "delivered",
    "accepted",
    "rejected",
    name="request_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    episode_quality.create(bind, checkfirst=True)
    request_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organisation", sa.String(length=200), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.String(length=100), nullable=False),
        sa.Column("robot_id", sa.String(length=100), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("operator_name", sa.String(length=200), nullable=False),
        sa.Column("quality", episode_quality, nullable=False),
        sa.CheckConstraint("duration_seconds > 0", name="episode_duration_positive"),
    )
    op.create_index("ix_episodes_episode_id", "episodes", ["episode_id"], unique=True)
    op.create_index("ix_episodes_robot_id", "episodes", ["robot_id"])
    op.create_index("ix_episodes_task_name", "episodes", ["task_name"])
    op.create_index("ix_episodes_recorded_at", "episodes", ["recorded_at"])
    op.create_index("ix_episodes_quality", "episodes", ["quality"])

    op.create_table(
        "requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=False),
        sa.Column("episodes_requested", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", request_status, nullable=False, server_default="submitted"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("episodes_requested > 0", name="request_episode_count_positive"),
    )
    op.create_index("ix_requests_client_id", "requests", ["client_id"])
    op.create_index("ix_requests_task_name", "requests", ["task_name"])
    op.create_index("ix_requests_status", "requests", ["status"])

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("episode_id", name="uq_assignments_episode_id"),
    )
    op.create_index("ix_assignments_request_id", "assignments", ["request_id"])
    op.create_index("ix_assignments_assigned_by", "assignments", ["assigned_by"])

    op.create_table(
        "status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("from_status", request_status, nullable=True),
        sa.Column("to_status", request_status, nullable=False),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_status_history_request_id", "status_history", ["request_id"])
    op.create_index("ix_status_history_changed_by", "status_history", ["changed_by"])


def downgrade() -> None:
    op.drop_table("status_history")
    op.drop_table("assignments")
    op.drop_table("requests")
    op.drop_table("episodes")
    op.drop_table("users")

    bind = op.get_bind()
    request_status.drop(bind, checkfirst=True)
    episode_quality.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)

