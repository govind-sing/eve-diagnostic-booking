# EVE Healthcare Diagnostic Booking Service

Backend service for diagnostic test bookings and simulated payments.
Built with FastAPI, PostgreSQL, SQLAlchemy and JWT-based auth.

Status: work in progress. This README is updated as each component is built.
See `DECISIONS.md` for the reasoning behind each design choice.

## Stack

- FastAPI
- PostgreSQL + SQLAlchemy (ORM) + Alembic (migrations)
- JWT auth via `python-jose`, password hashing via `passlib[bcrypt]`

## Running locally

1. Create a PostgreSQL database (e.g. `eve_diagnostics`).
2. Copy `.env.example` to `.env` and fill in `DATABASE_URL` and `JWT_SECRET_KEY`.
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run migrations:
   ```
   alembic upgrade head
   ```
5. Start the server:
   ```
   uvicorn app.main:app --reload
   ```
6. Interactive API docs: `http://localhost:8000/docs`

## Endpoints implemented so far

### `POST /auth/signup`
Create a new user account.

Request:
```json
{ "email": "user@example.com", "password": "at-least-8-chars", "full_name": "Jane Doe" }
```
Response `201`:
```json
{ "id": "uuid", "email": "user@example.com", "full_name": "Jane Doe" }
```
`409` if the email is already registered.

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

Protected endpoints (added later) expect `Authorization: Bearer <access_token>`.

### `GET /health`
Basic liveness check.

## Database schema so far

**users**
| column | type | notes |
|---|---|---|
| id | UUID (PK) | generated server-side |
| email | string, unique, indexed | |
| hashed_password | string | bcrypt hash, never the raw password |
| full_name | string, nullable | |
| created_at | timestamp | server default `now()` |

More tables (diagnostic centres, tests, bookings, payments) will be added as those
components are built.

## Assumptions made so far

- Email is the unique login identifier (no separate username).
- Passwords require a minimum of 8 characters; no additional complexity rules for
  a take-home assignment of this scope.
- JWTs are stateless (no server-side session/refresh-token store) since the
  assignment doesn't call for logout/refresh flows.

## What I'd improve with more time

(running list, updated as the project progresses)
- Refresh tokens / token revocation
- Rate limiting on login/signup to slow down credential-stuffing attempts
