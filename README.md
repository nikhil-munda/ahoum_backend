# Ahoum Events Platform

A Django REST Framework backend for an events platform with two roles — **Seeker** and **Facilitator** — supporting event creation, OTP-gated auth, search, and enrollment.

---

## Architecture

```
Django 4.2 LTS
├── djangorestframework          REST API layer
├── djangorestframework-simplejwt  JWT auth (access + refresh + blacklist)
├── django-filter                Search/filter for event listings
├── psycopg2-binary              PostgreSQL driver
├── python-decouple              12-factor env var management
└── celery[redis] + django-celery-beat  Scheduled mail (bonus)

PostgreSQL
└── Partial unique index on (event, seeker) WHERE status='enrolled'
    Allows re-enrollment after cancellation without storing duplicate rows.
```

### App layout

```
apps/
├── core/         Exception handler, pagination, permissions, utils
├── accounts/     Auth: User, UserProfile, OTP, JWT endpoints
└── events/       Event & Enrollment models, CRUD, search, enrollment
```

### Settings split

| File | Used for |
|---|---|
| `ahoum/settings/base.py` | Shared — DB, DRF, JWT, email, Celery |
| `ahoum/settings/local.py` | Development — `DEBUG=True`, console email |
| `ahoum/settings/production.py` | Production — security headers, SSL |

---

## Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis (optional — Celery scheduled mail)

### 1. Clone & create virtual environment

```bash
git clone <repo-url>
cd ahoum_backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values (see Environment Variables below)
```

### 3. Create PostgreSQL database

```bash
createuser -s postgres          # if the role doesn't exist
createdb -U postgres ahoum_db
```

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. Start development server

```bash
python manage.py runserver
```

API is available at `http://localhost:8000`.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Django secret key |
| `DEBUG` | No | `False` | Enable debug mode |
| `ALLOWED_HOSTS` | No | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DB_NAME` | No | `ahoum_db` | PostgreSQL database name |
| `DB_USER` | No | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | Yes | — | PostgreSQL password |
| `DB_HOST` | No | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `EMAIL_BACKEND` | No | `console.EmailBackend` | Django email backend |
| `EMAIL_HOST` | No | `smtp.gmail.com` | SMTP host |
| `EMAIL_PORT` | No | `587` | SMTP port |
| `EMAIL_USE_TLS` | No | `True` | Enable TLS |
| `EMAIL_HOST_USER` | No | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | No | — | SMTP password / app password |
| `DEFAULT_FROM_EMAIL` | No | `noreply@ahoum.com` | Sender address |
| `OTP_EXPIRY_MINUTES` | No | `5` | OTP TTL in minutes |
| `OTP_MAX_ATTEMPTS` | No | `5` | Max wrong OTP guesses |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis for Celery |

---

## Local Development

### Create a superuser

```bash
python manage.py createsuperuser
```

### Django Admin

Available at `http://localhost:8000/admin/`. Models registered: `User`, `UserProfile`, `OTPVerification`, `Event`, `Enrollment`.

### Email in development

`local.py` sets `EMAIL_BACKEND = console.EmailBackend`. OTP codes are printed to the terminal — no SMTP setup required.

To use a real SMTP backend locally, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` in `.env` and fill in the SMTP vars.

### Docker (optional)

```bash
docker-compose up --build
```

Services: `db` (PostgreSQL), `redis`, `web` (Django), `celery`.

---

## Migrations

```bash
# Apply all migrations
python manage.py migrate

# Create new migrations after model changes
python manage.py makemigrations

# Check for unapplied migrations
python manage.py migrate --check
```

---

## Running Tests

```bash
# All tests
pytest

# Verbose output (already default via pytest.ini)
pytest -v

# Single file
pytest tests/test_auth.py

# Single class or test
pytest tests/test_enrollment.py::TestEnroll::test_success_returns_201

