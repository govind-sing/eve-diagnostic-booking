# Decision Log

## Step 1 — Project skeleton + Authentication

**What was built:**
- Project structure: `app/` package with `config`, `database`, `core` (security),
  `models`, `schemas`, `api/routes`.
- Settings loaded from environment via `pydantic-settings` (`app/config.py`).
- SQLAlchemy engine/session setup (`app/database.py`), declarative `Base`.
- `User` model: UUID primary key, unique indexed email, hashed password, optional
  full name, `created_at` timestamp.
- Password hashing with bcrypt (`passlib`), JWT issuing/decoding with `python-jose`
  (`app/core/security.py`).
- `POST /auth/signup` and `POST /auth/login` endpoints, plus a `get_current_user`
  dependency (`app/api/deps.py`) that later endpoints will use to enforce auth.
- Alembic wired to read the DB URL from app settings and pick up models
  automatically; initial migration creates the `users` table.

**Decisions made:**
- **ORM: SQLAlchemy** (over SQLModel) — user's explicit choice, more mature/explicit
  ecosystem and matches prior project experience.
- **UUID primary keys** over auto-increment integers — avoids leaking sequential
  user counts, and is the more common choice for public-facing resource IDs.
- **JWT is stateless** — no refresh token / session table for this iteration, since
  the assignment doesn't require logout or token revocation. Flagged as a
  "what I'd improve" item in the README.
- **Email as the login identifier** — no separate username field, simplest model
  that satisfies "user signup/login".
- Initial Alembic migration was **written by hand** rather than via
  `alembic revision --autogenerate`, since autogenerate needs a live DB connection
  which isn't available in this build environment. It mirrors the `User` model
  exactly; running `alembic upgrade head` against a real Postgres instance will
  apply it cleanly.

**Verified:** app imports cleanly, all routes register (`/auth/signup`,
`/auth/login`, `/health`, `/docs`).

**Open for discussion:** webhook idempotency strategy — deferred until we build
the payment webhook section, as agreed.

## Step 2 — Diagnostic Centres & Tests (admin-managed)

**What was built:**
- `role` column on `User` (`admin` / `patient`, default `patient`).
- `get_current_admin` dependency (`app/api/deps.py`), built on top of
  `get_current_user`, returning `403` for non-admins.
- `DiagnosticCentre` and `DiagnosticTest` models, one-to-many with cascade delete
  on the ORM relationship (`app/models/diagnostics.py`).
- Routes (`app/api/routes/centres.py`, `app/api/routes/tests.py`):
  - `POST /centres/`, `PATCH /centres/{id}` — admin only
  - `GET /centres/`, `GET /centres/{id}` — public, tests nested in the response
  - `POST /centres/{id}/tests` — admin only, creates a test under a centre
  - `GET /tests` (filterable by `centre_id`), `GET /tests/{id}` — public
  - `PATCH /tests/{id}` — admin only
- Migration `8d1c61ef2ba4`: adds the `user_role` enum + `role` column, creates
  `diagnostic_centres` and `diagnostic_tests`.

**Decisions made:**
- **Admin-managed, per user's choice** — role-gated writes rather than a
  seed-only/open catalog.
- **Reads are public, writes are admin-gated** — booking a test (next step)
  needs any authenticated user to browse centres/tests, so locking `GET` behind
  auth would add friction with no real benefit at this scope.
- **`role` accepted at signup, defaulting to `patient`** — simplest way to get an
  admin account for testing without extra tooling. Documented as a shortcut in
  the README; flagged as something to fix with proper admin provisioning in a
  real deployment.
- **PATCH over PUT** for updates — partial updates fit "change a price" or
  "rename a centre" better than requiring the full payload every time.
- **No delete endpoints yet** — the assignment's edge cases are about bookings
  and payment webhooks, not catalog deletion; left out to keep scope tight,
  noted in "what I'd improve".

**Verified:** app imports cleanly with all new routes registered; existing auth
routes unaffected.

## Step 3 — Booking system

**What was built:**
- `Booking` model: `user_id`, `test_id`, `centre_id`, `appointment_datetime`,
  `amount`, `status` (`PENDING`/`CONFIRMED`/`FAILED`/`CANCELLED`), `created_at`.
- `POST /bookings/` — validates the test exists and belongs to the given
  centre, snapshots `amount` from the test's current price, rejects
  non-future `appointment_datetime` (422 via Pydantic validator).
- `GET /bookings/` — current user's own bookings only.
- `GET /bookings/{id}` — owner or admin, `403` otherwise.
- `POST /bookings/{id}/cancel` — owner or admin, only from `PENDING`, `409`
  otherwise.
- Migration `ab0b4ce8351b`: `booking_status` enum + `bookings` table, indexed
  on `user_id`.

