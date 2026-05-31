from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
    path("", include("apps.events.urls", namespace="events")),
]
