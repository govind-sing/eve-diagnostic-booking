from datetime import datetime, timedelta, timezone
from uuid import UUID

import app.api.routes.payments as payments_module
from app.models.payment import PaymentStatus
from tests.conftest import auth_headers


def future_iso(days=3):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def make_booking(client, token, test_id, centre_id):
    return client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_datetime": future_iso(),
        },
        headers=auth_headers(token),
    ).json()


def force_gateway_outcome(monkeypatch, outcome: PaymentStatus):
    """The gateway simulation is random.choice([...]); pin it for a
    deterministic test instead of leaving the outcome to chance."""
    monkeypatch.setattr(payments_module.random, "choice", lambda seq: outcome)


def test_successful_payment_confirms_booking(
    client, patient_token, centre_and_test, monkeypatch
):
    force_gateway_outcome(monkeypatch, PaymentStatus.SUCCESS)
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )

    resp = client.post(
        "/payments/",
        json={"booking_id": booking["id"]},
        headers=auth_headers(patient_token),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "SUCCESS"

    booking_after = client.get(
        f"/bookings/{booking['id']}", headers=auth_headers(patient_token)
    ).json()
    assert booking_after["status"] == "CONFIRMED"


def test_failed_payment_fails_booking(
    client, patient_token, centre_and_test, monkeypatch
):
    force_gateway_outcome(monkeypatch, PaymentStatus.FAILED)
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )

    resp = client.post(
        "/payments/",
        json={"booking_id": booking["id"]},
        headers=auth_headers(patient_token),
    )
    assert resp.json()["status"] == "FAILED"

    booking_after = client.get(
        f"/bookings/{booking['id']}", headers=auth_headers(patient_token)
    ).json()
    assert booking_after["status"] == "FAILED"


def test_cannot_pay_for_a_non_pending_booking_again(
    client, patient_token, centre_and_test, monkeypatch
):
    force_gateway_outcome(monkeypatch, PaymentStatus.SUCCESS)
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )
    client.post(
        "/payments/",
        json={"booking_id": booking["id"]},
        headers=auth_headers(patient_token),
    )

    resp = client.post(
        "/payments/",
        json={"booking_id": booking["id"]},
        headers=auth_headers(patient_token),
    )
    assert resp.status_code == 409


def test_other_patient_cannot_pay_for_someone_elses_booking(
    client, patient_token, other_patient_token, centre_and_test
):
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )
    resp = client.post(
        "/payments/",
        json={"booking_id": booking["id"]},
        headers=auth_headers(other_patient_token),
    )
    assert resp.status_code == 403


def test_webhook_replay_with_same_status_is_idempotent_noop(
    client, patient_token, centre_and_test, monkeypatch
):
    force_gateway_outcome(monkeypatch, PaymentStatus.SUCCESS)
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )
    payment = client.post(
        "/payments/",
        json={"booking_id": booking["id"]},
        headers=auth_headers(patient_token),
    ).json()

    resp = client.post(
        "/payments/webhook/",
        json={"event_id": payment["event_id"], "status": "SUCCESS"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESS"

    booking_after = client.get(
        f"/bookings/{booking['id']}", headers=auth_headers(patient_token)
    ).json()
    assert booking_after["status"] == "CONFIRMED"


def test_webhook_replay_with_conflicting_status_does_not_corrupt_state(
    client, patient_token, centre_and_test, monkeypatch
):
    force_gateway_outcome(monkeypatch, PaymentStatus.SUCCESS)
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )
    payment = client.post(
        "/payments/",
        json={"booking_id": booking["id"]},
        headers=auth_headers(patient_token),
    ).json()

    # A conflicting, out-of-order/duplicate delivery claiming FAILED. Must
    # not flip an already-CONFIRMED booking to FAILED.
    resp = client.post(
        "/payments/webhook/",
        json={"event_id": payment["event_id"], "status": "FAILED"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESS", "payment must remain resolved to SUCCESS"

    booking_after = client.get(
        f"/bookings/{booking['id']}", headers=auth_headers(patient_token)
    ).json()
    assert booking_after["status"] == "CONFIRMED", "booking must not flip to FAILED"


def test_webhook_unknown_event_id_returns_404(client):
    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "does-not-exist", "status": "SUCCESS"},
    )
    assert resp.status_code == 404


def test_duplicate_event_id_rejected_at_db_level(
    client, patient_token, centre_and_test, monkeypatch, db_session
):
    """Belt-and-suspenders check on the actual idempotency mechanism: the
    unique constraint on Payment.event_id, independent of the application
    logic tested above."""
    from app.models.booking import Booking
    from app.models.payment import Payment

    force_gateway_outcome(monkeypatch, PaymentStatus.SUCCESS)
    booking_resp = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )
    payment = client.post(
        "/payments/",
        json={"booking_id": booking_resp["id"]},
        headers=auth_headers(patient_token),
    ).json()

    session = db_session()
    try:
        booking = session.query(Booking).filter(Booking.id == UUID(booking_resp["id"])).one()
        dup = Payment(
            booking_id=booking.id,
            event_id=payment["event_id"],
            status=PaymentStatus.PENDING,
            amount=booking.amount,
        )
        session.add(dup)
        raised = False
        try:
            session.commit()
        except Exception:
            raised = True
            session.rollback()
        assert raised, "duplicate event_id must be rejected by the unique constraint"
    finally:
        session.close()