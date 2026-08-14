from django.db import connection, DatabaseError
from django.http import JsonResponse


def health(request):
    """Return a small, unauthenticated readiness response for Render."""
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "error"}, status=503)

    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response
