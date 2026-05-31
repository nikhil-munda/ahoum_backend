from datetime import timedelta

import pytest

from apps.core.utils import aware_utcnow
from apps.events.models import Event

EVENTS = "/events/"


def make_event(facilitator, **kwargs):
    now = aware_utcnow()
    defaults = {
        "title": "Event",
        "description": "Description",
        "language": "English",
        "location": "Delhi",
        "starts_at": now + timedelta(days=1),
        "ends_at": now + timedelta(days=2),
        "capacity": 10,
        "created_by": facilitator,
    }
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


@pytest.mark.django_db
class TestEventSearch:
    def test_list_only_returns_non_ended_events(self, seeker_client, event, past_event):
        resp = seeker_client.get(EVENTS)
        assert resp.status_code == 200
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids
        assert past_event.id not in ids

    def test_pagination_shape(self, seeker_client, event):
        resp = seeker_client.get(EVENTS)
        assert resp.status_code == 200
        for key in ("count", "next", "previous", "results"):
            assert key in resp.data

    # ── location ─────────────────────────────────────────────────────────────

    def test_location_filter_case_insensitive(self, seeker_client, event):
        # event is in "New Delhi"
        resp = seeker_client.get(f"{EVENTS}?location=delhi")
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_location_filter_partial_match(self, seeker_client, event):
        resp = seeker_client.get(f"{EVENTS}?location=New")
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_location_filter_no_match(self, seeker_client, event):
        resp = seeker_client.get(f"{EVENTS}?location=Tokyo")
        assert resp.data["count"] == 0

    # ── language ─────────────────────────────────────────────────────────────

    def test_language_filter_exact(self, seeker_client, event):
        resp = seeker_client.get(f"{EVENTS}?language=English")
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_language_filter_case_insensitive(self, seeker_client, event):
        resp = seeker_client.get(f"{EVENTS}?language=english")
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_language_filter_excludes_other_language(self, seeker_client, facilitator):
        now = aware_utcnow()
        hindi_event = make_event(facilitator, language="Hindi", title="Hindi Event")
        english_event = make_event(facilitator, language="English", title="English Event")
        resp = seeker_client.get(f"{EVENTS}?language=Hindi")
        ids = [e["id"] for e in resp.data["results"]]
        assert hindi_event.id in ids
        assert english_event.id not in ids

    # ── q (title / description) ───────────────────────────────────────────────

    def test_q_searches_title(self, seeker_client, event):
        # event.title == "Test Event"
        resp = seeker_client.get(f"{EVENTS}?q=Test")
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_q_searches_description(self, seeker_client, event):
        # event.description == "A test event description"
        resp = seeker_client.get(f"{EVENTS}?q=description")
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_q_case_insensitive(self, seeker_client, event):
        resp = seeker_client.get(f"{EVENTS}?q=TEST EVENT")
        ids = [e["id"] for e in resp.data["results"]]
        assert event.id in ids

    def test_q_no_match(self, seeker_client, event):
        resp = seeker_client.get(f"{EVENTS}?q=xyznonexistent")
        assert resp.data["count"] == 0

    # ── starts_after / starts_before ─────────────────────────────────────────

    def test_starts_after_filter(self, seeker_client, facilitator):
        now = aware_utcnow()
        early = make_event(facilitator, title="Early", starts_at=now + timedelta(hours=2), ends_at=now + timedelta(hours=4))
        late = make_event(facilitator, title="Late", starts_at=now + timedelta(days=10), ends_at=now + timedelta(days=11))
        # isoformat() on a UTC-aware datetime produces "+00:00" which becomes
        # a literal "+" (space) in URL query strings; use "Z" suffix instead.
        cutoff = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = seeker_client.get(f"{EVENTS}?starts_after={cutoff}")
        ids = [e["id"] for e in resp.data["results"]]
        assert late.id in ids
        assert early.id not in ids

    def test_starts_before_filter(self, seeker_client, facilitator):
        now = aware_utcnow()
        early = make_event(facilitator, title="Early2", starts_at=now + timedelta(hours=2), ends_at=now + timedelta(hours=4))
        late = make_event(facilitator, title="Late2", starts_at=now + timedelta(days=10), ends_at=now + timedelta(days=11))
        cutoff = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = seeker_client.get(f"{EVENTS}?starts_before={cutoff}")
        ids = [e["id"] for e in resp.data["results"]]
        assert early.id in ids
        assert late.id not in ids

    def test_combined_filters(self, seeker_client, facilitator):
        now = aware_utcnow()
        target = make_event(
            facilitator,
            title="Target Event",
            language="French",
            location="Paris",
            starts_at=now + timedelta(days=3),
            ends_at=now + timedelta(days=4),
        )
        other = make_event(facilitator, language="Spanish", location="Madrid", title="Other")
        resp = seeker_client.get(f"{EVENTS}?language=French&location=Paris")
        ids = [e["id"] for e in resp.data["results"]]
        assert target.id in ids
        assert other.id not in ids
