"""create_email_templates_table

Revision ID: 63bb1a81f8e9
Revises: 8ad3c9617d17
Create Date: 2026-02-20 18:35:32.930983

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '63bb1a81f8e9'
down_revision: Union[str, Sequence[str], None] = '8ad3c9617d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE email_templates (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id         UUID NOT NULL,
            name              TEXT NOT NULL,
            subject_template  TEXT NOT NULL,
            body_template     TEXT NOT NULL,
            is_fallback       BOOLEAN NOT NULL DEFAULT false,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_email_templates_tenant_name UNIQUE (tenant_id, name)
        );
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE email_templates;")
