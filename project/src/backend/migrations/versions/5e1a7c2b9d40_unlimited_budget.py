"""unlimited budget: itineraries.budget_total nullable (ADR-0021)

Revision ID: 5e1a7c2b9d40
Revises: c8d04543b9c7

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5e1a7c2b9d40"
down_revision: Union[str, Sequence[str], None] = "c8d04543b9c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("itineraries", "budget_total", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("itineraries", "budget_total", existing_type=sa.Integer(), nullable=False)
