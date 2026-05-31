# Ahoum Events Platform — Project Plan

## Requirements Summary

Build a small events backend with auth, RBAC, search, and enrollments serving two roles: **Seeker** and **Facilitator**.

### Key Constraints
- Django's default `User` model only — no `AUTH_USER_MODEL` swap
- No `username` field in signup request and never exposed in any serializer
- `username` is set internally to `uuid.uuid4().hex` — opaque, not email
- OTP email verification is mandatory before login is allowed
- Roles are exclusive: a user is either Seeker or Facilitator, not both
- Error response shape: `{ "detail": "...", "code": "..." }` everywhere
- PostgreSQL with useful indexes on `starts_at`, `language`, `location`
- DRF pagination shape: `{ "count", "next", "previous", "results" }`

---

## Architecture

```
Django 4.x + DRF + djangorestframework-simplejwt + django-filter + PostgreSQL
Bonus: Celery + Redis + django-celery-beat
```

Split settings (`base / local / production`) to keep secrets out of code.

**Three Django apps inside `apps/`:**
- `accounts` — auth, User extension, OTP
- `events` — Event and Enrollment domain
- `core` — shared exceptions, pagination, permissions, utils

---

## Folder Structure

```
ahoum_backend/                   ← repo root
├── manage.py
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── README.md
├── PROJECT_PLAN.md
├── postman/
│   └── ahoum_api.json
│
├── ahoum/                       ← Django project package
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── local.py
│   │   └── production.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
└── apps/
    ├── __init__.py
    │
    ├── core/
    │   ├── __init__.py
    │   ├── exceptions.py        ← global DRF exception handler → {detail, code}
    │   ├── pagination.py        ← StandardResultsPagination
    │   ├── permissions.py       ← IsSeeker, IsFacilitator, IsEmailVerified
    │   └── utils.py             ← generate_otp(), aware_utcnow()
    │
    ├── accounts/
    │   ├── __init__.py
    │   ├── admin.py
    │   ├── apps.py
    │   ├── backends.py          ← EmailAuthBackend (email + password login)
    │   ├── models.py            ← UserProfile, OTPVerification
    │   ├── serializers.py       ← Signup, OTPVerify, Login
    │   ├── services.py          ← send_otp_email(), verify_otp(), invalidate_old_otps()
    │   ├── views.py
    │   ├── urls.py
    │   └── migrations/
    │
    └── events/
        ├── __init__.py
        ├── admin.py
        ├── apps.py
        ├── models.py            ← Event, Enrollment
        ├── serializers.py       ← EventSerializer, EventListSerializer, EnrollmentSerializer
        ├── views.py
        ├── urls.py
        ├── filters.py           ← EventFilter (django-filter)
        ├── permissions.py       ← IsEventOwner
        ├── tasks.py             ← Celery tasks (bonus: scheduled emails)
        └── migrations/
```

---

## Models

### `accounts/models.py`

**`UserProfile`** — OneToOne extension of Django's default User

| Field | Type | Notes |
|---|---|---|
| `user` | `OneToOneField(User, on_delete=CASCADE)` | created via post_save signal |
| `role` | `CharField(choices: seeker / facilitator)` | set at signup |
| `is_email_verified` | `BooleanField(default=False)` | gated by OTP flow |

**`OTPVerification`**

| Field | Type | Notes |
|---|---|---|
| `user` | `ForeignKey(User, on_delete=CASCADE)` | |
| `otp` | `CharField(6)` | plain text (short-lived) |
| `expires_at` | `DateTimeField` | `now + 5 minutes` |
| `attempts` | `IntegerField(default=0)` | incremented on each wrong guess |
| `max_attempts` | `IntegerField(default=5)` | configurable |
| `is_used` | `BooleanField(default=False)` | marked True on success |

---

### `events/models.py`

**`Event`**

| Field | Type | Notes |
|---|---|---|
| `title` | `CharField(255)` | |
| `description` | `TextField` | |
| `language` | `CharField(100)` | `db_index=True` |
| `location` | `CharField(255)` | `db_index=True` |
| `starts_at` | `DateTimeField` | UTC, `db_index=True` |
| `ends_at` | `DateTimeField` | UTC |
| `capacity` | `PositiveIntegerField(null=True, blank=True)` | `null` = unlimited |
| `created_by` | `ForeignKey(User, on_delete=PROTECT)` | only Facilitators write |
| `created_at` | `DateTimeField(auto_now_add=True)` | |
| `updated_at` | `DateTimeField(auto_now=True)` | |

