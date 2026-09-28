import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    test_id = Column(
        UUID(as_uuid=True), ForeignKey("diagnostic_tests.id"), nullable=False
    )
    centre_id = Column(
        UUID(as_uuid=True), ForeignKey("diagnostic_centres.id"), nullable=False
    )
    appointment_datetime = Column(DateTime(timezone=True), nullable=False)
    # Snapshotted from the test's price at booking time, so a later price
    # change on the catalog doesn't alter an existing booking's amount.
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(
        Enum(BookingStatus, name="booking_status"),
        nullable=False,
        default=BookingStatus.PENDING,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    test = relationship("DiagnosticTest")
    centre = relationship("DiagnosticCentre")
