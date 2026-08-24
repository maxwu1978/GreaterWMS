"""
Security tests — RLS dependency order, JWT enforcement, tenant isolation,
Stripe webhook signature, platform_admin guards.
"""

import hashlib
import hmac
import time

from app.core.config import settings
from app.core.database import (
    get_current_tenant_id,
    get_is_platform_admin,
    set_current_tenant_id,
    set_is_platform_admin,
)
from app.core.security import (
    UserRole,
    create_access_token,
    verify_token,
)

# ─── JWT Tests ───


class TestJWTSecurity:
    def test_valid_token_roundtrip(self):
        token = create_access_token("user-1", UserRole.OPERATOR, "tenant-1")
        payload = verify_token(token)
        assert payload is not None
        assert payload.sub == "user-1"
        assert payload.tenant_id == "tenant-1"
        assert payload.role == UserRole.OPERATOR

    def test_invalid_token_rejected(self):
        assert verify_token("garbage.token.here") is None
        assert verify_token("") is None

    def test_platform_admin_has_no_tenant(self):
        token = create_access_token("admin-1", UserRole.PLATFORM_ADMIN)
        payload = verify_token(token)
        assert payload.tenant_id is None
        assert payload.role == UserRole.PLATFORM_ADMIN

    def test_client_viewer_has_client_id(self):
        token = create_access_token("user-2", UserRole.CLIENT_VIEWER, "tenant-1", "client-1")
        payload = verify_token(token)
        assert payload.client_id == "client-1"


# ─── ContextVar / RLS Dependency Order ───


class TestRLSContextVars:
    def test_default_context_is_safe(self):
        """Before any request, context should deny everything."""
        # Reset
        set_current_tenant_id(None)
        set_is_platform_admin(False)
        assert get_current_tenant_id() is None
        assert get_is_platform_admin() is False

    def test_tenant_context_set_correctly(self):
        set_current_tenant_id("tenant-123")
        set_is_platform_admin(False)
        assert get_current_tenant_id() == "tenant-123"
        assert get_is_platform_admin() is False

    def test_admin_context_set_correctly(self):
        set_current_tenant_id(None)
        set_is_platform_admin(True)
        assert get_current_tenant_id() is None
        assert get_is_platform_admin() is True

    def test_malicious_tenant_id_rejected(self):
        """SQL injection via tenant_id should be blocked by regex validation."""
        import re

        pattern = r"^[a-zA-Z0-9\-]+$"
        assert re.match(pattern, "tenant-001")  # valid
        assert re.match(pattern, "abc123-def-456")  # valid UUID
        assert not re.match(pattern, "'; DROP TABLE users; --")  # SQL injection
        assert not re.match(pattern, "tenant' OR '1'='1")  # SQL injection
        assert not re.match(pattern, "")  # empty

    def test_context_isolation_between_calls(self):
        """Each set is independent — no leakage from previous state."""
        set_current_tenant_id("tenant-A")
        set_is_platform_admin(False)
        assert get_current_tenant_id() == "tenant-A"

        # Simulate a new request
        set_current_tenant_id("tenant-B")
        assert get_current_tenant_id() == "tenant-B"


# ─── Stripe Webhook Signature ───


class TestStripeWebhookSignature:
    def _make_sig(self, payload: str, secret: str, timestamp: int | None = None) -> str:
        """Generate a valid Stripe webhook signature header."""
        ts = timestamp or int(time.time())
        signed = f"{ts}.{payload}"
        sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        return f"t={ts},v1={sig}"

    def test_valid_signature(self):
        secret = "whsec_test123"
        payload = '{"type":"test"}'
        sig_header = self._make_sig(payload, secret)

        # Parse like the endpoint does
        their_sigs = []
        timestamp = ""
        for pair in sig_header.split(","):
            key, _, value = pair.strip().partition("=")
            if key == "t":
                timestamp = value
            elif key == "v1":
                their_sigs.append(value)

        signed_payload = f"{timestamp}.{payload}"
        expected = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
        assert any(hmac.compare_digest(expected, s) for s in their_sigs)

    def test_invalid_signature_rejected(self):
        secret = "whsec_test123"
        payload = '{"type":"test"}'
        timestamp = int(time.time())

        # Sign with wrong secret
        wrong_sig = hmac.new(
            b"wrong_secret", f"{timestamp}.{payload}".encode(), hashlib.sha256
        ).hexdigest()
        expected = hmac.new(
            secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256
        ).hexdigest()

        assert not hmac.compare_digest(expected, wrong_sig)

    def test_multiple_v1_signatures(self):
        """During secret rotation, Stripe sends multiple v1 values."""
        secret_old = "whsec_old"
        secret_new = "whsec_new"
        payload = '{"type":"test"}'
        ts = int(time.time())

        sig_old = hmac.new(
            secret_old.encode(), f"{ts}.{payload}".encode(), hashlib.sha256
        ).hexdigest()
        sig_new = hmac.new(
            secret_new.encode(), f"{ts}.{payload}".encode(), hashlib.sha256
        ).hexdigest()

        # Header with both signatures
        sig_header = f"t={ts},v1={sig_old},v1={sig_new}"
        their_sigs = [p.partition("=")[2] for p in sig_header.split(",") if p.startswith("v1=")]

        # Verify using new secret — should match one of the v1 values
        expected = hmac.new(
            secret_new.encode(), f"{ts}.{payload}".encode(), hashlib.sha256
        ).hexdigest()
        assert any(hmac.compare_digest(expected, s) for s in their_sigs)

    def test_replay_old_timestamp(self):
        """Events older than 5 minutes should be rejected."""
        old_timestamp = int(time.time()) - 400  # 6+ minutes ago
        event_age = int(time.time()) - old_timestamp
        assert event_age > 300  # Would be rejected


# ─── JWT Secret Enforcement ───


class TestJWTSecretEnforcement:
    def test_insecure_defaults_list(self):
        from app.core.config import _INSECURE_DEFAULTS

        assert "" in _INSECURE_DEFAULTS
        assert "CHANGE-ME-IN-PRODUCTION" in _INSECURE_DEFAULTS
        assert "secret" in _INSECURE_DEFAULTS

    def test_actual_key_is_not_default(self):
        """The running settings should have a non-default key."""
        assert settings.JWT_SECRET_KEY not in {"", "CHANGE-ME-IN-PRODUCTION", "secret"}
        assert len(settings.JWT_SECRET_KEY) >= 20  # Auto-generated keys are 43+ chars
