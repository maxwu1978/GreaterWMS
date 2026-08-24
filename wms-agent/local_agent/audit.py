"""Small local audit log for local-agent activity."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SENSITIVE_KEY_PARTS = ("password", "token", "api_key", "apikey", "secret", "authorization")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if any(part in key.lower() for part in SENSITIVE_KEY_PARTS)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "payload": redact(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def tail(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        safe_limit = max(1, min(limit, 200))
        lines = self.path.read_text(encoding="utf-8").splitlines()[-safe_limit:]
        entries: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                entries.append(value)
        return entries
