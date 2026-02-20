"""create_runs_table

Revision ID: e2498aa7a10c
Revises: 7a48c1cbb8a0
Create Date: 2026-02-20 18:08:13.323874

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e2498aa7a10c'
down_revision: Union[str, Sequence[str], None] = '7a48c1cbb8a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE runs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL,
            lead_id          UUID NOT NULL REFERENCES lead_state(id),
            step             TEXT NOT NULL,
            status           TEXT NOT NULL,
            error            TEXT,
            error_code       TEXT,
            latency_ms       INT,
            model            TEXT,
            prompt_version   TEXT,
            tokens_in        INT,
            tokens_out       INT,
            cost_usd         DECIMAL(10, 6),
            schema_valid     BOOLEAN,
            repair_attempted BOOLEAN DEFAULT FALSE,
            fallback_used    TEXT,
            policy_decision  TEXT,
            policy_reason    TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_runs_lead_id ON runs (lead_id);")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX ix_runs_lead_id;")
    op.execute("DROP TABLE runs;")
