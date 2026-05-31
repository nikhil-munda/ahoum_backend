import secrets

from django.utils import timezone


def generate_otp() -> str:
    """
    Return a cryptographically random 6-digit OTP string (zero-padded).
    Uses secrets.randbelow — suitable for security-sensitive tokens.
    """
    return f"{secrets.randbelow(10 ** 6):06d}"


def aware_utcnow():
    """Return the current UTC datetime as a timezone-aware object."""
    return timezone.now()
