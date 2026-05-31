from django.contrib import admin

from apps.events.models import Enrollment, Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "location", "starts_at", "ends_at", "capacity", "created_by")
    list_filter = ("language",)
    search_fields = ("title", "description", "location")
    ordering = ("starts_at",)
    raw_id_fields = ("created_by",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("seeker", "event", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("seeker__email", "event__title")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("seeker", "event")
