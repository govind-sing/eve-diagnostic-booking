import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models.payment import PaymentStatus


class PaymentInitiate(BaseModel):
    booking_id: uuid.UUID


class PaymentOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    event_id: str
    status: PaymentStatus
    amount: Decimal

    model_config = {"from_attributes": True}


class WebhookPayload(BaseModel):
    event_id: str
    status: Literal[PaymentStatus.SUCCESS, PaymentStatus.FAILED]
