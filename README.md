# EVE Healthcare Diagnostic Booking Service

Backend service for diagnostic test bookings and simulated payments.
Built with FastAPI, PostgreSQL, SQLAlchemy and JWT-based auth.

Status: all core assignment requirements implemented and tested (auth,
diagnostic centres/tests, bookings, simulated payments, idempotent webhook).
38/38 pytest tests passing; `test.sh` end-to-end suite passing (33/33)
against a real Docker/Postgres deployment. Bonus engineering items are being
added incrementally — see `DECISIONS.md` for the reasoning behind every
design choice made along the way.

## Stack

- FastAPI
- PostgreSQL + SQLAlchemy (ORM) + Alembic (migrations)
- JWT auth via `python-jose`, password hashing via `passlib[bcrypt]`
- Docker + docker-compose for one-command local deployment

---

## Quick start for evaluators (Docker)

This is the fastest way to get the whole stack running, no local Python or
Postgres install required — only Docker.

```bash
git clone https://github.com/govind-sing/eve-diagnostic-booking
cd eve-diagnostic-booking

docker compose up --build -d
```

This builds the app image, starts Postgres, waits for it to be healthy, then
runs `alembic upgrade head` and starts the API automatically (see the `CMD`
in the `Dockerfile`). Give it a few seconds on first run.

```bash
# Confirm it's up
docker compose logs -f app
```

You should see all 4 Alembic migrations run, then Uvicorn start on
`http://0.0.0.0:8000`.

**Run the end-to-end test suite against the running stack:**

```bash
chmod +x test.sh
./test.sh
```

Expected output: `PASSED: 33   FAILED: 0`. This script exercises every
endpoint, every edge case listed in the assignment (invalid requests, repeated
webhook events, invalid booking IDs, failed payments, unauthorized access),
and the webhook idempotency guarantee specifically (same-status replay is a
no-op, conflicting-status replay does not corrupt state).

**Interactive API docs (Swagger UI):** `http://localhost:8000/docs`

**Tear down:**

```bash
docker compose down       # stop containers, keep the DB volume
docker compose down -v    # also wipe the DB volume (clean slate next run)
```

If port `8000` or `5432` is already in use on your machine, edit the `ports:`
mappings in `docker-compose.yml` (left side of the `:` is the host port).

---

## Running the pytest suite (no Docker needed)

A separate, faster pytest suite runs against a real SQLite database per test
(via a dependency override), so it needs nothing but Python — no Postgres,
no Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # or your preferred venv tool
pip install -r requirements-dev.txt
pytest -v
```

Expected output: `38 passed`.

Why two separate test suites: `pytest` is fast, isolated, and checks
application logic in detail (ownership rules, price snapshotting, idempotent
payment resolution, etc.) without needing infrastructure. `test.sh` is
slower but validates the *actual deployed stack* end-to-end over real HTTP,
against real Postgres, through real Alembic migrations — which is what
catches infrastructure-level issues pytest's SQLite backend can't (e.g. a
Postgres-specific enum migration bug was only caught this way).

---

## Manual setup (without Docker)

1. Create a PostgreSQL database (e.g. `eve_diagnostics`).
2. Copy `.env.example` to `.env` and fill in `DATABASE_URL` and `JWT_SECRET_KEY`:
```bash
   cp .env.example .env
```
3. Install dependencies:
```bash
   pip install -r requirements.txt
```
4. Run migrations:
```bash
   alembic upgrade head
```
5. Start the server:
```bash
   uvicorn app.main:app --reload
```
6. Interactive API docs: `http://localhost:8000/docs`
7. Run `./test.sh` against it the same way as the Docker setup above.

---

## API endpoints

### `POST /auth/signup`
Create a new user account.

Request:
```json
{ "email": "user@example.com", "password": "at-least-8-chars", "full_name": "Jane Doe", "role": "patient" }
```
`role` is optional, defaults to `"patient"`. Pass `"admin"` to create an
admin account for testing (see "Assumptions" below for why this is a
deliberate shortcut, not how a real system would provision admins).

