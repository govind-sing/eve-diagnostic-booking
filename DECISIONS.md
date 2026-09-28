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

### Payment Resolution & Idempotency

Key design: one shared `_apply_payment_result` function handles both the synchronous "gateway response" in `POST /payments/` and the async `POST /payments/webhook/`.

It only mutates state when the payment is still `PENDING` — so a replayed webhook, even with a conflicting status, is a guaranteed no-op.

`event_id` also has a unique DB constraint, so two truly concurrent duplicate deliveries can't both slip through.

I stress-tested that resolver against an in-memory DB before writing this up:

- First resolution applies correctly.
- Same-status replay is a no-op.
- Conflicting-status replay leaves the original result untouched.
- A duplicate `event_id` insert is rejected outright by the unique constraint.