from datetime import timedelta

import pytest

from apps.core.utils import aware_utcnow

EVENTS = "/events/"
MY_EVENTS = "/events/my/"
UPCOMING = "/enrollments/upcoming/"
PAST = "/enrollments/past/"


def future_event_payload():
    now = aware_utcnow()
    return {
        "title": "RBAC Test Event",
        "description": "Testing RBAC",
        "language": "English",
        "location": "Delhi",
        "starts_at": (now + timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=2)).isoformat(),
        "capacity": 5,
    }


# ── Seeker restrictions ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSeekerRestrictions:
    def test_cannot_create_event(self, seeker_client):
        resp = seeker_client.post(EVENTS, future_event_payload())
        assert resp.status_code == 403

    def test_cannot_update_event(self, seeker_client, event):
        resp = seeker_client.patch(f"/events/{event.id}/", {"title": "Hacked"})
        assert resp.status_code == 403

    def test_cannot_full_update_event(self, seeker_client, event):
        resp = seeker_client.put(f"/events/{event.id}/", future_event_payload())
        assert resp.status_code == 403

    def test_cannot_delete_event(self, seeker_client, event):
        resp = seeker_client.delete(f"/events/{event.id}/")
        assert resp.status_code == 403

    def test_cannot_access_my_events(self, seeker_client):
        resp = seeker_client.get(MY_EVENTS)
        assert resp.status_code == 403


# ── Facilitator restrictions ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestFacilitatorRestrictions:
    def test_cannot_enroll(self, facilitator_client, event):
        resp = facilitator_client.post(f"/events/{event.id}/enroll/")
        assert resp.status_code == 403

    def test_cannot_cancel_enrollment(self, facilitator_client, event):
        resp = facilitator_client.delete(f"/events/{event.id}/enroll/")
        assert resp.status_code == 403

    def test_cannot_view_upcoming_enrollments(self, facilitator_client):
        resp = facilitator_client.get(UPCOMING)
        assert resp.status_code == 403

    def test_cannot_view_past_enrollments(self, facilitator_client):
        resp = facilitator_client.get(PAST)
        assert resp.status_code == 403

    def test_cannot_search_events(self, facilitator_client):
        # GET /events/ is Seeker-only
        resp = facilitator_client.get(EVENTS)
        assert resp.status_code == 403


# ── Ownership checks ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOwnershipChecks:
    def test_non_owner_cannot_update(self, second_facilitator_client, event):
        resp = second_facilitator_client.patch(f"/events/{event.id}/", {"title": "Stolen"})
        assert resp.status_code == 403

    def test_non_owner_cannot_delete(self, second_facilitator_client, event):
        resp = second_facilitator_client.delete(f"/events/{event.id}/")
        assert resp.status_code == 403

    def test_owner_can_update(self, facilitator_client, event):
        resp = facilitator_client.patch(f"/events/{event.id}/", {"title": "Updated"})
        assert resp.status_code == 200

    def test_owner_can_delete(self, facilitator_client, event):
        resp = facilitator_client.delete(f"/events/{event.id}/")
        assert resp.status_code == 204


# ── Unauthenticated access ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestUnauthenticatedAccess:
    def test_cannot_list_events(self, api_client):
        resp = api_client.get(EVENTS)
        assert resp.status_code == 401

    def test_cannot_create_event(self, api_client):
        resp = api_client.post(EVENTS, future_event_payload())
        assert resp.status_code == 401

    def test_cannot_retrieve_event(self, api_client, event):
        resp = api_client.get(f"/events/{event.id}/")
        assert resp.status_code == 401

    def test_cannot_access_enrollments(self, api_client):
        resp = api_client.get(UPCOMING)
        assert resp.status_code == 401
