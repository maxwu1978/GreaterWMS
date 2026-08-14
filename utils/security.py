"""Security middleware used by the token-based WMS API.

The browser application authenticates API requests with the custom ``Token``
header rather than a session cookie.  Those requests do not need CSRF tokens,
but Django session-backed views (including the admin) still do.
"""

from django.utils.deprecation import MiddlewareMixin


class TokenCsrfBypassMiddleware(MiddlewareMixin):
    """Mark token API requests as CSRF-exempt before Django's standard check.

    The standard ``CsrfViewMiddleware`` remains enabled for session-backed
    views. Token requests do not rely on cookies, so a CSRF token would add no
    protection and would break the existing browser and CLI clients.
    """

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.META.get("HTTP_TOKEN"):
            request._dont_enforce_csrf_checks = True
        return None


class SecurityHeadersMiddleware:
    """Add response headers that are safe for the existing SPA and API."""

    content_security_policy = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "connect-src 'self' https:"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.content_security_policy)
        response.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Referrer-Policy", "same-origin")
        return response
