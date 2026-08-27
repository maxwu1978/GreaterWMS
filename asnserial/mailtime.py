"""Mailbox timestamp normalization for the Mail2Task projection.

The legacy GreaterWMS application uses naive datetimes for its existing WMS
tables. Mail timestamps are therefore normalized to the mailbox's local zone
before they enter the Mail2Task projection, while the raw header value remains
in source metadata for audit.
"""

from datetime import datetime, time
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone


MAILBOX_TIME_ZONE = ZoneInfo('America/Chicago')
EXACT = 'EXACT'
DATE_ONLY = 'DATE_ONLY'
UNKNOWN = 'UNKNOWN'


def _raw(value):
    return str(value or '').strip()


def mail_time_precision(value, explicit=''):
    explicit = _raw(explicit).upper()
    if explicit in {EXACT, DATE_ONLY, UNKNOWN}:
        return explicit
    raw = _raw(value)
    if not raw:
        return UNKNOWN
    if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', raw) or re.fullmatch(r'\d{4}年\d{1,2}月\d{1,2}日', raw):
        return DATE_ONLY
    if parse_date(raw) is not None and parse_datetime(raw) is None:
        return DATE_ONLY
    return EXACT if parse_datetime(raw.replace('Z', '+00:00')) is not None else UNKNOWN


def parse_mail_datetime(value):
    """Parse an email timestamp and normalize it to the mailbox timezone.

    The current legacy settings use ``USE_TZ=False``. In that mode, an aware
    timestamp must be made naive only after conversion to America/Chicago;
    otherwise the legacy Asia/Shanghai setting shifts US mailbox times.
    """
    raw = _raw(value)
    if not raw:
        return None
    parsed = parse_datetime(raw.replace('Z', '+00:00'))
    if parsed is None:
        parsed_date = parse_date(raw)
        if parsed_date is None:
            return None
        parsed = datetime.combine(parsed_date, time.min)
    if timezone.is_aware(parsed):
        local = parsed.astimezone(MAILBOX_TIME_ZONE)
        if getattr(settings, 'USE_TZ', False):
            return local
        return local.replace(tzinfo=None)
    if getattr(settings, 'USE_TZ', False):
        return timezone.make_aware(parsed, MAILBOX_TIME_ZONE)
    return parsed


def latest_mail_datetime(sent_at=None, received_at=None):
    """Return the latest known mail timestamp without using capture time."""
    values = [value for value in (sent_at, received_at) if value is not None]
    return max(values) if values else None
