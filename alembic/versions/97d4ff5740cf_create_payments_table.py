"""create payments table

Revision ID: 97d4ff5740cf
Revises: ab0b4ce8351b
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "97d4ff5740cf"
down_revision = "ab0b4ce8351b"
branch_labels = None
depends_on = None

payment_status = postgresql.ENUM("PENDING", "SUCCESS", "FAILED", name="payment_status")


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SUCCESS", "FAILED", name="payment_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # This unique constraint is what actually enforces idempotency at the
    # data layer, independent of the application-level check in the route.
    op.create_index("ix_payments_event_id", "payments", ["event_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payments_event_id", table_name="payments")
    op.drop_table("payments")
    payment_status.drop(op.get_bind(), checkfirst=True)
