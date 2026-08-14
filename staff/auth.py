"""Staff and administrator API session token helpers.

The legacy ``Users.openid`` value identifies a tenant.  It is not a
credential and must not be accepted as one by the API.  Session tokens are
stored as hashes so a database read does not expose reusable credentials.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import ListModel, StaffSessionToken


def hash_session_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def issue_session_token(staff_record, token_kind="staff"):
    """Create and return a raw token; only its hash is persisted."""
    raw_token = "gwms_{}".format(secrets.token_urlsafe(32))
    ttl_days = max(1, int(getattr(settings, "AUTH_SESSION_TTL_DAYS", 30)))
    StaffSessionToken.objects.create(
        staff_id=staff_record.id,
        openid=staff_record.openid,
        token_hash=hash_session_token(raw_token),
        token_kind=token_kind,
        expires_at=timezone.now() + timedelta(days=ttl_days),
    )
    return raw_token


def revoke_staff_tokens(staff_id, openid=None):
    filters = {"staff_id": staff_id, "is_revoked": False}
    if openid is not None:
        filters["openid"] = openid
    return StaffSessionToken.objects.filter(**filters).update(
        is_revoked=True,
        revoked_at=timezone.now(),
    )


def active_staff_for_token(session):
    return ListModel.objects.filter(
        id=session.staff_id,
        openid=session.openid,
        is_delete=False,
    ).first()