**`Enrollment`**

| Field | Type | Notes |
|---|---|---|
| `event` | `ForeignKey(Event, on_delete=CASCADE)` | |
| `seeker` | `ForeignKey(User, on_delete=CASCADE)` | |
| `status` | `CharField(choices: enrolled / canceled)` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |
| `updated_at` | `DateTimeField(auto_now=True)` | |
| **constraint** | `UniqueConstraint(fields=[event, seeker], condition=Q(status='enrolled'), name='unique_active_enrollment')` | partial index — re-enroll after cancel is allowed |

---

## Serializers

### `accounts/serializers.py`
- `SignupSerializer` — validates email uniqueness, role; sets `username = uuid.uuid4().hex` internally; creates User + UserProfile; triggers OTP send; never reads or returns `username`
- `OTPVerifySerializer` — validates email + otp; checks TTL and attempt count
- `LoginSerializer` — validates email + password; rejects unverified users

Token refresh is delegated to simplejwt's built-in `TokenRefreshView`.

### `events/serializers.py`
- `EventSerializer` — full CRUD fields; validates `starts_at < ends_at` and `starts_at` not in past
- `EventListSerializer` — adds computed `total_enrollments` and `available_seats` (for Facilitator my-events)
- `EnrollmentSerializer` — write serializer for enroll action
- `EnrollmentDetailSerializer` — read serializer; nests event data for Seeker enrollment lists

---

## Permissions

### `core/permissions.py`
- `IsEmailVerified` — `request.user.userprofile.is_email_verified`
- `IsSeeker` — `request.user.userprofile.role == 'seeker'`
- `IsFacilitator` — `request.user.userprofile.role == 'facilitator'`

### `events/permissions.py`
- `IsEventOwner` — `obj.created_by == request.user` (object-level; used on update/delete)

**Composition pattern:**
```python
permission_classes = [IsAuthenticated, IsEmailVerified, IsFacilitator, IsEventOwner]
```

---

## API Endpoints

### Auth

| Method | URL | Description |
|---|---|---|
| `POST` | `/auth/signup` | Create unverified user, send 6-digit OTP to email |
| `POST` | `/auth/verify-email` | `{email, otp}` → mark verified |
| `POST` | `/auth/login` | `{email, password}` → `{access, refresh}` JWTs |
| `POST` | `/auth/refresh` | Rotate / refresh access token |

### Seeker

| Method | URL | Description |
|---|---|---|
| `GET` | `/events/` | Search events — filters: `location`, `language`, `starts_after`, `starts_before`, `q`; ordered by `starts_at` ASC; paginated |
| `POST` | `/events/{id}/enroll/` | Enroll in event (checks capacity and uniqueness) |
| `DELETE` | `/events/{id}/enroll/` | Cancel enrollment |
| `GET` | `/enrollments/upcoming/` | List future enrolled events |
| `GET` | `/enrollments/past/` | List events that have already ended |

### Facilitator

| Method | URL | Description |
|---|---|---|
| `POST` | `/events/` | Create event |
| `GET` | `/events/my/` | List own events with `total_enrollments` and `available_seats` |
| `GET` | `/events/{id}/` | Retrieve event |
| `PUT` | `/events/{id}/` | Full update (owner only) |
| `PATCH` | `/events/{id}/` | Partial update (owner only) |
| `DELETE` | `/events/{id}/` | Delete event (owner only; blocked if active enrollments exist) |

---

## Edge Cases

| # | Scenario | Response |
|---|---|---|
| 1 | Signup — email already verified and exists | `400 email_already_exists` |
| 2 | Signup — email exists but unverified | Invalidate old OTP, generate new, resend |
| 3 | Verify — OTP expired | `400 otp_expired` |
| 4 | Verify — attempts exceeded | `429 otp_max_attempts` |
| 5 | Verify — wrong OTP | increment attempt; `400 otp_invalid` |
| 6 | Login — unverified user | `403 email_not_verified` |
| 7 | Login — wrong password | `401 invalid_credentials` |
| 8 | Seeker creates / updates / deletes event | `403 permission_denied` |
| 9 | Facilitator tries to enroll in event | `403 permission_denied` |
| 10 | Enroll — event at capacity | `400 event_full` |
| 11 | Enroll — already actively enrolled | `400 already_enrolled` |
| 12 | Cancel — enrollment not found | `404 not_found` |
| 13 | Cancel — enrollment already canceled | `400 enrollment_not_active` |
| 14 | Enroll — event already ended | `400 event_already_ended` |
| 15 | Update / delete — not event owner | `403 not_owner` |
| 16 | Create / update — `starts_at >= ends_at` | `400 invalid_dates` |
| 17 | Create — `starts_at` in the past | `400 event_in_past` |
| 18 | Capacity = 0 | Treated as immediately full |
| 19 | Delete event with active enrollments | `400 event_has_active_enrollments` |

