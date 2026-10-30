"""Add caption ledger and durable demo cursor.

Revision ID: 0002_caption_ledger
Revises: 0001_initial_schema
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_caption_ledger"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("demo_cursor", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("last_event_index", sa.Integer(), nullable=False, server_default="-1")
        )

    # Legacy demo cursors lived in AI memory and cannot resume the new scenario.
    op.execute(
        "UPDATE sessions SET status = 'COMPLETED', ended_at = CURRENT_TIMESTAMP "
        "WHERE mode = 'DEMO' AND status IN ('CREATED', 'ACTIVE', 'PAUSED')"
    )

    op.create_table(
        "captions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_text", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "session_id", name="uq_caption_session"),
    )
    op.create_index("ix_captions_session_id", "captions", ["session_id"])

    op.create_table(
        "caption_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("caption_id", sa.String(36), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("caption_version", sa.Integer(), nullable=False),
        sa.Column(
            "previous_event_id",
            sa.String(36),
            sa.ForeignKey("caption_events.id"),
            nullable=True,
        ),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["caption_id", "session_id"],
            ["captions.id", "captions.session_id"],
            name="fk_caption_events_caption_session",
        ),
        sa.UniqueConstraint("session_id", "event_index", name="uq_caption_event_order"),
        sa.UniqueConstraint(
            "session_id", "caption_id", "caption_version", name="uq_caption_version"
        ),
    )
    op.create_index("ix_caption_events_session_id", "caption_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_caption_events_session_id", table_name="caption_events")
    op.drop_table("caption_events")
    op.drop_index("ix_captions_session_id", table_name="captions")
    op.drop_table("captions")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("last_event_index")
        batch.drop_column("demo_cursor")
