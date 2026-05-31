from rest_framework import serializers

from apps.core.utils import aware_utcnow
from apps.events.models import Enrollment, Event


class EventSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "language",
            "location",
            "starts_at",
            "ends_at",
            "capacity",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        # For PATCH, fall back to the existing instance values if a field is absent
        starts_at = attrs.get("starts_at") or (
            self.instance.starts_at if self.instance else None
        )
        ends_at = attrs.get("ends_at") or (
            self.instance.ends_at if self.instance else None
        )

        if starts_at and ends_at and starts_at >= ends_at:
            raise serializers.ValidationError(
                detail="starts_at must be before ends_at.",
                code="invalid_dates",
            )

        # Only block past start times on create; updates may keep an existing starts_at
        if not self.instance and starts_at and starts_at <= aware_utcnow():
            raise serializers.ValidationError(
                detail="Event cannot start in the past.",
                code="event_in_past",
            )

        return attrs


class EventWithCountsSerializer(EventSerializer):
    """
    Extends EventSerializer with enrollment count fields.
    Requires the queryset to be annotated with total_enrollments
    (Count of active enrollments) before serialization.
    """

    total_enrollments = serializers.IntegerField(read_only=True)
    available_seats = serializers.SerializerMethodField()

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ["total_enrollments", "available_seats"]

    def get_available_seats(self, obj):
        if obj.capacity is None:
            return None  # unlimited
        return max(0, obj.capacity - obj.total_enrollments)


class EnrollmentDetailSerializer(serializers.ModelSerializer):
    """Read serializer for seeker enrollment lists — nests full event detail."""

    event = EventSerializer(read_only=True)

    class Meta:
        model = Enrollment
        fields = ["id", "event", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "event", "status", "created_at", "updated_at"]
