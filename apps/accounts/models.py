from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class UserProfile(models.Model):
    ROLE_SEEKER = "seeker"
    ROLE_FACILITATOR = "facilitator"
    ROLE_CHOICES = [
        (ROLE_SEEKER, "Seeker"),
        (ROLE_FACILITATOR, "Facilitator"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="userprofile",
    )
    # Default is seeker; overwritten immediately by SignupSerializer.
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_SEEKER)
    is_email_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.email} ({self.role})"


class OTPVerification(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="otp_verifications",
    )
    otp = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    # Stored at creation time from settings.OTP_MAX_ATTEMPTS so that
    # a settings change mid-flight doesn't alter in-flight OTPs.
    max_attempts = models.PositiveSmallIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user.email} (expires {self.expires_at})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts
