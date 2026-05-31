from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import OTPVerification
from apps.core.utils import aware_utcnow

User = get_user_model()

SIGNUP = "/auth/signup/"
VERIFY = "/auth/verify-email/"
LOGIN = "/auth/login/"
REFRESH = "/auth/refresh/"


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_otp(user, otp="123456", expired=False, exhausted=False):
    expires_at = (
        aware_utcnow() - timedelta(minutes=1)
        if expired
        else aware_utcnow() + timedelta(minutes=5)
    )
    return OTPVerification.objects.create(
        user=user,
        otp=otp,
        expires_at=expires_at,
        max_attempts=5,
        attempts=5 if exhausted else 0,
    )


# ── Signup ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSignup:
    def test_success_returns_200(self, api_client):
        resp = api_client.post(SIGNUP, {"email": "new@test.com", "password": "TestPass123!", "role": "seeker"})
        assert resp.status_code == 200
        assert resp.data["detail"] == "Verification code sent to your email."

    def test_user_created_in_db(self, api_client):
        api_client.post(SIGNUP, {"email": "new2@test.com", "password": "TestPass123!", "role": "seeker"})
        assert User.objects.filter(email="new2@test.com").exists()

    def test_username_is_uuid_not_email(self, api_client):
        api_client.post(SIGNUP, {"email": "uuid@test.com", "password": "TestPass123!", "role": "seeker"})
        user = User.objects.get(email="uuid@test.com")
        assert user.username != "uuid@test.com"
        assert len(user.username) == 32

    def test_otp_record_created(self, api_client):
        api_client.post(SIGNUP, {"email": "otp@test.com", "password": "TestPass123!", "role": "seeker"})
        user = User.objects.get(email="otp@test.com")
        assert OTPVerification.objects.filter(user=user, is_used=False).exists()

    def test_verified_email_rejected(self, api_client, seeker):
        resp = api_client.post(SIGNUP, {"email": seeker.email, "password": "TestPass123!", "role": "seeker"})
        assert resp.status_code == 400
        assert resp.data["code"] == "email_already_exists"

    def test_unverified_email_resends_otp(self, api_client, unverified_seeker):
        old = make_otp(unverified_seeker, otp="111111")
        resp = api_client.post(SIGNUP, {"email": unverified_seeker.email, "password": "TestPass123!", "role": "seeker"})
        assert resp.status_code == 200
        old.refresh_from_db()
        assert old.is_used is True  # old OTP invalidated

    def test_invalid_role_rejected(self, api_client):
        resp = api_client.post(SIGNUP, {"email": "x@test.com", "password": "TestPass123!", "role": "admin"})
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_role"

    def test_role_case_insensitive(self, api_client):
        resp = api_client.post(SIGNUP, {"email": "case@test.com", "password": "TestPass123!", "role": "SEEKER"})
        assert resp.status_code == 200

    def test_weak_password_rejected(self, api_client):
        resp = api_client.post(SIGNUP, {"email": "weak@test.com", "password": "pass", "role": "seeker"})
        assert resp.status_code == 400

    def test_missing_fields_rejected(self, api_client):
        resp = api_client.post(SIGNUP, {"email": "missing@test.com"})
        assert resp.status_code == 400


# ── OTP Verification ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestVerifyEmail:
    def test_success_returns_200(self, api_client, unverified_seeker):
        make_otp(unverified_seeker)
        resp = api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "123456"})
        assert resp.status_code == 200
        assert resp.data["detail"] == "Email verified successfully."

    def test_profile_marked_verified(self, api_client, unverified_seeker):
        make_otp(unverified_seeker)
        api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "123456"})
        unverified_seeker.userprofile.refresh_from_db()
        assert unverified_seeker.userprofile.is_email_verified is True

    def test_otp_marked_used(self, api_client, unverified_seeker):
        otp_obj = make_otp(unverified_seeker)
        api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "123456"})
        otp_obj.refresh_from_db()
        assert otp_obj.is_used is True

    def test_wrong_otp_returns_400(self, api_client, unverified_seeker):
        make_otp(unverified_seeker)
        resp = api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "000000"})
        assert resp.status_code == 400
        assert resp.data["code"] == "otp_invalid"

    def test_wrong_otp_increments_attempts(self, api_client, unverified_seeker):
        otp_obj = make_otp(unverified_seeker)
        api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "000000"})
        otp_obj.refresh_from_db()
        assert otp_obj.attempts == 1

    def test_expired_otp_returns_400(self, api_client, unverified_seeker):
        make_otp(unverified_seeker, expired=True)
        resp = api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "123456"})
        assert resp.status_code == 400
        assert resp.data["code"] == "otp_expired"

    def test_exhausted_attempts_returns_429(self, api_client, unverified_seeker):
        make_otp(unverified_seeker, exhausted=True)
        resp = api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "123456"})
        assert resp.status_code == 429
        assert resp.data["code"] == "otp_max_attempts"

    def test_no_active_otp_returns_400(self, api_client, unverified_seeker):
        resp = api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "123456"})
        assert resp.status_code == 400
        assert resp.data["code"] == "otp_not_found"

    def test_nonexistent_email_returns_400(self, api_client):
        resp = api_client.post(VERIFY, {"email": "ghost@test.com", "otp": "123456"})
        assert resp.status_code == 400
        assert resp.data["code"] == "otp_not_found"

    def test_non_digit_otp_rejected(self, api_client, unverified_seeker):
        resp = api_client.post(VERIFY, {"email": unverified_seeker.email, "otp": "abcdef"})
        assert resp.status_code == 400
        assert resp.data["code"] == "otp_invalid"


# ── Login ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLogin:
    def test_success_returns_tokens(self, api_client, seeker):
        resp = api_client.post(LOGIN, {"email": seeker.email, "password": "TestPass123!"})
        assert resp.status_code == 200
        assert "access" in resp.data
        assert "refresh" in resp.data

    def test_wrong_password_returns_401(self, api_client, seeker):
        resp = api_client.post(LOGIN, {"email": seeker.email, "password": "WrongPass!"})
        assert resp.status_code == 401
        assert resp.data["code"] == "invalid_credentials"

    def test_nonexistent_email_returns_401(self, api_client):
        resp = api_client.post(LOGIN, {"email": "nobody@test.com", "password": "TestPass123!"})
        assert resp.status_code == 401
        assert resp.data["code"] == "invalid_credentials"

    def test_unverified_user_returns_403(self, api_client, unverified_seeker):
        resp = api_client.post(LOGIN, {"email": unverified_seeker.email, "password": "TestPass123!"})
        assert resp.status_code == 403
        assert resp.data["code"] == "email_not_verified"

    def test_facilitator_login_success(self, api_client, facilitator):
        resp = api_client.post(LOGIN, {"email": facilitator.email, "password": "TestPass123!"})
        assert resp.status_code == 200
        assert "access" in resp.data


# ── Token Refresh ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTokenRefresh:
    def test_refresh_returns_new_access_token(self, api_client, seeker):
        refresh = RefreshToken.for_user(seeker)
        resp = api_client.post(REFRESH, {"refresh": str(refresh)})
        assert resp.status_code == 200
        assert "access" in resp.data

    def test_invalid_token_returns_401(self, api_client):
        resp = api_client.post(REFRESH, {"refresh": "not.a.valid.token"})
        assert resp.status_code == 401

    def test_missing_token_returns_400(self, api_client):
        resp = api_client.post(REFRESH, {})
        assert resp.status_code == 400
