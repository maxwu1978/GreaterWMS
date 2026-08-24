"""
Request middleware — logging, rate limiting, request ID tracking.
"""

import logging
import time
import uuid
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("wms.middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with timing, tenant context, and unique request ID."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # Extract tenant from JWT if present (already decoded by deps)
        tenant_id = getattr(request.state, "tenant_id", "-")

        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} ({duration_ms}ms)",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "tenant_id": tenant_id,
            },
        )

        response.headers["X-Request-ID"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiter.
    In production, use Redis-based rate limiting for multi-instance deployments.
    """

    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Skip health checks and static files
        if request.url.path in ("/health", "/api/docs", "/api/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        # Clean old entries
        self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < 60]

        if len(self.requests[client_ip]) >= self.rpm:
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        self.requests[client_ip].append(now)
        return await call_next(request)
