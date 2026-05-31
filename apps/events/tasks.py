from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.events.models import Enrollment


@shared_task
def send_enrollment_followup():
    """
    Send a follow-up email to every seeker who enrolled approximately 1 hour ago.
    Runs every 60 seconds; checks a ±1-minute window around the 1-hour mark.
    """
    now = timezone.now()
    window_start = now - timedelta(hours=1, minutes=1)
    window_end = now - timedelta(hours=1) + timedelta(minutes=1)

    enrollments = (
        Enrollment.objects.filter(
            status=Enrollment.STATUS_ENROLLED,
            created_at__gte=window_start,
            created_at__lte=window_end,
        )
        .select_related("seeker", "event")
    )

    for enrollment in enrollments:
        send_mail(
            subject=f"You're enrolled in {enrollment.event.title}",
            message=(
                f"Hi,\n\n"
                f"You enrolled in \"{enrollment.event.title}\" about an hour ago.\n\n"
                f"Starts: {enrollment.event.starts_at:%Y-%m-%d %H:%M UTC}\n"
                f"Location: {enrollment.event.location}\n\n"
                f"See you there!"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[enrollment.seeker.email],
            fail_silently=True,
        )


@shared_task
def send_event_reminder():
    """
    Send a reminder email to every seeker whose enrolled event starts in ~1 hour.
    Runs every 60 seconds; checks a ±1-minute window around the 1-hour mark.
    """
    now = timezone.now()
    window_start = now + timedelta(hours=1) - timedelta(minutes=1)
    window_end = now + timedelta(hours=1) + timedelta(minutes=1)

    enrollments = (
        Enrollment.objects.filter(
            status=Enrollment.STATUS_ENROLLED,
            event__starts_at__gte=window_start,
            event__starts_at__lte=window_end,
        )
        .select_related("seeker", "event")
    )

    for enrollment in enrollments:
        send_mail(
            subject=f"Reminder: {enrollment.event.title} starts in 1 hour",
            message=(
                f"Hi,\n\n"
                f"\"{enrollment.event.title}\" starts in about 1 hour.\n\n"
                f"Starts: {enrollment.event.starts_at:%Y-%m-%d %H:%M UTC}\n"
                f"Location: {enrollment.event.location}\n\n"
                f"Get ready!"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[enrollment.seeker.email],
            fail_silently=True,
        )
