from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from apps.accounts.exceptions import (
    OTPExpiredException,
    OTPExhaustedException,
    OTPInvalidException,
    OTPNotFoundException,
)
from apps.accounts.models import OTPVerification, UserProfile
from apps.core.utils import aware_utcnow, generate_otp

User = get_user_model()


def generate_and_send_otp(user) -> OTPVerification:
    """
    Invalidate any previous non-used OTPs for the user, create a fresh one,
    and send the verification code by email.

    max_attempts is stored on the row at creation time so that a later
    settings change does not retroactively alter an in-flight OTP.
    """
    # Invalidate all previous active OTPs in one query
    OTPVerification.objects.filter(user=user, is_used=False).update(is_used=True)

    otp_code = generate_otp()
    otp = OTPVerification.objects.create(
        user=user,
        otp=otp_code,
        expires_at=aware_utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        max_attempts=settings.OTP_MAX_ATTEMPTS,
    )

    send_mail(
        subject="Your Ahoum verification code",
        message=(
            f"Your verification code is: {otp_code}\n\n"
            f"This code expires in {settings.OTP_EXPIRY_MINUTES} minutes.\n\n"
            "If you did not request this, please ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

    return otp


def verify_otp(email: str, otp_value: str) -> User:
    """
    Validate the OTP submitted for the given email address.

    Checks are applied in this order:
        1. Active (non-used) OTP exists for the email
        2. OTP is not expired
        3. Attempt limit is not exhausted
        4. OTP value matches

    On success: marks the OTP as used and sets UserProfile.is_email_verified.
    Returns the verified User instance.
    Raises a domain exception on any failure — callers do not need try/except.
    """
    try:
        user = User.objects.get(email=email)
    except (User.DoesNotExist, User.MultipleObjectsReturned):
        # MultipleObjectsReturned guards against duplicate emails that bypass
        # the API layer; treated the same as not-found to avoid leaking info.
        raise OTPNotFoundException()

    # OTPVerification.Meta.ordering = ["-created_at"], so .first() is newest
    otp = OTPVerification.objects.filter(user=user, is_used=False).first()

    if otp is None:
        raise OTPNotFoundException()

    if otp.is_expired:
        raise OTPExpiredException()

    if otp.is_exhausted:
        raise OTPExhaustedException()

    if otp.otp != otp_value:
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        raise OTPInvalidException()

    # Success — single-field updates to minimise write contention
    otp.is_used = True
    otp.save(update_fields=["is_used"])

    UserProfile.objects.filter(user=user).update(is_email_verified=True)

    return user
