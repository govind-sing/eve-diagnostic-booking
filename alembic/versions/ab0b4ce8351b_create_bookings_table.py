"""create bookings table

Revision ID: ab0b4ce8351b
Revises: 8d1c61ef2ba4
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ab0b4ce8351b"
down_revision = "8d1c61ef2ba4"
branch_labels = None
depends_on = None

booking_status = postgresql.ENUM(
    "PENDING", "CONFIRMED", "FAILED", "CANCELLED", name="booking_status"
)


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "test_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diagnostic_tests.id"),
            nullable=False,
        ),
        sa.Column(
            "centre_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diagnostic_centres.id"),
            nullable=False,
        ),
        sa.Column("appointment_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "CONFIRMED", "FAILED", "CANCELLED", name="booking_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_table("bookings")
    booking_status.drop(op.get_bind(), checkfirst=True)
