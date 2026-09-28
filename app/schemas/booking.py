import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    test_id: uuid.UUID
    centre_id: uuid.UUID
    appointment_datetime: datetime

    @field_validator("appointment_datetime")
    @classmethod
    def must_be_future(cls, value: datetime) -> datetime:
        now = datetime.now(value.tzinfo)
        if value <= now:
            raise ValueError("appointment_datetime must be in the future")
        return value


class BookingOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    test_id: uuid.UUID
    centre_id: uuid.UUID
    appointment_datetime: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime

    model_config = {"from_attributes": True}
