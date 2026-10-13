from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie


@login_required
@never_cache
@ensure_csrf_cookie
def readiness(request):
    return render(request, "react_frontend/readiness.html")