# With coverage (requires pytest-cov)
pytest --cov=apps --cov-report=term-missing
```

Tests use PostgreSQL (same DB engine as production). Each test runs in a transaction that is rolled back on completion — no manual cleanup required.

---

## API Endpoints

### Auth

| Method | URL | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/signup/` | Public | Register; sends OTP |
| `POST` | `/auth/verify-email/` | Public | Submit OTP; enables login |
| `POST` | `/auth/login/` | Public | Returns `access` + `refresh` JWT |
| `POST` | `/auth/refresh/` | Public | Rotate refresh token |

### Events — Seeker

| Method | URL | Description |
|---|---|---|
| `GET` | `/events/` | Search upcoming events (filters: `location`, `language`, `starts_after`, `starts_before`, `q`) |
| `POST` | `/events/{id}/enroll/` | Enroll in event |
| `DELETE` | `/events/{id}/enroll/` | Cancel enrollment |
| `GET` | `/enrollments/upcoming/` | Active enrollments in future events |
| `GET` | `/enrollments/past/` | Active enrollments in ended events |

### Events — Facilitator

| Method | URL | Description |
|---|---|---|
| `POST` | `/events/` | Create event |
| `GET` | `/events/my/` | Own events with `total_enrollments` + `available_seats` |
| `GET` | `/events/{id}/` | Retrieve event detail |
| `PUT` | `/events/{id}/` | Full update (owner only) |
| `PATCH` | `/events/{id}/` | Partial update (owner only) |
| `DELETE` | `/events/{id}/` | Delete (owner only; blocked if active enrollments exist) |

### Response formats

**Success (list):**
```json
{ "count": 10, "next": "...", "previous": null, "results": [...] }
```

**Error:**
```json
{ "detail": "Human-readable message.", "code": "machine_readable_code" }
```

---

## Design Decisions

### Default Django User model + UserProfile

The requirements prohibit swapping `AUTH_USER_MODEL`. A `UserProfile` (OneToOne) stores `role` and `is_email_verified`. Every `User.save()` triggers a `post_save` signal that creates the profile with a default role; the signup serializer immediately overwrites the role. This adds one JOIN per auth check, mitigated by `select_related` on hot paths.

### `username = uuid4().hex` at signup

Django's `User.username` is required and must be unique, but the spec bans exposing it. Rather than using `email` as username (which risks a 150-char truncation on long emails), we generate a 32-char UUID hex. `EmailAuthBackend` looks up users by `email` only; `username` is never returned by any serializer.

### OTP plain-text storage

OTPs expire in 5 minutes and are limited to 5 attempts. Storing them as plain text avoids a hash-comparison round-trip per request. The attack window is tiny; hashing would be added for a stricter security posture.

### Partial unique index for Enrollment

`UniqueConstraint(fields=[event, seeker], condition=Q(status='enrolled'))` lets a seeker cancel and re-enroll without duplicate-row errors. Requires PostgreSQL — SQLite does not support partial indexes.

### `select_for_update()` in enrollment

All capacity and duplicate checks run inside `transaction.atomic()` with a row-level lock on the event. This eliminates the TOCTOU race where two concurrent requests both pass the capacity check but together overfill the event.

### Error shape `{ "detail", "code" }`

A global DRF exception handler in `core/exceptions.py` normalises all three response shapes DRF can produce (dict with `detail`, field-error dict, list) into a single flat shape. Permission classes carry a `code` attribute that DRF forwards to `PermissionDenied(code=...)`, which flows through the handler automatically.

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| UserProfile OneToOne | No model swap needed | Extra DB join on every auth check |
| UUID username | Clean separation of auth identity from business identity | Custom `EmailAuthBackend` required |
| Plain-text OTP | Simple, fast | Not suitable if longer TTL or DB exposure risk |
| Partial unique index | Re-enrollment without extra state tracking | PostgreSQL only |
| `select_for_update` on enroll | Correct under concurrent load | Serialises concurrent enrollments for the same event |
| role embedded in UserProfile | Simple RBAC | No role hierarchy; adding roles requires a migration |
| Celery + Redis for scheduled mail | Production-grade, scalable | Infrastructure overhead vs. APScheduler |
