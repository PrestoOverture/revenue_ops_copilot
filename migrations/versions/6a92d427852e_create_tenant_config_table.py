"""create_tenant_config_table

Revision ID: 6a92d427852e
Revises: 63bb1a81f8e9
Create Date: 2026-02-20 21:45:05.117439

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6a92d427852e'
down_revision: Union[str, Sequence[str], None] = '63bb1a81f8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE tenant_config (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id             UUID NOT NULL UNIQUE,
            approval_required     BOOLEAN NOT NULL DEFAULT true,
            followups_enabled     BOOLEAN NOT NULL DEFAULT true,
            max_touchpoints       INT NOT NULL DEFAULT 3,
            followup_delay_hours  INT NOT NULL DEFAULT 48,
            email_provider        TEXT,
            email_credentials     BYTEA,
            crm_provider          TEXT,
            crm_credentials       BYTEA,
            llm_provider          TEXT NOT NULL DEFAULT 'openai',
            qualification_model   TEXT NOT NULL DEFAULT 'gpt-4o-mini',
            drafting_model        TEXT NOT NULL DEFAULT 'gpt-4o',
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE tenant_config;")
