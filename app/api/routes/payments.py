import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.schemas.payment import PaymentInitiate, PaymentOut, WebhookPayload

router = APIRouter(prefix="/payments", tags=["payments"])


def _apply_payment_result(
    payment: Payment, new_status: PaymentStatus, db: Session
) -> Payment:
    """Move a payment to a terminal state and update its booking to match.

    Both the synchronous "gateway response" in create_payment and the
    asynchronous webhook go through this, so idempotency behavior is
    identical regardless of path: once a payment is terminal, calling
    this again is a no-op.
    """
    if payment.status != PaymentStatus.PENDING:
        return payment

    payment.status = new_status
    payment.booking.status = (
        BookingStatus.CONFIRMED if new_status == PaymentStatus.SUCCESS else BookingStatus.FAILED
    )
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentInitiate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == payload.booking_id).first()
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    if booking.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this booking",
        )
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot pay for a booking with status {booking.status.value}",
        )

    payment = Payment(
        booking_id=booking.id,
        event_id=str(uuid.uuid4()),
        status=PaymentStatus.PENDING,
        amount=booking.amount,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    outcome = random.choice([PaymentStatus.SUCCESS, PaymentStatus.FAILED])
    return _apply_payment_result(payment, outcome, db)


@router.post("/webhook/", response_model=PaymentOut)
def payment_webhook(payload: WebhookPayload, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.event_id == payload.event_id).first()
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown payment event"
        )

    return _apply_payment_result(payment, payload.status, db)
