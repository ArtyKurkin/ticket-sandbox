from django.contrib.auth.decorators import (
    login_required,
)
from django.http import JsonResponse
from django.shortcuts import redirect


@login_required
def home(request):
    if request.user.is_staff:
        return redirect(
            "traineediary:dashboard",
        )

    return redirect(
        "sandbox:dashboard",
    )


def healthz(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "ticket-sandbox",
        },
    )
