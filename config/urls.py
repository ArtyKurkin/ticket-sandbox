from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from react_frontend.views import achievements, readiness, roadmap
from config.views import (
    healthz,
    home,
)


urlpatterns = [
    path("", home, name="home"),

    path("api/roadmap/", include("roadmap.urls")),
    path("api/achievements/", include("achievements.urls")),

    path("roadmap/", roadmap, name="roadmap"),

    path("achievements/", achievements, name="achievements"),

    path("internal/react-readiness/", readiness, name="react-readiness"),

    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),

    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path("", include("sandbox.urls")),

    path("diary/", include("traineediary.urls", namespace="traineediary")),
    path(
        "assessment/",
        include(
            "assessment.urls",
            namespace="assessment",
        ),
    ),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
