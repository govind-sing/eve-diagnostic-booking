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
