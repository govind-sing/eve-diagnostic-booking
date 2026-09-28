import uuid

from sqlalchemy import Column, String, Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    location = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tests = relationship(
        "DiagnosticTest", back_populates="centre", cascade="all, delete-orphan"
    )


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    centre_id = Column(
        UUID(as_uuid=True), ForeignKey("diagnostic_centres.id"), nullable=False
    )
    name = Column(String, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    centre = relationship("DiagnosticCentre", back_populates="tests")
