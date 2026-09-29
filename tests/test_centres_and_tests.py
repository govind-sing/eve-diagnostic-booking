from tests.conftest import auth_headers


def test_non_admin_cannot_create_centre(client, patient_token):
    resp = client.post(
        "/centres/",
        json={"name": "Rogue Centre", "location": "Nowhere"},
        headers=auth_headers(patient_token),
    )
    assert resp.status_code == 403


def test_unauthenticated_cannot_create_centre(client):
    resp = client.post(
        "/centres/", json={"name": "Rogue Centre", "location": "Nowhere"}
    )
    assert resp.status_code == 401


def test_admin_can_create_centre_and_test(client, admin_token):
    centre_resp = client.post(
        "/centres/",
        json={"name": "City Diagnostics", "location": "Indore"},
        headers=auth_headers(admin_token),
    )
    assert centre_resp.status_code == 201
    centre_id = centre_resp.json()["id"]

    test_resp = client.post(
        f"/centres/{centre_id}/tests",
        json={"name": "CBC", "price": 499.00},
        headers=auth_headers(admin_token),
    )
    assert test_resp.status_code == 201
    assert test_resp.json()["centre_id"] == centre_id


def test_public_can_list_centres_with_nested_tests(client, centre_and_test):
    resp = client.get("/centres/")
    assert resp.status_code == 200
    centres = resp.json()
    assert len(centres) == 1
    assert len(centres[0]["tests"]) == 1


def test_public_can_get_one_centre(client, centre_and_test):
    resp = client.get(f"/centres/{centre_and_test['centre_id']}")
    assert resp.status_code == 200


def test_get_unknown_centre_returns_404(client):
    resp = client.get("/centres/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_non_admin_cannot_add_test_to_centre(client, patient_token, centre_and_test):
    resp = client.post(
        f"/centres/{centre_and_test['centre_id']}/tests",
        json={"name": "MRI", "price": 3000},
        headers=auth_headers(patient_token),
    )
    assert resp.status_code == 403


def test_admin_can_update_centre(client, admin_token, centre_and_test):
    resp = client.patch(
        f"/centres/{centre_and_test['centre_id']}",
        json={"location": "Bhopal"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["location"] == "Bhopal"


def test_admin_can_update_test_price(client, admin_token, centre_and_test):
    resp = client.patch(
        f"/tests/{centre_and_test['test_id']}",
        json={"price": 599.00},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    assert float(resp.json()["price"]) == 599.00


def test_list_tests_filtered_by_centre(client, centre_and_test):
    resp = client.get(f"/tests?centre_id={centre_and_test['centre_id']}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
