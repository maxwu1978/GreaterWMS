"""In-memory local session store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass
class LocalSession:
    id: str
    wms_api_base_url: str
    access_token: str
    role: str
    tenant_id: str | None
    job_title: str | None
    permissions: list[str]
    agent_settings: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def api_v1_url(self) -> str:
        return self.wms_api_base_url

    @property
    def tool_catalog(self) -> list:
        return list(self.agent_settings.get("tool_catalog") or [])

    @property
    def tool_count(self) -> int:
        return len(self.tool_catalog)


@dataclass
class UserSession:
    access_token: str
    api_v1_url: str
    role: str
    tenant_id: str | None
    job_title: str | None
    permissions: list[str]
    tool_count: int
    tool_catalog: list

    @property
    def id(self) -> str:
        return "default"

    @property
    def wms_api_base_url(self) -> str:
        return self.api_v1_url

    @property
    def agent_settings(self) -> dict:
        return {"tool_catalog": self.tool_catalog}


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, LocalSession] = {}
        self._default_session: LocalSession | UserSession | None = None

    def create(
        self,
        *,
        wms_api_base_url: str,
        access_token: str,
        role: str,
        tenant_id: str | None,
        job_title: str | None,
        permissions: list[str],
        agent_settings: dict,
    ) -> LocalSession:
        session = LocalSession(
            id=uuid4().hex,
            wms_api_base_url=wms_api_base_url,
            access_token=access_token,
            role=role,
            tenant_id=tenant_id,
            job_title=job_title,
            permissions=permissions,
            agent_settings=agent_settings,
        )
        self._sessions[session.id] = session
        self._default_session = session
        return session

    def set(self, session: LocalSession | UserSession) -> None:
        self._default_session = session
        self._sessions[session.id] = session  # type: ignore[assignment]

    def get(self, session_id: str | None = None) -> LocalSession | UserSession | None:
        if session_id is None:
            return self._default_session
        return self._sessions.get(session_id)

    def require(self) -> LocalSession | UserSession:
        if not self._default_session:
            raise RuntimeError("Sign in to WMS before using the local agent")
        return self._default_session

    def clear(self) -> None:
        self._default_session = None

    def delete(self, session_id: str) -> None:
        if self._default_session and self._default_session.id == session_id:
            self._default_session = None
        self._sessions.pop(session_id, None)
