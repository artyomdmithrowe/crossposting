"""disable telegram id autoincrement

Revision ID: 0944e59edb13
Revises: 16d09006091c
Create Date: 2026-10-29 01:40:32.836737

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0944e59edb13"
down_revision: Union[str, Sequence[str], None] = "16d09006091c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        server_default=None,
    )

    op.execute("DROP SEQUENCE users_telegram_id_seq")


def downgrade() -> None:
    op.execute(
        "CREATE SEQUENCE users_telegram_id_seq AS bigint OWNED BY users.telegram_id"
    )

    op.execute(
        "SELECT setval("
        "'users_telegram_id_seq', "
        "GREATEST(COALESCE((SELECT MAX(telegram_id) FROM users), 1), 1), "
        "EXISTS (SELECT 1 FROM users)"
        ")"
    )

    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        server_default=sa.text("nextval('users_telegram_id_seq'::regclass)"),
    )
