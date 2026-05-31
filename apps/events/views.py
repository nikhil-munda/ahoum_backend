from django.db import transaction
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.permissions import IsEmailVerified, IsFacilitator, IsSeeker
from apps.core.utils import aware_utcnow
from apps.events.filters import EventFilter
from apps.events.models import Enrollment, Event
from apps.events.permissions import IsEventOwner
from apps.events.serializers import (
    EnrollmentDetailSerializer,
    EventSerializer,
    EventWithCountsSerializer,
)


class EventViewSet(ModelViewSet):
    """
    Handles all event CRUD, the facilitator dashboard, and seeker enrollment.

    Action → permission mapping
    ───────────────────────────
    list              IsSeeker
    create            IsFacilitator
    retrieve          any authenticated + verified
    update / partial  IsFacilitator + IsEventOwner (object-level)
    destroy           IsFacilitator + IsEventOwner (object-level)
    my_events         IsFacilitator
    enroll            IsSeeker
    """

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = EventFilter
    ordering = ["starts_at"]
    ordering_fields = ["starts_at", "title"]

    # ── Permissions ───────────────────────────────────────────────────────────

    def get_permissions(self):
        if self.action == "list":
            perms = [IsAuthenticated, IsEmailVerified, IsSeeker]
        elif self.action == "create":
            perms = [IsAuthenticated, IsEmailVerified, IsFacilitator]
        elif self.action in ("update", "partial_update", "destroy"):
            # IsEventOwner.has_permission returns True; object check fires in get_object()
            perms = [IsAuthenticated, IsEmailVerified, IsFacilitator, IsEventOwner]
        elif self.action == "my_events":
            perms = [IsAuthenticated, IsEmailVerified, IsFacilitator]
        elif self.action == "enroll":
            perms = [IsAuthenticated, IsEmailVerified, IsSeeker]
        else:
            # retrieve — any authenticated, verified user
            perms = [IsAuthenticated, IsEmailVerified]
        return [p() for p in perms]

    # ── Serializer ────────────────────────────────────────────────────────────

    def get_serializer_class(self):
        if self.action == "my_events":
            return EventWithCountsSerializer
        return EventSerializer

    # ── Queryset ──────────────────────────────────────────────────────────────

    def get_queryset(self):
        if self.action == "my_events":
            return (
                Event.objects.filter(created_by=self.request.user)
                .annotate(
                    total_enrollments=Count(
                        "enrollments",
                        filter=Q(enrollments__status=Enrollment.STATUS_ENROLLED),
                    )
                )
                .order_by("starts_at")
            )

        if self.action == "list":
            # Seekers browse events that have not yet ended
            return Event.objects.filter(ends_at__gt=aware_utcnow())

        # retrieve, update, partial_update, destroy, enroll — all events
        return Event.objects.all()

    # ── Write helpers ─────────────────────────────────────────────────────────

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.enrollments.filter(status=Enrollment.STATUS_ENROLLED).exists():
            raise ValidationError(
                detail="Cannot delete an event that has active enrollments.",
                code="event_has_active_enrollments",
            )
        instance.delete()

    # ── Custom actions ────────────────────────────────────────────────────────

    @action(detail=False, methods=["get"], url_path="my")
    def my_events(self, request):
        """GET /events/my/ — Facilitator dashboard with enrollment counts."""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post", "delete"], url_path="enroll")
    def enroll(self, request, pk=None):
        """POST /events/{id}/enroll/ — Enroll. DELETE — Cancel enrollment."""
        event = self.get_object()
        if request.method == "POST":
            return self._handle_enroll(request, event)
        return self._handle_cancel(request, event)

    # ── Enrollment business logic ─────────────────────────────────────────────

    def _handle_enroll(self, request, event):
        seeker = request.user

        with transaction.atomic():
            # Lock the event row so concurrent requests see an accurate count
            locked = Event.objects.select_for_update().get(pk=event.pk)

            if aware_utcnow() >= locked.ends_at:
                raise ValidationError(
                    detail="This event has already ended.",
                    code="event_already_ended",
                )

            already_enrolled = Enrollment.objects.filter(
                event=locked,
                seeker=seeker,
                status=Enrollment.STATUS_ENROLLED,
            ).exists()
            if already_enrolled:
                raise ValidationError(
                    detail="You are already enrolled in this event.",
                    code="already_enrolled",
                )

            if locked.capacity is not None:
                active_count = Enrollment.objects.filter(
                    event=locked,
                    status=Enrollment.STATUS_ENROLLED,
                ).count()
                if active_count >= locked.capacity:
                    raise ValidationError(
                        detail="This event is at full capacity.",
                        code="event_full",
                    )

            Enrollment.objects.create(event=locked, seeker=seeker)

        return Response(
            {"detail": "Successfully enrolled in the event."},
            status=status.HTTP_201_CREATED,
        )

    def _handle_cancel(self, request, event):
        try:
            enrollment = Enrollment.objects.get(
                event=event,
                seeker=request.user,
                status=Enrollment.STATUS_ENROLLED,
            )
        except Enrollment.DoesNotExist:
            raise NotFound(
                detail="No active enrollment found for this event.",
                code="not_found",
            )

        enrollment.status = Enrollment.STATUS_CANCELED
        enrollment.save(update_fields=["status", "updated_at"])

        return Response(
            {"detail": "Enrollment canceled successfully."},
            status=status.HTTP_200_OK,
        )


class UpcomingEnrollmentsView(ListAPIView):
    """GET /enrollments/upcoming/ — Seeker's active enrollments in future events."""

    permission_classes = [IsAuthenticated, IsEmailVerified, IsSeeker]
    serializer_class = EnrollmentDetailSerializer

    def get_queryset(self):
        return (
            Enrollment.objects.filter(
                seeker=self.request.user,
                status=Enrollment.STATUS_ENROLLED,
                event__ends_at__gt=aware_utcnow(),
            )
            .select_related("event", "event__created_by")
            .order_by("event__starts_at")
        )


class PastEnrollmentsView(ListAPIView):
    """GET /enrollments/past/ — Seeker's active enrollments in ended events."""

    permission_classes = [IsAuthenticated, IsEmailVerified, IsSeeker]
    serializer_class = EnrollmentDetailSerializer

    def get_queryset(self):
        return (
            Enrollment.objects.filter(
                seeker=self.request.user,
                status=Enrollment.STATUS_ENROLLED,
                event__ends_at__lte=aware_utcnow(),
            )
            .select_related("event", "event__created_by")
            .order_by("-event__starts_at")
        )
