from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers


def future_iso(days=3):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def past_iso(days=1):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def make_booking(client, token, test_id, centre_id, when=None):
    return client.post(
        "/bookings/",
        json={
            "test_id": test_id,
            "centre_id": centre_id,
            "appointment_datetime": when or future_iso(),
        },
        headers=auth_headers(token),
    )


def test_patient_can_book_a_test(client, patient_token, centre_and_test):
    resp = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PENDING"
    assert float(body["amount"]) == 499.00


def test_booking_rejects_past_appointment(client, patient_token, centre_and_test):
    resp = make_booking(
        client,
        patient_token,
        centre_and_test["test_id"],
        centre_and_test["centre_id"],
        when=past_iso(),
    )
    assert resp.status_code == 422


def test_booking_requires_test_to_belong_to_given_centre(
    client, admin_token, patient_token, centre_and_test
):
    # A second, unrelated centre. The original test_id does not belong to it.
    other_centre = client.post(
        "/centres/",
        json={"name": "Other Centre", "location": "Bhopal"},
        headers=auth_headers(admin_token),
    ).json()

    resp = make_booking(
        client, patient_token, centre_and_test["test_id"], other_centre["id"]
    )
    assert resp.status_code == 400


def test_booking_unknown_test_returns_404(client, patient_token, centre_and_test):
    resp = make_booking(
        client,
        patient_token,
        "00000000-0000-0000-0000-000000000000",
        centre_and_test["centre_id"],
    )
    assert resp.status_code == 404


def test_price_change_does_not_affect_existing_booking(
    client, admin_token, patient_token, centre_and_test
):
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    ).json()
    assert float(booking["amount"]) == 499.00

    # Admin raises the price after the booking already exists.
    client.patch(
        f"/tests/{centre_and_test['test_id']}",
        json={"price": 999.00},
        headers=auth_headers(admin_token),
    )

    refetched = client.get(
        f"/bookings/{booking['id']}", headers=auth_headers(patient_token)
    ).json()
    assert float(refetched["amount"]) == 499.00, "booking amount must stay snapshotted"


def test_owner_can_view_own_booking(client, patient_token, centre_and_test):
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    ).json()
    resp = client.get(f"/bookings/{booking['id']}", headers=auth_headers(patient_token))
    assert resp.status_code == 200


def test_other_patient_cannot_view_booking(
    client, patient_token, other_patient_token, centre_and_test
):
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    ).json()
    resp = client.get(
        f"/bookings/{booking['id']}", headers=auth_headers(other_patient_token)
    )
    assert resp.status_code == 403


def test_unauthenticated_cannot_view_booking(client, patient_token, centre_and_test):
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    ).json()
    resp = client.get(f"/bookings/{booking['id']}")
    assert resp.status_code == 401


def test_unknown_booking_returns_404(client, patient_token):
    resp = client.get(
        "/bookings/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(patient_token),
    )
    assert resp.status_code == 404


def test_owner_can_cancel_pending_booking(client, patient_token, centre_and_test):
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    ).json()
    resp = client.post(
        f"/bookings/{booking['id']}/cancel", headers=auth_headers(patient_token)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_cancelling_an_already_cancelled_booking_conflicts(
    client, patient_token, centre_and_test
):
    booking = make_booking(
        client, patient_token, centre_and_test["test_id"], centre_and_test["centre_id"]
    ).json()
    client.post(f"/bookings/{booking['id']}/cancel", headers=auth_headers(patient_token))
    resp = client.post(
        f"/bookings/{booking['id']}/cancel", headers=auth_headers(patient_token)
    )
    assert resp.status_code == 409