---

## Implementation Order

### Phase 1 — Bootstrap
1. Django project scaffold with split settings (`base / local / production`)
2. `requirements.txt` (Django, DRF, simplejwt, psycopg2-binary, django-filter, python-decouple, celery[redis])
3. `.env.example` with all required environment variables
4. `Dockerfile` + `docker-compose.yml` (services: `db`, `redis`, `web`, `celery`)

### Phase 2 — Core Utilities (no inter-app dependencies)
5. `core/exceptions.py` — custom DRF exception handler producing `{detail, code}`
6. `core/pagination.py` — `StandardResultsPagination` (count / next / previous / results)
7. `core/permissions.py` — `IsEmailVerified`, `IsSeeker`, `IsFacilitator`
8. `core/utils.py` — `generate_otp()`, `aware_utcnow()`

### Phase 3 — Accounts App
9. `UserProfile` and `OTPVerification` models → generate + run migration
10. `accounts/backends.py` — `EmailAuthBackend`
11. `accounts/services.py` — OTP generation, storage, expiry, email send, verification logic
12. `accounts/serializers.py` — `SignupSerializer`, `OTPVerifySerializer`, `LoginSerializer`
13. `accounts/views.py` + `accounts/urls.py`
14. JWT settings in `base.py` (lifetimes, custom claims including `role`)

### Phase 4 — Events App
15. `Event` model with `db_index` fields → migration
16. `Enrollment` model with partial `UniqueConstraint` → migration
17. `events/filters.py` — `EventFilter` (location, language, starts_after, starts_before, q)
18. `events/serializers.py` — all four serializers
19. `events/permissions.py` — `IsEventOwner`
20. `events/views.py` — Facilitator CRUD + my-events views
21. `events/views.py` — Seeker search + enroll/cancel + upcoming/past views
22. `events/urls.py` + wire into project `urls.py`

### Phase 5 — Tests
23. Auth flow: signup → OTP → login → refresh; OTP expiry + attempt limits
24. RBAC: every endpoint rejects the wrong role
25. Event CRUD: ownership enforcement, date validation
26. Enrollment: capacity check, uniqueness, past/upcoming filters

### Phase 6 — Documentation
27. `README.md` — env vars, local run, Docker instructions, design decisions, tradeoffs
28. `postman/ahoum_api.json` — Postman collection covering all endpoints

### Phase 7 — Bonus
29. Celery + `django-celery-beat` wiring in settings and `docker-compose.yml`
30. Task: send follow-up email to seeker 1 hour after enrollment
31. Task: send reminder email to enrolled seekers 1 hour before event starts

---

## Key Design Decisions & Tradeoffs

| Decision | Rationale | Tradeoff |
|---|---|---|
| `UserProfile` OneToOne instead of custom User | Respects "default User model only" constraint | Extra join on every auth check; mitigated by `select_related` |
| `username = uuid.uuid4().hex` on signup | Fully decouples the username field from business logic; no length-collision risk; `username` is never exposed in any serializer or API response | Requires `EmailAuthBackend` to look up users by `email` instead of `username`; Django admin login still works via the `ModelBackend` fallback |
| OTP stored plain text | Short TTL (5 min) makes attack window tiny; simpler code | If DB is compromised within TTL window, OTPs are exposed — acceptable for this scope |
| Partial unique index for enrollment | Allows re-enroll after cancel without extra status-tracking tables | Requires PostgreSQL (not SQLite-compatible) |
| `PROTECT` on `Event.created_by` | Prevents accidental user deletion cascading to events | Must explicitly handle user deletion if needed |
| `CASCADE` on `Enrollment.event` | Deleting an event cleans up enrollments (after block check) | Business logic must prevent delete when enrollments are active |
| Celery + Redis for scheduled mail | Industry-standard; easily deployable via Docker Compose | Adds infrastructure complexity; alternative is APScheduler for simpler single-process setup |
