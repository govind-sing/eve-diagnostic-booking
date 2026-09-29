"""add user role, diagnostic centres and tests

Revision ID: 8d1c61ef2ba4
Revises: 633406948697
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "8d1c61ef2ba4"
down_revision = "633406948697"
branch_labels = None
depends_on = None

user_role = postgresql.ENUM("admin", "patient", name="user_role")


def upgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("admin", "patient", name="user_role"),
            nullable=False,
            server_default="patient",
        ),
    )

    op.create_table(
        "diagnostic_centres",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "diagnostic_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "centre_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diagnostic_centres.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("diagnostic_tests")
    op.drop_table("diagnostic_centres")
    op.drop_column("users", "role")
    user_role.drop(op.get_bind(), checkfirst=True)
