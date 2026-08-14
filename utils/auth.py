from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated

from staff.auth import active_staff_for_token, hash_session_token
from staff.models import ListModel, StaffSessionToken
from userprofile.models import Users


class AuthenticatedIdentity:
    """Small request identity shared by the legacy view layer and DRF."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, staff_record, appid='', token_kind='staff'):
        self.id = staff_record.id
        self.staff_id = staff_record.id
        self.staff_name = staff_record.staff_name
        self.staff_type = staff_record.staff_type
        self.openid = staff_record.openid
        self.appid = appid
        self.token_kind = token_kind
        self.is_admin = str(staff_record.staff_type).strip().casefold() == 'admin'

    def __bool__(self):
        return True


def _identity_for_staff(staff_record, token_kind='staff'):
    user_detail = Users.objects.filter(
        openid=staff_record.openid,
        is_delete=False,
    ).first()
    return AuthenticatedIdentity(
        staff_record,
        appid=user_detail.appid if user_detail else '',
        token_kind=token_kind,
    )

class Authtication(object):
    def authenticate(self, request):
        token = request.META.get('HTTP_TOKEN')
        if not token:
            raise NotAuthenticated("Please add a token to your request headers")

        token_hash = hash_session_token(token)
        session = StaffSessionToken.objects.filter(
            token_hash=token_hash,
            is_revoked=False,
        ).first()
        if session is not None:
            if session.expires_at and session.expires_at <= timezone.now():
                raise AuthenticationFailed("Token has expired")
            staff_record = active_staff_for_token(session)
            if staff_record is None or staff_record.is_lock:
                raise AuthenticationFailed("Staff account is unavailable")
            identity = _identity_for_staff(staff_record, session.token_kind)
            if session.token_kind == 'admin' and not identity.is_admin:
                raise AuthenticationFailed("Administrator session is invalid")
            return (identity, identity)

        # Tenant openid values were historically accepted as bearer tokens.
        # Keep an explicit, opt-in migration switch, but disable this unsafe
        # compatibility path by default.
        if getattr(settings, 'ALLOW_LEGACY_OPENID_AUTH', False):
            user_detail = Users.objects.filter(
                openid__exact=str(token),
                is_delete=False,
            ).first()
            if user_detail is not None:
                staff_record = ListModel.objects.filter(
                    openid=user_detail.openid,
                    staff_name=user_detail.name,
                    staff_type__iexact='Admin',
                    is_delete=False,
                ).first()
                if staff_record is not None:
                    identity = _identity_for_staff(staff_record, 'legacy_admin')
                    return (identity, identity)

        raise AuthenticationFailed("Invalid or revoked token")

    def authenticate_header(self, request):
        return 'Token'
