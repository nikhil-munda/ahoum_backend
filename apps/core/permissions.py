from rest_framework.permissions import BasePermission


class IsEmailVerified(BasePermission):
    """Allow access only to users who have completed OTP email verification."""

    message = "Email address is not verified."
    code = "email_not_verified"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.userprofile.is_email_verified
        except Exception:
            return False


class IsSeeker(BasePermission):
    """Allow access only to users with the Seeker role."""

    message = "This action requires a Seeker account."
    code = "permission_denied"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.userprofile.role == "seeker"
        except Exception:
            return False


class IsFacilitator(BasePermission):
    """Allow access only to users with the Facilitator role."""

    message = "This action requires a Facilitator account."
    code = "permission_denied"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.userprofile.role == "facilitator"
        except Exception:
            return False
