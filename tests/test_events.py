from datetime import timedelta

import pytest

from apps.core.utils import aware_utcnow
from apps.events.models import Enrollment, Event


def future_payload(**overrides):
    now = aware_utcnow()
    data = {
        "title": "Sample Event",
        "description": "A sample event for testing",
        "language": "English",
        "location": "Mumbai",
        "starts_at": (now + timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=2)).isoformat(),
        "capacity": 20,
    }
    data.update(overrides)
    return data


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEventCreate:
    def test_success_returns_201(self, facilitator_client):
        resp = facilitator_client.post("/events/", future_payload())
        assert resp.status_code == 201
        assert resp.data["title"] == "Sample Event"

    def test_created_by_set_to_request_user(self, facilitator_client, facilitator):
        resp = facilitator_client.post("/events/", future_payload())
        assert resp.data["created_by"] == facilitator.id

    def test_event_persisted_to_db(self, facilitator_client):
        facilitator_client.post("/events/", future_payload())
        assert Event.objects.filter(title="Sample Event").exists()

    def test_invalid_dates_rejected(self, facilitator_client):
        now = aware_utcnow()
        resp = facilitator_client.post("/events/", future_payload(
            starts_at=(now + timedelta(days=2)).isoformat(),
            ends_at=(now + timedelta(days=1)).isoformat(),
        ))
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_dates"

    def test_equal_dates_rejected(self, facilitator_client):
        now = aware_utcnow()
        ts = (now + timedelta(days=1)).isoformat()
        resp = facilitator_client.post("/events/", future_payload(starts_at=ts, ends_at=ts))
        assert resp.status_code == 400
        assert resp.data["code"] == "invalid_dates"

    def test_past_start_rejected(self, facilitator_client):
        now = aware_utcnow()
        resp = facilitator_client.post("/events/", future_payload(
            starts_at=(now - timedelta(hours=1)).isoformat(),
            ends_at=(now + timedelta(days=1)).isoformat(),
        ))
        assert resp.status_code == 400
        assert resp.data["code"] == "event_in_past"

    def test_null_capacity_allowed(self, facilitator_client):
        data = future_payload()
        data.pop("capacity")
        resp = facilitator_client.post("/events/", data)
        assert resp.status_code == 201
        assert resp.data["capacity"] is None

    def test_zero_capacity_allowed(self, facilitator_client):
        resp = facilitator_client.post("/events/", future_payload(capacity=0))
        assert resp.status_code == 201
        assert resp.data["capacity"] == 0


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEventUpdate:
    def test_partial_update_by_owner(self, facilitator_client, event):
        resp = facilitator_client.patch(f"/events/{event.id}/", {"title": "Updated Title"})
        assert resp.status_code == 200
        assert resp.data["title"] == "Updated Title"

    def test_created_by_unchanged_after_update(self, facilitator_client, facilitator, event):
        facilitator_client.patch(f"/events/{event.id}/", {"title": "New"})
        event.refresh_from_db()
        assert event.created_by == facilitator

    def test_full_update_by_owner(self, facilitator_client, facilitator, event):
        now = aware_utcnow()
        resp = facilitator_client.put(f"/events/{event.id}/", {
            "title": "Fully Updated",
            "description": "New desc",
            "language": "Hindi",
            "location": "Chennai",
            "starts_at": (now + timedelta(days=3)).isoformat(),
            "ends_at": (now + timedelta(days=4)).isoformat(),
            "capacity": 5,
        })
        assert resp.status_code == 200
        assert resp.data["language"] == "Hindi"

    def test_patch_preserves_unmentioned_fields(self, facilitator_client, event):
        resp = facilitator_client.patch(f"/events/{event.id}/", {"title": "Only Title Changed"})
        assert resp.status_code == 200
        assert resp.data["location"] == event.location

    def test_non_owner_update_blocked(self, second_facilitator_client, event):
        resp = second_facilitator_client.patch(f"/events/{event.id}/", {"title": "Stolen"})
        assert resp.status_code == 403
        assert resp.data["code"] == "not_owner"


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEventDelete:
    def test_owner_can_delete(self, facilitator_client, event):
        resp = facilitator_client.delete(f"/events/{event.id}/")
        assert resp.status_code == 204
        assert not Event.objects.filter(pk=event.id).exists()

    def test_non_owner_cannot_delete(self, second_facilitator_client, event):
        resp = second_facilitator_client.delete(f"/events/{event.id}/")
        assert resp.status_code == 403

    def test_delete_with_active_enrollments_blocked(self, facilitator_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = facilitator_client.delete(f"/events/{event.id}/")
        assert resp.status_code == 400
        assert resp.data["code"] == "event_has_active_enrollments"
        assert Event.objects.filter(pk=event.id).exists()

    def test_delete_with_only_canceled_enrollments_allowed(self, facilitator_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_CANCELED)
        resp = facilitator_client.delete(f"/events/{event.id}/")
        assert resp.status_code == 204


# ── Facilitator dashboard ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestFacilitatorDashboard:
    def test_returns_own_events_only(self, facilitator_client, second_facilitator_client, facilitator, event):
        resp = facilitator_client.get("/events/my/")
        assert resp.status_code == 200
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_excludes_other_facilitators_events(self, second_facilitator_client, event):
        resp = second_facilitator_client.get("/events/my/")
        assert resp.status_code == 200
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id not in ids

    def test_includes_total_enrollments(self, facilitator_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = facilitator_client.get("/events/my/")
        event_data = next(e for e in resp.data["results"] if e["id"] == event.id)
        assert event_data["total_enrollments"] == 1

    def test_canceled_enrollments_not_counted(self, facilitator_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_CANCELED)
        resp = facilitator_client.get("/events/my/")
        event_data = next(e for e in resp.data["results"] if e["id"] == event.id)
        assert event_data["total_enrollments"] == 0

    def test_available_seats_calculated(self, facilitator_client, seeker, event):
        Enrollment.objects.create(event=event, seeker=seeker, status=Enrollment.STATUS_ENROLLED)
        resp = facilitator_client.get("/events/my/")
        event_data = next(e for e in resp.data["results"] if e["id"] == event.id)
        assert event_data["available_seats"] == event.capacity - 1

    def test_unlimited_capacity_shows_none_seats(self, facilitator_client, facilitator):
        now = aware_utcnow()
        unlimited = Event.objects.create(
            title="Unlimited",
            description="No cap",
            language="English",
            location="Delhi",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=2),
            capacity=None,
            created_by=facilitator,
        )
        resp = facilitator_client.get("/events/my/")
        event_data = next(e for e in resp.data["results"] if e["id"] == unlimited.id)
        assert event_data["available_seats"] is None

    def test_response_is_paginated(self, facilitator_client):
        resp = facilitator_client.get("/events/my/")
        assert resp.status_code == 200
        assert "count" in resp.data
        assert "results" in resp.data