Response `201`:
```json
{ "id": "uuid", "email": "user@example.com", "full_name": "Jane Doe", "role": "patient" }
```
`409` if the email is already registered. `422` on invalid email or a
password under 8 characters.

### `POST /auth/login`
Authenticate and receive a JWT.

Request:
```json
{ "email": "user@example.com", "password": "at-least-8-chars" }
```
Response `200`:
```json
{ "access_token": "...", "token_type": "bearer" }
```
`401` on invalid credentials.

All protected endpoints below expect `Authorization: Bearer <access_token>`.

### `GET /health`
Basic liveness check, no auth required.

### Diagnostic centres and tests (admin-managed)

Reads are public. Writes require a JWT belonging to a user with `role: admin`.

- `POST /centres/` (admin) — create a centre: `{ "name": "...", "location": "..." }`
- `GET /centres/` — list all centres, each with its nested `tests`
- `GET /centres/{centre_id}` — get one centre with its tests
- `PATCH /centres/{centre_id}` (admin) — partial update (`name` and/or `location`)
- `POST /centres/{centre_id}/tests` (admin) — add a test to a centre:
  `{ "name": "...", "price": 499.00 }`
- `GET /tests` (optional `?centre_id=`) — list tests, optionally filtered by centre
- `GET /tests/{test_id}` — get one test
- `PATCH /tests/{test_id}` (admin) — partial update (`name` and/or `price`)

Non-admin write attempts get `403`. Unknown centre/test IDs get `404`.

### Bookings (authenticated)

- `POST /bookings/` — book a test at a centre:
```json
  { "test_id": "uuid", "centre_id": "uuid", "appointment_datetime": "2026-10-05T10:00:00Z" }
```
  `amount` is snapshotted from the test's current price at booking time.
  `400` if the test isn't actually offered at the given centre. `404` if the
  test doesn't exist. `422` if `appointment_datetime` isn't in the future.
- `GET /bookings/` — list the current user's own bookings
- `GET /bookings/{booking_id}` — get one booking (owner or admin only, `403` otherwise)
- `POST /bookings/{booking_id}/cancel` — cancel a `PENDING` booking (owner or
  admin only). `409` if the booking isn't `PENDING` (already confirmed,
  failed, or cancelled).

### Payments (simulated) and webhook

- `POST /payments/` (authenticated, booking owner) — body: `{ "booking_id": "uuid" }`.
  Simulates calling a payment gateway: creates a `Payment` with a
  server-generated `event_id` (the idempotency key), randomly resolves to
  `SUCCESS` or `FAILED`, and updates the booking to `CONFIRMED` or `FAILED`
  accordingly. `409` if the booking isn't `PENDING` (e.g. already paid or
  cancelled). `403` if you don't own the booking.
- `POST /payments/webhook/` — body: `{ "event_id": "...", "status": "SUCCESS" | "FAILED" }`.
  Simulates the payment provider's asynchronous notification for the same
  event. **Idempotent**: `event_id` is unique at the database level, and the
  handler only applies a result to a payment that's still `PENDING`. A
  replayed webhook (same event, same or even a different status) is a no-op
  once the payment is already resolved, so it can never double-confirm a
  booking, re-fail an already-succeeded payment, or corrupt state. `404` if
  the `event_id` is unrecognized.

---

## Database schema

**users**
| column | type | notes |
|---|---|---|
| id | UUID (PK) | generated server-side |
| email | string, unique, indexed | |
| hashed_password | string | bcrypt hash, never the raw password |
| full_name | string, nullable | |
| role | enum: `admin`, `patient` | default `patient` |
| created_at | timestamp | server default `now()` |

**diagnostic_centres**
| column | type | notes |
|---|---|---|
| id | UUID (PK) | |
| name | string | |
| location | string | |
| created_at | timestamp | |

**diagnostic_tests**
| column | type | notes |
|---|---|---|
| id | UUID (PK) | |
| centre_id | UUID (FK -> diagnostic_centres.id) | cascade delete |
| name | string | |
| price | numeric(10,2) | |
| created_at | timestamp | |

