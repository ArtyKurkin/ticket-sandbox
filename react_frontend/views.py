from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie


@login_required
@never_cache
@ensure_csrf_cookie
def readiness(request):
    return render(request, "react_frontend/readiness.html")


@login_required
@never_cache
@ensure_csrf_cookie
def achievements(request):
    from django.urls import reverse

    return render(request, "react_frontend/achievements.html", {
        "trophy_profile": {
            "displayName": request.user.get_full_name() or request.user.get_username(),
            "role": "Наставник" if request.user.is_staff else "Стажёр",
            "sandboxUrl": reverse("sandbox:dashboard"),
        },
    })


@login_required
@never_cache
@ensure_csrf_cookie
def roadmap(request):
    from django.urls import reverse

    return render(request, "react_frontend/roadmap.html", {
        "roadmap_profile": {
            "displayName": request.user.get_full_name() or request.user.get_username(),
            "role": "Наставник" if request.user.is_staff else "Стажёр",
            "canDemo": request.user.is_staff,
            "sandboxUrl": reverse("sandbox:dashboard"),
            "achievementsUrl": reverse("achievements"),
            "initialProgress": {"completed": 1, "trophyCount": 2},
        },
    })
