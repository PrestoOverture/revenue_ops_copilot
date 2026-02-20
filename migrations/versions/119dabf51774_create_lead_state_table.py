"""create_lead_state_table

Revision ID: 119dabf51774
Revises: 50691814b9d6
Create Date: 2026-02-19 18:28:24.818988

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '119dabf51774'
down_revision: Union[str, Sequence[str], None] = '50691814b9d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE lead_state (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id           UUID NOT NULL,
            external_lead_id    TEXT NOT NULL,
            email               TEXT NOT NULL,
            name                TEXT,
            company             TEXT,
            source              TEXT,
            raw_payload         JSONB,

            -- Qualification output
            priority            TEXT,
            budget_range        TEXT,
            timeline            TEXT,
            qualification_notes TEXT,

            -- State machine
            state               TEXT NOT NULL DEFAULT 'PENDING',
            routing             TEXT,

            -- Follow-up tracking
            touchpoint_count    INT NOT NULL DEFAULT 0,
            max_touchpoints     INT NOT NULL DEFAULT 3,
            next_followup_at    TIMESTAMPTZ,

            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT uq_lead_tenant_external UNIQUE (tenant_id, external_lead_id)
        );
        """
    )
    op.execute("CREATE INDEX ix_lead_state_state ON lead_state (state);")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX ix_lead_state_state;")
    op.execute("DROP TABLE lead_state;")
