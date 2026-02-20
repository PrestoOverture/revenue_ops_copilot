"""create_outbox_table

Revision ID: 7a48c1cbb8a0
Revises: 119dabf51774
Create Date: 2026-02-20 15:02:57.890950

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7a48c1cbb8a0'
down_revision: Union[str, Sequence[str], None] = '119dabf51774'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE outbox (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL,
            lead_id         UUID NOT NULL REFERENCES lead_state(id),
            type            TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            payload         JSONB NOT NULL,
            status          TEXT NOT NULL DEFAULT 'PENDING',
            attempts        INT NOT NULL DEFAULT 0,
            max_attempts    INT NOT NULL DEFAULT 5,
            last_error      TEXT,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            sent_at         TIMESTAMPTZ,
            CONSTRAINT uq_outbox_idempotency UNIQUE (tenant_id, type, idempotency_key)
        );
        """
    )
    op.execute("CREATE INDEX ix_outbox_status_next_attempt ON outbox (status, next_attempt_at);")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX ix_outbox_status_next_attempt;")
    op.execute("DROP TABLE outbox;")
