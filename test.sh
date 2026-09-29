#!/usr/bin/env bash
# End-to-end smoke test for the EVE Healthcare diagnostic booking service.
# Assumes the API is already running (e.g. `docker compose up`) at BASE_URL.
#
# Usage: ./test.sh [base_url]
#   ./test.sh                       # defaults to http://localhost:8000
#   ./test.sh http://localhost:9000

# Deliberately no `set -e`/`set -u` here: we want the script to run every
# check and report a full pass/fail summary, not abort on the first failure
# or on the empty-array quirk in macOS's default bash 3.2.
BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

# --- helpers ---------------------------------------------------------------

expect_status() {
  local description="$1" expected="$2" method="$3" path="$4" data="${5:-}" token="${6:-}"

  local http_code
  if [ -n "$token" ] && [ -n "$data" ]; then
    http_code=$(curl -sS -o /tmp/resp_body.$$ -w "%{http_code}" -X "$method" \
      -H "Content-Type: application/json" -H "Authorization: Bearer $token" \
      -d "$data" "$BASE_URL$path")
  elif [ -n "$token" ]; then
    http_code=$(curl -sS -o /tmp/resp_body.$$ -w "%{http_code}" -X "$method" \
      -H "Authorization: Bearer $token" "$BASE_URL$path")
  elif [ -n "$data" ]; then
    http_code=$(curl -sS -o /tmp/resp_body.$$ -w "%{http_code}" -X "$method" \
      -H "Content-Type: application/json" -d "$data" "$BASE_URL$path")
  else
    http_code=$(curl -sS -o /tmp/resp_body.$$ -w "%{http_code}" -X "$method" "$BASE_URL$path")
  fi
  RESPONSE_BODY=$(cat /tmp/resp_body.$$ 2>/dev/null || echo "")
  rm -f /tmp/resp_body.$$

  if [ "$http_code" == "$expected" ]; then
    echo "PASS: $description (got $http_code)"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $description (expected $expected, got $http_code) -> $RESPONSE_BODY"
    FAIL=$((FAIL + 1))
  fi
}

json_field() {
  python3 -c "
import sys, json
try:
    print(json.loads(sys.argv[1])[sys.argv[2]])
except Exception:
    pass
" "$1" "$2"
}

RAND=$RANDOM$RANDOM

echo "== Health check =="
expect_status "GET /health" 200 GET "/health"

echo
echo "== Auth: signup + login =="
ADMIN_EMAIL="admin_${RAND}@example.com"
PATIENT_EMAIL="patient_${RAND}@example.com"
OTHER_EMAIL="other_${RAND}@example.com"
PASSWORD="supersecret123"

expect_status "signup admin" 201 POST "/auth/signup" \
  "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\",\"role\":\"admin\"}"
expect_status "signup patient" 201 POST "/auth/signup" \
  "{\"email\":\"$PATIENT_EMAIL\",\"password\":\"$PASSWORD\"}"
expect_status "signup second patient (other)" 201 POST "/auth/signup" \
  "{\"email\":\"$OTHER_EMAIL\",\"password\":\"$PASSWORD\"}"
expect_status "duplicate signup rejected" 409 POST "/auth/signup" \
  "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\"}"
expect_status "signup with short password rejected" 422 POST "/auth/signup" \
  "{\"email\":\"short_${RAND}@example.com\",\"password\":\"short\"}"

expect_status "login admin" 200 POST "/auth/login" \
  "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\"}"
ADMIN_TOKEN=$(json_field "$RESPONSE_BODY" access_token)

expect_status "login patient" 200 POST "/auth/login" \
  "{\"email\":\"$PATIENT_EMAIL\",\"password\":\"$PASSWORD\"}"
PATIENT_TOKEN=$(json_field "$RESPONSE_BODY" access_token)

expect_status "login other patient" 200 POST "/auth/login" \
  "{\"email\":\"$OTHER_EMAIL\",\"password\":\"$PASSWORD\"}"
OTHER_TOKEN=$(json_field "$RESPONSE_BODY" access_token)

expect_status "login with wrong password rejected" 401 POST "/auth/login" \
  "{\"email\":\"$PATIENT_EMAIL\",\"password\":\"wrongpassword\"}"

echo
echo "== Diagnostic centres & tests (admin-managed) =="
expect_status "non-admin cannot create centre" 403 POST "/centres/" \
  "{\"name\":\"Rogue Centre\",\"location\":\"Nowhere\"}" "$PATIENT_TOKEN"

expect_status "admin creates centre" 201 POST "/centres/" \
  "{\"name\":\"City Diagnostics\",\"location\":\"Indore\"}" "$ADMIN_TOKEN"
CENTRE_ID=$(json_field "$RESPONSE_BODY" id)

expect_status "admin adds test to centre" 201 POST "/centres/$CENTRE_ID/tests" \
  "{\"name\":\"Complete Blood Count\",\"price\":499.00}" "$ADMIN_TOKEN"
TEST_ID=$(json_field "$RESPONSE_BODY" id)

