"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-23
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    session_source = sa.Enum("CAMERA", "VIDEO", "DEMO", name="sessionsource")
    session_mode = sa.Enum("DEMO", "LIVE", name="sessionmode")
    session_status = sa.Enum("CREATED", "ACTIVE", "PAUSED", "COMPLETED", "FAILED", name="sessionstatus")
    decision = sa.Enum("WAIT", "SPEAK", "UPDATE", name="decision")

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source", session_source, nullable=False),
        sa.Column("mode", session_mode, nullable=False),
        sa.Column("status", session_status, nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_frame_index", sa.Integer(), nullable=True),
    )
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])
    op.create_index("ix_sessions_mode", "sessions", ["mode"])
    op.create_index("ix_sessions_status", "sessions", ["status"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.String(length=128), nullable=False),
        sa.Column("action_label", sa.String(length=256), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("decision", decision, nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("previous_prediction_id", sa.String(length=36), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("inference_time_ms", sa.Float(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])
    op.create_index("ix_predictions_decision", "predictions", ["decision"])
    op.create_index("ix_predictions_session_id", "predictions", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_predictions_session_id", table_name="predictions")
    op.drop_index("ix_predictions_decision", table_name="predictions")
    op.drop_index("ix_predictions_created_at", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_index("ix_sessions_mode", table_name="sessions")
    op.drop_index("ix_sessions_created_at", table_name="sessions")
    op.drop_table("sessions")

