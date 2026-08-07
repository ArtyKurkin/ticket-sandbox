from django.contrib.auth.decorators import (
    login_required,
)
from django.http import JsonResponse
from django.shortcuts import redirect

from assessment.models import ExamAssignment


@login_required
def home(request):
    if request.user.is_staff:
        return redirect(
            "traineediary:dashboard",
        )

    has_assessment = (
        ExamAssignment.objects.filter(
            employee__user=request.user,
            employee__is_active=True,
            is_active=True,
        ).exists()
    )

    if has_assessment:
        return redirect(
            "assessment:dashboard",
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