expect_status "public can list centres" 200 GET "/centres/"
expect_status "public can get one centre" 200 GET "/centres/$CENTRE_ID"
expect_status "get unknown centre returns 404" 404 GET "/centres/00000000-0000-0000-0000-000000000000"

echo
echo "== Bookings =="
FUTURE_DATE=$(python3 -c "from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc)+timedelta(days=3)).isoformat())")
PAST_DATE=$(python3 -c "from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc)-timedelta(days=1)).isoformat())")

expect_status "booking with past appointment rejected" 422 POST "/bookings/" \
  "{\"test_id\":\"$TEST_ID\",\"centre_id\":\"$CENTRE_ID\",\"appointment_datetime\":\"$PAST_DATE\"}" "$PATIENT_TOKEN"

expect_status "patient books a test" 201 POST "/bookings/" \
  "{\"test_id\":\"$TEST_ID\",\"centre_id\":\"$CENTRE_ID\",\"appointment_datetime\":\"$FUTURE_DATE\"}" "$PATIENT_TOKEN"
BOOKING_ID=$(json_field "$RESPONSE_BODY" id)
BOOKING_AMOUNT=$(json_field "$RESPONSE_BODY" amount)
echo "  booking amount snapshotted at: $BOOKING_AMOUNT"

expect_status "other patient cannot view this booking" 403 GET "/bookings/$BOOKING_ID" "" "$OTHER_TOKEN"
expect_status "owner can view their booking" 200 GET "/bookings/$BOOKING_ID" "" "$PATIENT_TOKEN"
expect_status "get unknown booking returns 404" 404 GET "/bookings/00000000-0000-0000-0000-000000000000" "" "$PATIENT_TOKEN"
expect_status "unauthenticated request rejected" 401 GET "/bookings/$BOOKING_ID"

expect_status "patient books a second test (for cancel test)" 201 POST "/bookings/" \
  "{\"test_id\":\"$TEST_ID\",\"centre_id\":\"$CENTRE_ID\",\"appointment_datetime\":\"$FUTURE_DATE\"}" "$PATIENT_TOKEN"
BOOKING_ID_2=$(json_field "$RESPONSE_BODY" id)

expect_status "owner cancels a PENDING booking" 200 POST "/bookings/$BOOKING_ID_2/cancel" "" "$PATIENT_TOKEN"
expect_status "cancelling an already-cancelled booking is rejected" 409 POST "/bookings/$BOOKING_ID_2/cancel" "" "$PATIENT_TOKEN"

echo
echo "== Payments + idempotent webhook =="
expect_status "patient initiates payment" 201 POST "/payments/" \
  "{\"booking_id\":\"$BOOKING_ID\"}" "$PATIENT_TOKEN"
EVENT_ID=$(json_field "$RESPONSE_BODY" event_id)
PAYMENT_STATUS=$(json_field "$RESPONSE_BODY" status)
echo "  simulated gateway outcome: $PAYMENT_STATUS"

expect_status "booking status reflects payment outcome" 200 GET "/bookings/$BOOKING_ID" "" "$PATIENT_TOKEN"
BOOKING_STATUS_AFTER_PAY=$(json_field "$RESPONSE_BODY" status)
echo "  booking status after payment: $BOOKING_STATUS_AFTER_PAY"

expect_status "cannot pay for a non-PENDING booking again" 409 POST "/payments/" \
  "{\"booking_id\":\"$BOOKING_ID\"}" "$PATIENT_TOKEN"

expect_status "webhook replay with SAME status is accepted (idempotent no-op)" 200 POST "/payments/webhook/" \
  "{\"event_id\":\"$EVENT_ID\",\"status\":\"$PAYMENT_STATUS\"}"

OPPOSITE_STATUS="SUCCESS"
[ "$PAYMENT_STATUS" == "SUCCESS" ] && OPPOSITE_STATUS="FAILED"
expect_status "webhook replay with CONFLICTING status still returns 200 (ignored, not applied)" 200 POST "/payments/webhook/" \
  "{\"event_id\":\"$EVENT_ID\",\"status\":\"$OPPOSITE_STATUS\"}"

expect_status "booking status did NOT change after conflicting replay" 200 GET "/bookings/$BOOKING_ID" "" "$PATIENT_TOKEN"
BOOKING_STATUS_AFTER_REPLAY=$(json_field "$RESPONSE_BODY" status)
if [ "$BOOKING_STATUS_AFTER_REPLAY" == "$BOOKING_STATUS_AFTER_PAY" ]; then
  echo "PASS: booking status unchanged by conflicting webhook replay ($BOOKING_STATUS_AFTER_REPLAY)"
  PASS=$((PASS + 1))
else
  echo "FAIL: booking status changed from $BOOKING_STATUS_AFTER_PAY to $BOOKING_STATUS_AFTER_REPLAY after a replay!"
  FAIL=$((FAIL + 1))
fi

expect_status "webhook with unknown event_id returns 404" 404 POST "/payments/webhook/" \
  "{\"event_id\":\"nonexistent-event-id\",\"status\":\"SUCCESS\"}"

echo
echo "======================================"
echo "  PASSED: $PASS   FAILED: $FAIL"
echo "======================================"
[ "$FAIL" -eq 0 ]