**bookings**
| column | type | notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK -> users.id), indexed | |
| test_id | UUID (FK -> diagnostic_tests.id) | |
| centre_id | UUID (FK -> diagnostic_centres.id) | |
| appointment_datetime | timestamp | must be in the future at creation |
| amount | numeric(10,2) | snapshotted from the test's price at booking time |
| status | enum: `PENDING`, `CONFIRMED`, `FAILED`, `CANCELLED` | default `PENDING` |
| created_at | timestamp | |

**payments**
| column | type | notes |
|---|---|---|
| id | UUID (PK) | |
| booking_id | UUID (FK -> bookings.id) | |
| event_id | string, unique, indexed | idempotency key; simulates the provider's transaction reference |
| status | enum: `PENDING`, `SUCCESS`, `FAILED` | default `PENDING` |
| amount | numeric(10,2) | copied from the booking's (already-snapshotted) amount |
| created_at | timestamp | |

This is the full schema for the current scope of the assignment.

---

## Assumptions

- Email is the unique login identifier (no separate username).
- Passwords require a minimum of 8 characters; no additional complexity rules
  for a take-home assignment of this scope.
- JWTs are stateless (no server-side session/refresh-token store) since the
  assignment doesn't call for logout/refresh flows.
- **Admin provisioning**: `POST /auth/signup` accepts an optional `role` field
  (defaults to `patient`) so an admin account can be created without extra
  tooling for this assignment. In a real system, admin accounts would be
  provisioned out-of-band (invite flow, internal tool, or manual DB grant),
  not self-service at signup. Flagged in "what I'd improve" below.
- Deleting centres/tests isn't implemented yet, only create/update, since the
  assignment's edge cases focus on bookings and payments, not catalog deletion.
- **Price snapshotting**: a booking's `amount` is copied from the test's price
  at creation time and never recalculated, so a later admin price change
  doesn't retroactively alter an existing booking.
- **Cancellation** is only allowed while a booking is `PENDING` (i.e. before
  payment succeeds). Once `CONFIRMED`, cancelling would need refund logic,
  which is out of scope here.
- A booking requires `test_id` and `centre_id` to agree (the test must
  actually belong to that centre), since the assignment lists both as
  separate booking fields rather than deriving centre from test.
- **Payment idempotency**: `Payment.event_id` is unique at the database level
  and acts as the idempotency key. `POST /payments/` generates it (simulating
  a gateway issuing a transaction reference); `POST /payments/webhook/`
  receives it back. A payment is only ever resolved once, from `PENDING` to a
  terminal state, no matter how many times the webhook fires for that event
  or even if it later reports a conflicting status.
- **Webhook endpoint is unauthenticated**, matching how real payment provider
  webhooks work (no user JWT to attach). A real deployment would verify a
  provider-supplied signature header instead; noted under "what I'd improve".
- **`bcrypt` pinned to `4.0.1`** in `requirements.txt`. `passlib[bcrypt]==1.7.4`
  is incompatible with `bcrypt>=4.1` (a known upstream break: passlib's
  internal self-test crashes with a "password cannot be longer than 72 bytes"
  error unrelated to any actual password). Pinning avoids it entirely.
- **JWT subject is parsed into an actual `uuid.UUID`** before querying in
  `get_current_user` (`app/api/deps.py`), rather than comparing the column to
  the raw string from the token. Postgres's UUID type is lenient about
  string input so this worked there, but it's not portable (SQLite's UUID
  handling expects a real `uuid.UUID` and errors on a bare string) — found
  via the pytest suite, which runs against SQLite.

## What I'd improve with more time

- Refresh tokens / token revocation
- Rate limiting on login/signup to slow down credential-stuffing attempts
- Proper admin provisioning instead of a self-service `role` field at signup
- Soft-delete or delete endpoints for centres/tests
- Webhook signature verification (e.g. HMAC header) to confirm requests
  genuinely come from the payment provider
- Retry/backoff handling and dead-letter logging for webhook processing
- Pagination on list endpoints (`GET /centres/`, `GET /tests`)
- Structured (JSON) logging
- Redis caching for frequently-read, rarely-written data (centre/test catalog)