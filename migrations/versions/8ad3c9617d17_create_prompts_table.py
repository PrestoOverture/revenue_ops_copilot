"""create_prompts_table

Revision ID: 8ad3c9617d17
Revises: e2498aa7a10c
Create Date: 2026-02-20 18:23:58.530749

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8ad3c9617d17'
down_revision: Union[str, Sequence[str], None] = 'e2498aa7a10c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE prompts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID,
            name            TEXT NOT NULL,
            version         TEXT NOT NULL,
            system_prompt   TEXT NOT NULL,
            user_template   TEXT NOT NULL,
            model           TEXT NOT NULL,
            temperature     DECIMAL(2,1) NOT NULL DEFAULT 0.0,
            max_tokens      INT NOT NULL DEFAULT 1024,
            is_active       BOOLEAN NOT NULL DEFAULT false,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_prompts_tenant_name_active
            ON prompts (tenant_id, name)
            WHERE is_active = true;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_prompts_system_default_active
            ON prompts (name)
            WHERE is_active = true AND tenant_id IS NULL;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX uq_prompts_system_default_active;")
    op.execute("DROP INDEX uq_prompts_tenant_name_active;")
    op.execute("DROP TABLE prompts;")
