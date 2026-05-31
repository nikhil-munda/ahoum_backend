from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.events.views import EventViewSet, PastEnrollmentsView, UpcomingEnrollmentsView

router = DefaultRouter()
router.register(r"events", EventViewSet, basename="event")

app_name = "events"

urlpatterns = [
    path("", include(router.urls)),
    path("enrollments/upcoming/", UpcomingEnrollmentsView.as_view(), name="enrollments_upcoming"),
    path("enrollments/past/", PastEnrollmentsView.as_view(), name="enrollments_past"),
]
