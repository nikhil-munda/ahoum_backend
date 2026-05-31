from django.contrib import admin

from apps.accounts.models import OTPVerification, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_email_verified")
    list_filter = ("role", "is_email_verified")
    search_fields = ("user__email",)


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "attempts", "max_attempts", "is_used")
    list_filter = ("is_used",)
    search_fields = ("user__email",)
    readonly_fields = ("created_at",)
