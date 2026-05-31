import uuid

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.accounts.services import generate_and_send_otp, verify_otp

User = get_user_model()


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )
    role = serializers.CharField()

    def validate_email(self, value):
        value = value.strip().lower()
        verified_exists = User.objects.filter(
            email=value,
            userprofile__is_email_verified=True,
        ).exists()
        if verified_exists:
            raise serializers.ValidationError(
                detail="A verified account with this email already exists.",
                code="email_already_exists",
            )
        return value

    def validate_role(self, value):
        normalized = value.strip().lower()
        valid_roles = [choice[0] for choice in UserProfile.ROLE_CHOICES]
        if normalized not in valid_roles:
            raise serializers.ValidationError(
                detail=f"Role must be one of: {', '.join(valid_roles)}.",
                code="invalid_role",
            )
        return normalized

    def validate_password(self, value):
        django_validate_password(value)
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]
        role = validated_data["role"]

        with transaction.atomic():
            existing_user = User.objects.filter(email=email).first()

            if existing_user:
                # Unverified user already exists — reuse, refresh credentials, resend OTP.
                # validate_email guarantees this user is not yet verified.
                existing_user.set_password(password)
                existing_user.save(update_fields=["password"])
                UserProfile.objects.filter(user=existing_user).update(role=role)
                user = existing_user
            else:
                # New user — username is an opaque UUID, never exposed externally.
                user = User.objects.create_user(
                    username=uuid.uuid4().hex,
                    email=email,
                    password=password,
                )
                # post_save signal created UserProfile with default role; set actual role.
                UserProfile.objects.filter(user=user).update(role=role)

            # OTP creation + email send inside the transaction so that a send
            # failure rolls back the entire signup attempt cleanly.
            generate_and_send_otp(user)

        return user


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError(
                detail="OTP must be a 6-digit number.",
                code="otp_invalid",
            )
        return value

    def save(self):
        # verify_otp raises domain exceptions (OTPExpiredException, etc.) on
        # any failure; they propagate to the view and are handled by the global
        # exception handler without any extra try/except here.
        verify_otp(
            email=self.validated_data["email"],
            otp_value=self.validated_data["otp"],
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        # Raising AuthenticationFailed / PermissionDenied (not ValidationError)
        # so that correct HTTP status codes (401 / 403) are returned.
        # These are APIException subclasses and propagate through is_valid()
        # to APIView.handle_exception(), which routes them to the global handler.
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"],
            password=attrs["password"],
        )

        if user is None:
            raise AuthenticationFailed(
                detail="Invalid email or password.",
                code="invalid_credentials",
            )

        try:
            is_verified = user.userprofile.is_email_verified
        except Exception:
            is_verified = False

        if not is_verified:
            raise PermissionDenied(
                detail="Email address is not verified.",
                code="email_not_verified",
            )

        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
