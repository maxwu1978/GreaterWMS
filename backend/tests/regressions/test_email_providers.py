"""Regression tests: email providers (split from tests/test_regressions.py)."""

import pytest

from app.services import email_service
from tests.regressions.helpers import _disable_email_provider_settings


@pytest.mark.asyncio
async def test_resend_email_provider_sends_password_reset_via_http_api(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(
        email_service.settings,
        "RESEND_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    assert email_service.email_delivery_enabled() is True

    result = await email_service.send_password_reset_email(
        to_email="reset@example.com",
        company_name="WMS QuickStart",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert result == {"success": True}
    assert captured["url"] == email_service.RESEND_API_URL
    assert captured["headers"] == {
        "Authorization": "Bearer re_test_key",
        "Content-Type": "application/json",
    }
    assert captured["json"]["from"] == "WMS QuickStart <no-reply@example.com>"
    assert captured["json"]["to"] == ["reset@example.com"]
    assert captured["json"]["subject"] == "Reset your password for WMS QuickStart"
    assert "https://app.example.com/reset-password?token=abc" in captured["json"]["html"]


@pytest.mark.asyncio
async def test_brevo_email_provider_sends_password_reset_via_http_api(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(email_service.settings, "BREVO_API_KEY", "xkeysib_test_key")
    monkeypatch.setattr(
        email_service.settings,
        "BREVO_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    assert email_service.email_delivery_enabled() is True

    result = await email_service.send_password_reset_email(
        to_email="reset@example.com",
        company_name="WMS QuickStart",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert result == {"success": True}
    assert captured["url"] == email_service.BREVO_API_URL
    assert captured["headers"] == {
        "api-key": "xkeysib_test_key",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    assert captured["json"]["sender"] == {
        "name": "WMS QuickStart",
        "email": "no-reply@example.com",
    }
    assert captured["json"]["to"] == [{"email": "reset@example.com"}]
    assert captured["json"]["subject"] == "Reset your password for WMS QuickStart"
    assert "https://app.example.com/reset-password?token=abc" in captured["json"]["htmlContent"]


@pytest.mark.asyncio
async def test_smtp2go_email_provider_sends_survey_attachment_via_http_api(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "smtp2go")
    monkeypatch.setattr(email_service.settings, "SMTP2GO_API_KEY", "api-test-key")
    monkeypatch.setattr(
        email_service.settings,
        "SMTP2GO_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_survey_email(
        to_email="ops@example.com",
        company_name="ACME Warehouse",
        contact_name="Alice",
        contact_email="alice@example.com",
        summary="Ready for assessment.",
        pdf_base64="cGRm",
    )

    assert result == {"success": True}
    assert captured["url"] == email_service.SMTP2GO_API_URL
    assert captured["headers"] == {
        "X-Smtp2go-Api-Key": "api-test-key",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    assert captured["json"]["sender"] == "WMS QuickStart <no-reply@example.com>"
    assert captured["json"]["to"] == ["ops@example.com"]
    assert captured["json"]["subject"] == "WMS Assessment: ACME Warehouse — Alice"
    assert captured["json"]["attachments"] == [
        {
            "filename": "WMS-Assessment-ACME-Warehouse.pdf",
            "fileblob": "cGRm",
            "mimetype": "application/pdf",
        }
    ]


@pytest.mark.asyncio
async def test_mailersend_email_provider_sends_password_reset_via_http_api(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "mailersend")
    monkeypatch.setattr(email_service.settings, "MAILERSEND_API_KEY", "mlsn.test-token")
    monkeypatch.setattr(
        email_service.settings,
        "MAILERSEND_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_password_reset_email(
        to_email="reset@example.com",
        company_name="WMS QuickStart",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert result == {"success": True}
    assert captured["url"] == email_service.MAILERSEND_API_URL
    assert captured["headers"] == {
        "Authorization": "Bearer mlsn.test-token",
        "Content-Type": "application/json",
    }
    assert captured["json"]["from"] == {
        "name": "WMS QuickStart",
        "email": "no-reply@example.com",
    }
    assert captured["json"]["to"] == [{"email": "reset@example.com"}]
    assert captured["json"]["subject"] == "Reset your password for WMS QuickStart"
    assert "https://app.example.com/reset-password?token=abc" in captured["json"]["html"]


@pytest.mark.asyncio
async def test_email_provider_falls_back_after_selected_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {"urls": []}

    class FailingResponse:
        def raise_for_status(self) -> None:
            raise RuntimeError("403 Forbidden")

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["urls"].append(url)
            captured["json"] = json
            captured["headers"] = headers
            if url == email_service.MAILERSEND_API_URL:
                return FailingResponse()
            return SuccessfulResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "mailersend")
    monkeypatch.setattr(email_service.settings, "MAILERSEND_API_KEY", "mlsn.test-token")
    monkeypatch.setattr(
        email_service.settings,
        "MAILERSEND_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.settings, "SMTP2GO_API_KEY", "smtp2go-test-token")
    monkeypatch.setattr(
        email_service.settings,
        "SMTP2GO_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_verification_email(
        to_email="new-admin@example.com",
        company_name="WMS QuickStart",
        verification_url="https://api.example.com/verify-email?token=abc",
    )

    assert result == {"success": True}
    assert captured["urls"] == [
        email_service.MAILERSEND_API_URL,
        email_service.SMTP2GO_API_URL,
    ]
    assert captured["headers"] == {
        "X-Smtp2go-Api-Key": "smtp2go-test-token",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    assert captured["json"]["sender"] == "WMS QuickStart <no-reply@example.com>"
    assert captured["json"]["to"] == ["new-admin@example.com"]


@pytest.mark.asyncio
async def test_password_reset_email_uses_provider_fallback_chain(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {"urls": []}

    class FailingResponse:
        def raise_for_status(self) -> None:
            raise RuntimeError("403 Forbidden")

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["urls"].append(url)
            captured["json"] = json
            captured["headers"] = headers
            if url == email_service.RESEND_API_URL:
                return FailingResponse()
            return SuccessfulResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(
        email_service.settings,
        "RESEND_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.settings, "MAILERSEND_API_KEY", "mlsn.test-token")
    monkeypatch.setattr(
        email_service.settings,
        "MAILERSEND_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_password_reset_email(
        to_email="reset@example.com",
        company_name="WMS QuickStart",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert result == {"success": True}
    assert captured["urls"] == [
        email_service.RESEND_API_URL,
        email_service.MAILERSEND_API_URL,
    ]
    assert captured["headers"] == {
        "Authorization": "Bearer mlsn.test-token",
        "Content-Type": "application/json",
    }
    assert captured["json"]["to"] == [{"email": "reset@example.com"}]
    assert "https://app.example.com/reset-password?token=abc" in captured["json"]["html"]


@pytest.mark.asyncio
async def test_email_provider_diagnostic_reports_safe_failover_attempts(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {"urls": []}

    class FailingResponse:
        def raise_for_status(self) -> None:
            raise RuntimeError("403 Forbidden token=mlsn.secret-token-that-must-not-leak")

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["urls"].append(url)
            if url == email_service.MAILERSEND_API_URL:
                return FailingResponse()
            return SuccessfulResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "mailersend")
    monkeypatch.setattr(email_service.settings, "MAILERSEND_API_KEY", "mlsn.secret-token")
    monkeypatch.setattr(
        email_service.settings,
        "MAILERSEND_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.settings, "SMTP2GO_API_KEY", "smtp2go-test-token")
    monkeypatch.setattr(
        email_service.settings,
        "SMTP2GO_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_email_provider_diagnostic("ops@example.com")

    assert result["success"] is True
    assert result["selected_provider"] == "mailersend"
    assert result["delivered_by"] == "smtp2go"
    assert result["attempts"] == [
        {
            "provider": "mailersend",
            "success": False,
            "error": "403 Forbidden token=<redacted>",
        },
        {"provider": "smtp2go", "success": True},
    ]
    assert "mlsn.secret-token" not in str(result)
    assert result["status"]["delivery_enabled"] is True
    assert result["status"]["configured_candidates"] == ["mailersend", "smtp2go"]
    assert result["status"]["requested_provider_supported"] is True
    assert result["status"]["requested_provider_ready"] is True
    assert result["status"]["requested_provider_missing"] == []


def test_email_provider_status_reports_unsupported_or_unready_requested_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "smtp2go")
    monkeypatch.setattr(email_service.settings, "MAILERSEND_API_KEY", "mlsn.test-token")
    monkeypatch.setattr(
        email_service.settings,
        "MAILERSEND_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )

    status = email_service.email_provider_status()

    assert status["requested_provider"] == "smtp2go"
    assert status["requested_provider_supported"] is True
    assert status["requested_provider_ready"] is False
    assert status["requested_provider_missing"] == ["SMTP2GO_API_KEY", "sender"]
    assert status["selected_provider"] == "mailersend"
    assert status["configured_candidates"] == ["mailersend"]

    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "not-a-provider")

    status = email_service.email_provider_status()

    assert status["requested_provider"] == "not-a-provider"
    assert status["requested_provider_supported"] is False
    assert status["requested_provider_ready"] is False
    assert status["requested_provider_missing"] == []
    assert status["selected_provider"] == "mailersend"


@pytest.mark.asyncio
async def test_postmark_email_provider_sends_password_reset_via_http_api(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "postmark")
    monkeypatch.setattr(email_service.settings, "POSTMARK_SERVER_TOKEN", "pm-test-token")
    monkeypatch.setattr(
        email_service.settings,
        "POSTMARK_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_password_reset_email(
        to_email="reset@example.com",
        company_name="WMS QuickStart",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert result == {"success": True}
    assert captured["url"] == email_service.POSTMARK_API_URL
    assert captured["headers"] == {
        "X-Postmark-Server-Token": "pm-test-token",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    assert captured["json"]["From"] == "WMS QuickStart <no-reply@example.com>"
    assert captured["json"]["To"] == "reset@example.com"
    assert captured["json"]["MessageStream"] == "outbound"
    assert "https://app.example.com/reset-password?token=abc" in captured["json"]["HtmlBody"]


@pytest.mark.asyncio
async def test_sendgrid_email_provider_sends_password_reset_via_http_api(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "sendgrid")
    monkeypatch.setattr(email_service.settings, "SENDGRID_API_KEY", "sg-test-token")
    monkeypatch.setattr(
        email_service.settings,
        "SENDGRID_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_password_reset_email(
        to_email="reset@example.com",
        company_name="WMS QuickStart",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert result == {"success": True}
    assert captured["url"] == email_service.SENDGRID_API_URL
    assert captured["headers"] == {
        "Authorization": "Bearer sg-test-token",
        "Content-Type": "application/json",
    }
    assert captured["json"]["from"] == {
        "name": "WMS QuickStart",
        "email": "no-reply@example.com",
    }
    assert captured["json"]["personalizations"] == [{"to": [{"email": "reset@example.com"}]}]
    assert (
        "https://app.example.com/reset-password?token=abc"
        in captured["json"]["content"][0]["value"]
    )


@pytest.mark.asyncio
async def test_mailgun_email_provider_sends_password_reset_via_http_api(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyAsyncClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, data: dict, files: object, auth: tuple[str, str]):
            captured["url"] = url
            captured["data"] = data
            captured["files"] = files
            captured["auth"] = auth
            return DummyResponse()

    _disable_email_provider_settings(monkeypatch)
    monkeypatch.setattr(email_service.settings, "EMAIL_PROVIDER", "mailgun")
    monkeypatch.setattr(email_service.settings, "MAILGUN_API_KEY", "mg-test-token")
    monkeypatch.setattr(email_service.settings, "MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setattr(
        email_service.settings,
        "MAILGUN_FROM_EMAIL",
        "WMS QuickStart <no-reply@example.com>",
    )
    monkeypatch.setattr(email_service.httpx, "AsyncClient", DummyAsyncClient)

    result = await email_service.send_password_reset_email(
        to_email="reset@example.com",
        company_name="WMS QuickStart",
        reset_url="https://app.example.com/reset-password?token=abc",
    )

    assert result == {"success": True}
    assert captured["url"] == "https://api.mailgun.net/v3/mg.example.com/messages"
    assert captured["data"]["from"] == "WMS QuickStart <no-reply@example.com>"
    assert captured["data"]["to"] == "reset@example.com"
    assert captured["data"]["subject"] == "Reset your password for WMS QuickStart"
    assert "https://app.example.com/reset-password?token=abc" in captured["data"]["html"]
    assert captured["files"] is None
    assert captured["auth"] == ("api", "mg-test-token")
