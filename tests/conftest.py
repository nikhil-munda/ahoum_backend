import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.core.utils import aware_utcnow
from apps.events.models import Event

User = get_user_model()

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_user(email, password, role, verified=True):
    user = User.objects.create_user(
        username=uuid.uuid4().hex,
        email=email,
        password=password,
    )
    UserProfile.objects.filter(user=user).update(
        role=role,
        is_email_verified=verified,
    )
    user.refresh_from_db()
    return user


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


# ── Core fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def seeker(db):
    return make_user("seeker@test.com", "TestPass123!", UserProfile.ROLE_SEEKER)


@pytest.fixture
def facilitator(db):
    return make_user("facilitator@test.com", "TestPass123!", UserProfile.ROLE_FACILITATOR)


@pytest.fixture
def second_facilitator(db):
    return make_user("second@test.com", "TestPass123!", UserProfile.ROLE_FACILITATOR)


@pytest.fixture
def unverified_seeker(db):
    return make_user("unverified@test.com", "TestPass123!", UserProfile.ROLE_SEEKER, verified=False)


# ── Authenticated clients ─────────────────────────────────────────────────────


@pytest.fixture
def seeker_client(seeker):
    return auth_client(seeker)


@pytest.fixture
def facilitator_client(facilitator):
    return auth_client(facilitator)


@pytest.fixture
def second_facilitator_client(second_facilitator):
    return auth_client(second_facilitator)


# ── Event fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def event(db, facilitator):
    now = aware_utcnow()
    return Event.objects.create(
        title="Test Event",
        description="A test event description",
        language="English",
        location="New Delhi",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=2),
        capacity=10,
        created_by=facilitator,
    )


@pytest.fixture
def full_event(db, facilitator):
    """Event whose capacity is 0 — always full."""
    now = aware_utcnow()
    return Event.objects.create(
        title="Full Event",
        description="No seats available",
        language="English",
        location="Mumbai",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=2),
        capacity=0,
        created_by=facilitator,
    )


@pytest.fixture
def past_event(db, facilitator):
    """Event that has already ended."""
    now = aware_utcnow()
    return Event.objects.create(
        title="Past Event",
        description="This event has ended",
        language="Hindi",
        location="Bangalore",
        starts_at=now - timedelta(days=3),
        ends_at=now - timedelta(days=1),
        capacity=10,
        created_by=facilitator,
    )
