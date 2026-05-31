from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def home(request):
    return JsonResponse(
        {
            "detail": "Ahoum API is running.",
            "endpoints": ["/auth/", "/events/", "/admin/"],
        }
    )

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
    path("", include("apps.events.urls", namespace="events")),
]