**Decisions made:**
- **Snapshot the price at booking time** (user's call) — a booking's `amount`
  is copied from the test's price when created and never recalculated, so an
  admin price change later doesn't alter a pending or completed booking.
- **`test_id` + `centre_id` must agree** — the assignment lists both as
  distinct booking fields, so a mismatch (test not actually offered at that
  centre) is a `400`, not silently ignored.
- **Ownership enforcement**: a plain `user_id` check plus an admin bypass,
  reused across `get`/`cancel` via one helper, rather than duplicating the
  check per route.
- **Cancellation only from `PENDING`** — once a payment has succeeded
  (`CONFIRMED`), cancelling would require refund handling, which is out of
  scope; documented as a deliberate limitation in the README.
- **Appointment must be in the future** — caught at the schema level with a
  Pydantic validator rather than in the route, so it fails fast with a clear
  `422` before touching the database.

**Verified:** app imports cleanly with all booking routes registered
alongside auth, centres, and tests.

## Step 4 — Payment service and idempotent webhook

**What was built:**
- `Payment` model: `booking_id`, `event_id` (unique, the idempotency key),
  `status` (`PENDING`/`SUCCESS`/`FAILED`), `amount`, `created_at`.
- `_apply_payment_result(payment, new_status, db)` — the single function that
  moves a payment from `PENDING` to a terminal state and syncs the booking
  (`CONFIRMED` on `SUCCESS`, `FAILED` on `FAILED`). It's a no-op if the
  payment is already terminal, whatever status is passed in.
- `POST /payments/` — booking owner only, `409` if the booking isn't
  `PENDING`. Creates a `Payment` with a server-generated `event_id`, then
  immediately calls `_apply_payment_result` with a random `SUCCESS`/`FAILED`
  outcome to simulate the gateway's synchronous response.
- `POST /payments/webhook/` — looks up the payment by `event_id` (`404` if
  unknown), then calls the same `_apply_payment_result`. Matches the
  assignment's exact path.
- Migration `97d4ff5740cf`: `payment_status` enum + `payments` table with a
  unique index on `event_id`.

**Decisions made:**
- **Idempotency key on a unique column** (user's call) over a booking-status
  check — `event_id` is unique at the database level, so even a race between
  two concurrent identical webhook deliveries can't both "win"; the shared
  resolver function is what prevents a conflicting second delivery from
  altering an already-resolved payment.
- **One shared resolver for both the synchronous payment call and the
  webhook** — rather than duplicating the SUCCESS/FAILED handling logic in
  two places, `POST /payments/` and `POST /payments/webhook/` both go through
  `_apply_payment_result`. This guarantees identical idempotency behavior
  regardless of which path a given event's outcome comes through, and there
  is exactly one place that can transition a booking based on a payment
  result.
- **Conflicting replay is silently ignored, not rejected with an error** —
  if a webhook reports a different status than what's already recorded, the
  existing terminal state wins and the call still returns `200` with the
  actual current state. This avoids the webhook sender interpreting an error
  response as "retry me," which could otherwise turn into a retry loop.
- **Webhook left unauthenticated** — no JWT applies to a server-to-server
  callback with no user context; flagged in the README that a real system
  would verify a provider signature instead.
- **`POST /payments/webhook/` path matches the assignment exactly** (trailing
  slash included), verified by inspecting the app's registered routes
  directly rather than assuming FastAPI's default redirect behavior would
  paper over a mismatch.

**Verified:** app imports cleanly with all payment routes registered at the
exact spec'd paths. Ran the idempotency logic in isolation against an
in-memory database: first resolution applies correctly, a replay with the
same status is a no-op, a replay with a conflicting status does not alter the
already-resolved payment or booking, and a duplicate `event_id` insert is
rejected by the unique constraint.

## Step 5 — Fixing bugs found on first real end-to-end run

With Docker unavailable in my own environment, I installed Postgres directly
and ran the actual app against it for the first time here, then had the user
run `docker compose up` + `test.sh` on their machine. Two real bugs surfaced:

1. **`test.sh` failed entirely on macOS's default bash 3.2** — expanding an
   empty array (`"${auth_header[@]}"`) under `set -u` is a known bash <4.4
   bug ("unbound variable"). Fixed by building the curl invocation as
   conditional branches instead of an array, and dropping `set -u`/`set -e`
   entirely (the script is meant to run every check and report a full
   summary, not abort on the first failure).
2. **`POST /auth/signup` returned 500** — two independent causes, both real:
   - SQLAlchemy's `Enum` type sends a Python enum member's **name** to the
     database by default, not its **value**. `BookingStatus`/`PaymentStatus`
     happened to work because their member names equal their values
     (`PENDING = "PENDING"`), but `UserRole` didn't (`ADMIN = "admin"`), so
     every insert tried `'ADMIN'`/`'PATIENT'` against a Postgres enum that
     only accepts `'admin'`/`'patient'`. Fixed with `values_callable` on the
     `role` column in `app/models/user.py`.
   - `passlib[bcrypt]==1.7.4` is incompatible with `bcrypt>=4.1` (an upstream
     compatibility break: passlib's internal self-test throws a "password
     cannot be longer than 72 bytes" error that has nothing to do with the
     actual password). Fixed by pinning `bcrypt==4.0.1` in `requirements.txt`.

**Verified:** ran the full `test.sh` suite against a real Postgres instance
(not sqlite) five times in a row after both fixes — 33/33 checks pass every
time, including both branches of the random payment outcome (`SUCCESS` and
`FAILED`).

**Also caught and fixed earlier (before handing off Docker files):** the
`booking_status`/`payment_status` Alembic migrations were calling
`.create(checkfirst=True)` on the enum type explicitly, and then
`op.create_table` tried to create the same type again unconditionally,
causing `DuplicateObject` errors. Fixed by removing the redundant explicit
call for `create_table`-based migrations (the table creation creates the type
once, correctly); the `add_column`-based migration (`user_role`) still needs
the explicit call, since `add_column` does not auto-create enum types the way
`create_table` does.

## Step 6 — pytest suite (the graded "Tests" line item)

**What was built:** `tests/` — a pytest suite using FastAPI's `TestClient`
against a real SQLite database (one fresh file per test, via a `get_db`
dependency override), separate from `test.sh`'s HTTP-level smoke test against
a running instance.

- `tests/conftest.py` — `db_session`/`client` fixtures, plus shared
  `admin_token`/`patient_token`/`other_patient_token`/`centre_and_test`
  fixtures reused across modules.
- `tests/test_auth.py` — signup defaults/roles, duplicate email, password
  length, invalid email, login success/failure.
- `tests/test_centres_and_tests.py` — admin-only writes, public reads, 404s,
  price/location updates, filtering.
- `tests/test_bookings.py` — booking creation, past-date rejection,
  test/centre mismatch, ownership enforcement, cancellation states, **and a
  dedicated test that an admin price change after booking does not alter the
  booking's snapshotted `amount`** (directly verifies the Step 3 decision).
- `tests/test_payments.py` — both payment outcomes (gateway randomness
  patched deterministic via `monkeypatch`), the idempotent webhook (same
  status is a no-op, conflicting status doesn't corrupt state), unknown
  event 404, and a test hitting the underlying unique constraint on
  `event_id` directly, independent of the route-level logic.
- `requirements-dev.txt` (`-r requirements.txt` + `pytest`, `httpx`) and
  `pytest.ini` (`pythonpath = .`) so `app`/`tests` resolve regardless of
  where pytest is invoked from.

**A real bug this caught:** `get_current_user` (`app/api/deps.py`) compared
`User.id == user_id` where `user_id` was the raw string from the JWT's `sub`
claim, not a `uuid.UUID`. Postgres's UUID column accepts a plain string
directly, so this worked fine in every manual/`test.sh` run against real
Postgres — but SQLite's UUID handling requires an actual `uuid.UUID` object
and throws `AttributeError: 'str' object has no attribute 'hex'` on a bare
string. This was a genuine portability bug in the code, not a testing
artifact. Fixed by explicitly parsing the JWT subject into a `uuid.UUID`
(with a `401`, not a `500`, on a malformed value) before querying. Also fixed
the same class of bug in `test_duplicate_event_id_rejected_at_db_level`
itself (comparing `Booking.id` to a raw JSON string).

**Decisions made:**
- **SQLite over a second Postgres instance for pytest** — keeps the unit
  test suite fast and dependency-free (no Docker/Postgres required to run
  `pytest`), while `test.sh` remains the real-Postgres, real-deployment
  check. The tradeoff: SQLite doesn't enforce the Postgres-specific `ENUM`
  types or catch Postgres-only SQL issues, which is exactly why `test.sh`
  against the actual Docker stack still matters as a separate check — and
  is exactly how the `get_current_user` bug above surfaced despite `test.sh`
  passing 33/33 against Postgres.
- **`monkeypatch` on `random.choice`** for payment tests, rather than
  running many iterations and hoping to see both outcomes — deterministic
  and explicit about which branch each test covers.
- **A dedicated price-snapshot test** rather than relying on `test.sh` or
  manual inspection — this decision (Step 3) has no other automated
  coverage otherwise, and it's exactly the kind of regression a future
  change could silently reintroduce.

**Verified:** `pytest -v` → 38 passed. Also reran `test.sh` against real
Postgres after the `deps.py` fix → still 33/33, confirming the fix changes
nothing about Postgres behavior.

One follow-up: the first attempt to hand off the `deps.py` fix used a partial
diff instead of the full file, and the same raw-string-vs-`uuid.UUID` bug was
still present in `test_duplicate_event_id_rejected_at_db_level` itself
(comparing `Booking.id` to a raw JSON string, not the app code). Fixed by
wrapping the JSON id in `UUID(...)` before the query, and confirmed
independently on the actual project machine (not just this build
environment): `pytest -v` → **38 passed, 0 failed**. Lesson applied going
forward: hand off full files, not diffs, whenever a change touches more than
one line.