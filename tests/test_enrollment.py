from datetime import timedelta

import pytest

from apps.core.utils import aware_utcnow
from apps.events.models import Enrollment, Event

UPCOMING = "/enrollments/upcoming/"
PAST = "/enrollments/past/"


def enroll_url(event_id):
    return f"/events/{event_id}/enroll/"


# ── Enroll ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEnroll:
    def test_success_returns_201(self, seeker_client, event):
        resp = seeker_client.post(enroll_url(event.id))
        assert resp.status_code == 201
        assert resp.data["detail"] == "Successfully enrolled in the event."

    def test_enrollment_record_created(self, seeker_client, seeker, event):
        seeker_client.post(enroll_url(event.id))
        assert Enrollment.objects.filter(
            event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED
        ).exists()

    def test_duplicate_enrollment_rejected(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.post(enroll_url(event.id))
        assert resp.status_code == 400
        assert resp.data["code"] == "already_enrolled"

    def test_full_event_rejected(self, seeker_client, full_event):
        resp = seeker_client.post(enroll_url(full_event.id))
        assert resp.status_code == 400
        assert resp.data["code"] == "event_full"

    def test_ended_event_rejected(self, seeker_client, past_event):
        resp = seeker_client.post(enroll_url(past_event.id))
        assert resp.status_code == 400
        assert resp.data["code"] == "event_already_ended"

    def test_capacity_respected(self, db, facilitator, seeker_client, seeker):
        """Enrolling in the last remaining seat succeeds."""
        now = aware_utcnow()
        limited = Event.objects.create(
            title="One Seat",
            description="Very limited",
            language="English",
            location="Chennai",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=2),
            capacity=1,
            created_by=facilitator,
        )
        resp = seeker_client.post(enroll_url(limited.id))
        assert resp.status_code == 201

    def test_reenroll_after_cancel_succeeds(self, seeker_client, seeker, event):
        """Partial unique index allows re-enrollment after cancellation."""
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_CANCELED)
        resp = seeker_client.post(enroll_url(event.id))
        assert resp.status_code == 201

    def test_nonexistent_event_returns_404(self, seeker_client):
        resp = seeker_client.post(enroll_url(99999))
        assert resp.status_code == 404


# ── Cancel enrollment ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCancelEnrollment:
    def test_cancel_success_returns_200(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.delete(enroll_url(event.id))
        assert resp.status_code == 200
        assert resp.data["detail"] == "Enrollment canceled successfully."

    def test_enrollment_status_set_to_canceled(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        seeker_client.delete(enroll_url(event.id))
        enrollment = Enrollment.objects.get(event=event, seeker=seeker)
        assert enrollment.status == Enrollment.STATUS_CANCELED

    def test_no_active_enrollment_returns_404(self, seeker_client, event):
        resp = seeker_client.delete(enroll_url(event.id))
        assert resp.status_code == 404
        assert resp.data["code"] == "not_found"

    def test_already_canceled_returns_404(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_CANCELED)
        resp = seeker_client.delete(enroll_url(event.id))
        assert resp.status_code == 404


# ── Upcoming enrollments ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestUpcomingEnrollments:
    def test_returns_future_active_enrollments(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(UPCOMING)
        assert resp.status_code == 200
        assert any(e["event"]["id"] == event.id for e in resp.data["results"])

    def test_excludes_canceled_enrollments(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_CANCELED)
        resp = seeker_client.get(UPCOMING)
        assert resp.data["count"] == 0

    def test_excludes_past_events(self, seeker_client, seeker, past_event):
        Enrollment.objects.create(event=past_event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(UPCOMING)
        assert not any(e["event"]["id"] == past_event.id for e in resp.data["results"])

    def test_only_returns_own_enrollments(self, seeker_client, second_facilitator, event):
        # Enroll a different user; the seeker's upcoming should be empty
        Enrollment.objects.create(event=event, seeker=second_facilitator, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(UPCOMING)
        assert resp.data["count"] == 0

    def test_nested_event_data_present(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(UPCOMING)
        enrollment = resp.data["results"][0]
        assert "event" in enrollment
        assert enrollment["event"]["title"] == event.title

    def test_response_is_paginated(self, seeker_client):
        resp = seeker_client.get(UPCOMING)
        assert "count" in resp.data
        assert "results" in resp.data


# ── Past enrollments ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPastEnrollments:
    def test_returns_ended_event_enrollments(self, seeker_client, seeker, past_event):
        Enrollment.objects.create(event=past_event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(PAST)
        assert resp.status_code == 200
        assert any(e["event"]["id"] == past_event.id for e in resp.data["results"])

    def test_excludes_future_events(self, seeker_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(PAST)
        assert not any(e["event"]["id"] == event.id for e in resp.data["results"])

    def test_excludes_canceled_enrollments(self, seeker_client, seeker, past_event):
        Enrollment.objects.create(event=past_event, seeker=seeker, status=Enrollment.STATUS_CANCELED)
        resp = seeker_client.get(PAST)
        assert resp.data["count"] == 0

    def test_only_returns_own_enrollments(self, seeker_client, second_facilitator, past_event):
        Enrollment.objects.create(event=past_event, seeker=second_facilitator, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(PAST)
        assert resp.data["count"] == 0

    def test_nested_event_data_present(self, seeker_client, seeker, past_event):
        Enrollment.objects.create(event=past_event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = seeker_client.get(PAST)
        enrollment = resp.data["results"][0]
        assert "event" in enrollment
        assert enrollment["event"]["title"] == past_event.title
