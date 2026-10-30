"""Add temporal streaming fields to caption events.

Revision ID: 0003_streaming_contract_v1
Revises: 0002_caption_ledger
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_streaming_contract_v1"
down_revision = "0002_caption_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("caption_events", sa.Column("start_ms", sa.Integer(), nullable=True))
    op.add_column("caption_events", sa.Column("end_ms", sa.Integer(), nullable=True))
    op.add_column("caption_events", sa.Column("model_id", sa.String(128), nullable=True))
    op.add_column("caption_events", sa.Column("inference_ms", sa.Float(), nullable=True))
    op.add_column("caption_events", sa.Column("processing_delay_ms", sa.Float(), nullable=True))
    op.add_column(
        "caption_events",
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE caption_events SET start_ms = timestamp_ms, end_ms = timestamp_ms, "
        "model_id = model_version, is_mock = is_demo"
    )
    op.create_index(
        "ix_caption_events_session_start", "caption_events", ["session_id", "start_ms"]
    )


def downgrade() -> None:
    op.drop_index("ix_caption_events_session_start", table_name="caption_events")
    with op.batch_alter_table("caption_events") as batch:
        batch.drop_column("is_mock")
        batch.drop_column("processing_delay_ms")
        batch.drop_column("inference_ms")
        batch.drop_column("model_id")
        batch.drop_column("end_ms")
        batch.drop_column("start_ms")
