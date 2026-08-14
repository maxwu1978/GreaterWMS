from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.exceptions import APIException
from django.db import DatabaseError


def _status_for_legacy_api_exception(exc, response):
    """Map legacy APIException uses to client-facing status codes.

    Older GreaterWMS views raise the base APIException for validation and
    duplicate-record errors. Preserve genuine server errors, but keep those
    known client errors from being reported as HTTP 500.
    """
    if not isinstance(exc, APIException) or response.status_code != 500:
        return response.status_code

    detail = response.data.get('detail') if isinstance(response.data, dict) else response.data
    message = str(detail).lower()
    if any(marker in message for marker in ('data exists', 'already exists', 'duplicate', 'has already')):
        return 409
    return 400


def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # Now add the HTTP status code to the response.
    if response is not None:
        status_code = _status_for_legacy_api_exception(exc, response)
        if isinstance(response.data, dict):
            response.data['status_code'] = status_code
        response = Response(
            response.data,
            status=status_code,
            headers=response.headers,
        )
    else:
        if isinstance(exc, DatabaseError):
            pass
            # response = Response({'detail': 'Database Error'})
        else:
            pass
            # response = Response({'detail': 'Other Error'})
    return response
