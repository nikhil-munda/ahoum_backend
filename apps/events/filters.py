import django_filters
from django.db.models import Q

from apps.events.models import Event


class EventFilter(django_filters.FilterSet):
    location = django_filters.CharFilter(field_name="location", lookup_expr="icontains")
    language = django_filters.CharFilter(field_name="language", lookup_expr="iexact")
    starts_after = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_before = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lte")
    q = django_filters.CharFilter(method="search_q")

    class Meta:
        model = Event
        fields = ["location", "language", "starts_after", "starts_before", "q"]

    def search_q(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
