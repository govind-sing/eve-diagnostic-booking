import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.diagnostics import DiagnosticTest
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _get_owned_booking_or_404(
    booking_id: uuid.UUID, user: User, db: Session
) -> Booking:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )
    if booking.user_id != user.id and user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this booking",
        )
    return booking


@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    test = (
        db.query(DiagnosticTest)
        .filter(DiagnosticTest.id == payload.test_id)
        .first()
    )
    if test is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic test not found"
        )
    if test.centre_id != payload.centre_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This test is not offered at the given diagnostic centre",
        )

    booking = Booking(
        user_id=user.id,
        test_id=test.id,
        centre_id=payload.centre_id,
        appointment_datetime=payload.appointment_datetime,
        amount=test.price,  # snapshot: later price changes won't affect this booking
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/", response_model=list[BookingOut])
def list_my_bookings(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return db.query(Booking).filter(Booking.user_id == user.id).all()


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _get_owned_booking_or_404(booking_id, user, db)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = _get_owned_booking_or_404(booking_id, user, db)
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel a booking with status {booking.status.value}",
        )
    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking
