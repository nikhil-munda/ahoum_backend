# Ahoum Events Platform — Backend API

A production-ready REST API for an events platform with two roles: **facilitators** who create and manage events, and **seekers** who discover and enroll in them. Built with Django, Django REST Framework, PostgreSQL, Celery, and Redis.

---

## Project Overview

Ahoum is a role-based event management system. The backend exposes a JSON API covering:

- Email + OTP two-step signup with role assignment
- JWT-based authentication with rotating refresh tokens
- Full event lifecycle (create, browse, update, delete)
- Capacity-controlled, race-condition-safe enrollment
- Automated follow-up and reminder emails via Celery

---

## Features

| Feature | Details |
|---|---|
| Email + OTP signup | 6-digit cryptographically secure OTP; configurable expiry and attempt limit |
| Role-based access control | `seeker` browses and enrolls; `facilitator` creates and manages events |
| JWT authentication | 15-minute access token + 7-day rotating refresh token with blacklisting |
| Event CRUD | Create, list, retrieve, partial update (PATCH), full update (PUT), delete |
| Owner-only mutation guard | Object-level `IsEventOwner` permission blocks other facilitators from editing |
| Capacity enforcement | `SELECT FOR UPDATE` inside `transaction.atomic()` prevents over-enrollment |
| Event filtering | `location`, `language`, date range, and free-text search over title + description |
| Pagination | Page-number pagination; default 10 per page, max 100 via `?page_size=N` |
| Facilitator dashboard | `GET /events/my/` annotates each event with active enrollment count and available seats |
| Enrollment history | Separate upcoming and past enrollment views for seekers |
| Email notifications | Follow-up email ~1 hour after enrollment; reminder email ~1 hour before event start |
| Normalised error responses | All errors return `{"detail": "...", "code": "..."}` |

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Web framework | Django | 4.2.30 |
| REST API | Django REST Framework | 3.17.1 |
| Database | PostgreSQL | 15 |
| Async task queue | Celery | 5.6.3 |
| Message broker | Redis | 7 |
| JWT | djangorestframework-simplejwt | 5.5.1 |
| Filtering | django-filter | 25.1 |
| DB driver | psycopg2-binary | 2.9.12 |
| Config management | python-decouple | 3.8 |
| Containerisation | Docker + Docker Compose | — |

---

## Architecture Overview

```
Client (HTTP)
     │
     ▼
┌─────────────────────────────────────┐
│          Django / DRF               │
│  (accounts · events · core apps)    │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
  PostgreSQL          Redis
  (primary DB)     (Celery broker)
                        │
               ┌────────┴────────┐
               ▼                 ▼
         Celery Worker      Celery Beat
         (email send)       (60s schedule)
               │
               ▼
             SMTP
```

---

## Project Structure

```
ahoum_backend/
├── ahoum/
│   ├── settings/
│   │   ├── base.py           # Shared: DB, JWT, Celery, DRF, email
│   │   ├── local.py          # Dev overrides: DEBUG=True, console email
│   │   └── production.py     # Production overrides
│   ├── celery.py             # Celery app initialisation
│   ├── urls.py               # Root URL conf (/, /auth/, /events/, /admin/)
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── core/
│   │   ├── exceptions.py     # custom_exception_handler (normalises all DRF errors)
│   │   ├── pagination.py     # StandardResultsPagination (page_size=10, max=100)
│   │   ├── permissions.py    # IsEmailVerified, IsSeeker, IsFacilitator
│   │   └── utils.py          # generate_otp(), aware_utcnow()
│   ├── accounts/
│   │   ├── models.py         # UserProfile, OTPVerification
│   │   ├── views.py          # SignupAPIView, VerifyEmailAPIView, LoginAPIView
│   │   ├── serializers.py    # SignupSerializer, OTPVerifySerializer, LoginSerializer
│   │   ├── services.py       # generate_and_send_otp(), verify_otp()
│   │   ├── backends.py       # EmailAuthBackend (email+password lookup)
│   │   ├── exceptions.py     # OTPNotFoundException, OTPExpiredException, …
│   │   ├── signals.py        # post_save → auto-create UserProfile
│   │   └── urls.py
│   └── events/
│       ├── models.py         # Event, Enrollment
│       ├── views.py          # EventViewSet, UpcomingEnrollmentsView, PastEnrollmentsView
│       ├── serializers.py    # EventSerializer, EventWithCountsSerializer, EnrollmentDetailSerializer
│       ├── filters.py        # EventFilter (location, language, starts_after/before, q)
│       ├── permissions.py    # IsEventOwner (object-level)
│       ├── tasks.py          # send_enrollment_followup, send_event_reminder
│       └── urls.py
├── postman/
│   ├── Ahoum_Events_Platform.postman_collection.json
│   └── Ahoum_Local.postman_environment.json
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── manage.py
└── .env
```

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- PostgreSQL 15
- Redis 7
- Docker + Docker Compose (for containerised setup)

### Local Setup (no Docker)

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd ahoum_backend

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env   # then edit values as required
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Django secret key |
| `DEBUG` | No | `False` | Enable debug mode |
| `ALLOWED_HOSTS` | No | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DB_NAME` | No | `ahoum_db` | PostgreSQL database name |
| `DB_USER` | No | `postgres` | PostgreSQL username |
| `DB_PASSWORD` | Yes | — | PostgreSQL password |
| `DB_HOST` | No | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection URL (Celery broker + backend) |
| `OTP_EXPIRY_MINUTES` | No | `5` | OTP validity window in minutes |
| `OTP_MAX_ATTEMPTS` | No | `5` | Maximum OTP verification attempts before lockout |
| `EMAIL_BACKEND` | No | `console.EmailBackend` | Django email backend class |
| `EMAIL_HOST` | No | `smtp.gmail.com` | SMTP host |
| `EMAIL_PORT` | No | `587` | SMTP port |
| `EMAIL_USE_TLS` | No | `True` | Enable STARTTLS |
| `EMAIL_HOST_USER` | No | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | No | — | SMTP password |
| `DEFAULT_FROM_EMAIL` | No | `noreply@ahoum.com` | Sender address for all outgoing mail |

---

## Database Setup

```bash
# Create the PostgreSQL database
createdb -U postgres ahoum_db

# Or via psql
psql -U postgres -c "CREATE DATABASE ahoum_db;"
```

---

## Running Migrations

```bash
python manage.py migrate --settings=ahoum.settings.local
```

---

## Running the Application

```bash
python manage.py runserver --settings=ahoum.settings.local
# API available at http://localhost:8000/
```

In development, `local.py` sets `EMAIL_BACKEND = console.EmailBackend` — OTP codes are printed to the terminal instead of being sent via SMTP.

---

## Running Docker

Docker Compose starts five services: `db` (PostgreSQL), `redis`, `web` (Django), `celery` (worker), and `celery-beat` (scheduler). The `web` service automatically runs migrations on startup.

```bash
# Build and start all services
docker compose up --build

# Run detached
docker compose up -d --build

# Stop and remove containers
docker compose down

# Tail logs for a specific service
docker compose logs -f web
docker compose logs -f celery
```

---

## Running Celery Worker

```bash
celery -A ahoum worker --loglevel=info
```

---

## Running Celery Beat

```bash
celery -A ahoum beat --loglevel=info --scheduler celery.beat.PersistentScheduler
```

---

## API Authentication Flow

```
Step 1 — Register
  POST /auth/signup/
  Body: { "email": "...", "password": "...", "role": "seeker" | "facilitator" }
  → 200 { "detail": "Verification code sent to your email." }

Step 2 — Verify email
  POST /auth/verify-email/
  Body: { "email": "...", "otp": "123456" }
  → 200 { "detail": "Email verified successfully." }

Step 3 — Login
  POST /auth/login/
  Body: { "email": "...", "password": "..." }
  → 200 { "access": "<jwt>", "refresh": "<jwt>" }

Step 4 — Authenticated requests
  Header: Authorization: Bearer <access token>

Step 5 — Refresh
  POST /auth/refresh/
  Body: { "refresh": "<refresh token>" }
  → 200 { "access": "<new jwt>", "refresh": "<rotated jwt>" }
```

JWT tokens expire after **15 minutes** (access) and **7 days** (refresh). The refresh token is rotated on every use and the old token is blacklisted.

---

## API Endpoints Summary

### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup/` | None | Register a new user; sends OTP to email |
| POST | `/auth/verify-email/` | None | Submit 6-digit OTP to verify email |
| POST | `/auth/login/` | None | Authenticate; returns access + refresh tokens |
| POST | `/auth/refresh/` | None | Rotate refresh token; returns new access token |

### Events

| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/events/` | Facilitator | Create an event |
| GET | `/events/` | Seeker | Browse upcoming events (filterable, paginated) |
| GET | `/events/{id}/` | Any verified | Retrieve a single event |
| PATCH | `/events/{id}/` | Facilitator + Owner | Partially update an event |
| PUT | `/events/{id}/` | Facilitator + Owner | Fully replace an event |
| DELETE | `/events/{id}/` | Facilitator + Owner | Delete (blocked if active enrollments exist) |
| GET | `/events/my/` | Facilitator | Own events with enrollment counts and available seats |

### Enrollments

| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/events/{id}/enroll/` | Seeker | Enroll in an event |
| DELETE | `/events/{id}/enroll/` | Seeker | Cancel active enrollment |
| GET | `/enrollments/upcoming/` | Seeker | Active enrollments in future events |
| GET | `/enrollments/past/` | Seeker | Active enrollments in ended events |

### List Events — Supported Query Parameters

| Parameter | Description |
|---|---|
| `location` | Case-insensitive substring match on `location` |
| `language` | Case-insensitive exact match on `language` |
| `starts_after` | ISO 8601 — events starting at or after this datetime |
| `starts_before` | ISO 8601 — events starting at or before this datetime |
| `q` | Full-text search across `title` and `description` |
| `ordering` | `starts_at` or `title`; prefix `-` for descending |
| `page` | Page number (default `1`) |
| `page_size` | Results per page (default `10`, max `100`) |

---

## Postman Collection Usage

The collection and environment file are in `postman/`.

**Import:**
1. Postman → **Import** → `postman/Ahoum_Events_Platform.postman_collection.json`
2. **Import** → `postman/Ahoum_Local.postman_environment.json`
3. Select **Ahoum Local** from the environment dropdown (top-right)

**Flow:**
1. Run **Signup** with the desired role
2. Run **Verify Email** with the OTP received
3. Run **Login** → paste `access` value into `{{access_token}}`, `refresh` into `{{refresh_token}}`
4. All protected requests inherit `Authorization: Bearer {{access_token}}` from the collection-level auth

---

## Design Decisions

| Decision | Rationale |
|---|---|
| `username = uuid4().hex` at signup | Email is the public identity. An opaque UUID username avoids exposing internal identifiers while reusing Django's built-in `User` model without a model swap. |
| `OTP.max_attempts` stored on the row | Snapshotting `settings.OTP_MAX_ATTEMPTS` at creation time means a settings change mid-flight does not retroactively alter in-flight OTPs. |
| Previous OTPs invalidated on re-signup | Ensures only one active OTP exists per user at any time; prevents replay of a previously issued code. |
| `SELECT FOR UPDATE` on enrollment | Serialises concurrent enrollment requests for the same event row, eliminating the TOCTOU race where two requests both pass the capacity check but together overfill the event. |
| `IsEventOwner.has_permission` returns `True` | Allows composition with view-level permissions without blocking non-object actions (`list`, `create`, `my_events`). The ownership check fires only at object level via `get_object()`. |
| Refresh token rotation + blacklisting | Limits the blast radius of a stolen refresh token to a single use; the old token is immediately blacklisted after rotation. |
| Celery Beat ±1 min jitter window | Each task checks enrollments/events within `[T−1min, T+1min]` rather than at an exact timestamp, compensating for scheduling drift without duplicating sends under normal conditions. |
| Normalised error shape `{detail, code}` | `custom_exception_handler` in `core/exceptions.py` collapses all three shapes DRF can produce into one flat structure, giving clients a single parsing contract. |

---

## Tradeoffs

| Area | Decision Made | Cost |
|---|---|---|
| Email uniqueness | Enforced in `SignupSerializer`, not at the DB level (Django's default `User` model has no `UNIQUE` on `email`) | A race condition at the DB layer could create duplicate emails if the API layer is bypassed |
| Plain-text OTP storage | Stored as-is; expires in 5 min with a 5-attempt limit | A DB read compromise exposes valid OTPs within their short window |
| Enrollment soft-delete | Cancellation sets `status=canceled`; rows are never deleted | The enrollments table grows unbounded; historical data is preserved |
| Celery Beat jitter window | Sends if `created_at` falls in `[now−61min, now−59min]` | On Beat restart or double-fire, a user enrolled exactly on the boundary could receive two follow-up emails |
| Role embedded in `UserProfile` | Simple flat RBAC, easy to query | No role hierarchy; adding a third role requires a migration and a new permission class |

---

## Future Improvements

- Add a DB-level `UNIQUE` constraint on `auth_user.email` via a custom `AbstractBaseUser` to close the duplicate-email race condition
- Hash stored OTPs using PBKDF2 or Argon2 to defend against a DB read compromise
- Add idempotency tracking to Celery email tasks (store a `task_sent_at` field on `Enrollment`) to guarantee at-most-once delivery across Beat restarts
- Expose a `PATCH /auth/profile/` endpoint so users can update their display name or role
- Add a `canceled_at` timestamp to `Enrollment` to support accurate analytics on cancellation patterns
