"""Configuration helpers for the local WMS agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_WMS_API_BASE_URL = "https://api.maxsmartwms.online/api/v1"

BACKEND_MODEL_PROVIDERS: dict[str, dict[str, str]] = {
    "minimax": {
        "label": "MiniMax",
        "api_key": "MINIMAX_API_KEY",
        "base_url": "MINIMAX_BASE_URL",
        "model": "MINIMAX_MODEL",
        "default_base_url": "https://api.minimaxi.com/v1",
        "default_model": "MiniMax-M1",
    },
    "qwen": {
        "label": "Qwen",
        "api_key": "QWEN_API_KEY",
        "base_url": "QWEN_BASE_URL",
        "model": "QWEN_MODEL",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-max",
    },
    "kimi": {
        "label": "Kimi",
        "api_key": "KIMI_API_KEY",
        "base_url": "KIMI_BASE_URL",
        "model": "KIMI_MODEL",
        "default_base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
    },
    "deepseek": {
        "label": "DeepSeek",
        "api_key": "DEEPSEEK_API_KEY",
        "base_url": "DEEPSEEK_BASE_URL",
        "model": "DEEPSEEK_MODEL",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
    },
}

DEFAULT_BACKEND_PROVIDER_ORDER = ("deepseek", "qwen", "kimi", "minimax")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def package_root() -> Path:
    """Return the source or bundled application root."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def user_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "WMS Agent"


def user_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "WMS Agent"


def env_file_candidates() -> list[Path]:
    return [
        Path.cwd() / ".env",
        package_root() / ".env",
        user_config_dir() / ".env",
        repo_root() / "backend" / ".env",
    ]


def default_skill_root() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "bundled_skills",
        package_root() / "skills",
        user_config_dir() / "skills",
        repo_root() / ".codex" / "skills",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def merged_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in env_file_candidates():
        values.update(read_env_file(path))
    return values


def normalize_wms_api_url(value: str | None) -> str:
    raw = (value or DEFAULT_WMS_API_BASE_URL).strip().rstrip("/")
    if raw.endswith("/api/v1"):
        return raw
    if raw.endswith("/api"):
        return f"{raw}/v1"
    return f"{raw}/api/v1"


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def backend_model_roster(env_values: dict[str, str] | None = None) -> list[dict[str, Any]]:
    values = env_values if env_values is not None else merged_env_values()
    roster: list[dict[str, Any]] = []
    for key, spec in BACKEND_MODEL_PROVIDERS.items():
        api_key = values.get(spec["api_key"], "")
        base_url = values.get(spec["base_url"]) or spec["default_base_url"]
        model = values.get(spec["model"]) or spec["default_model"]
        roster.append(
            {
                "key": key,
                "label": spec["label"],
                "base_url": base_url,
                "model": model,
                "configured": bool(api_key and model),
            }
        )
    return roster


def backend_model_configs(env_values: dict[str, str] | None = None) -> list[dict[str, str]]:
    values = env_values if env_values is not None else merged_env_values()
    configs: list[dict[str, str]] = []
    for provider in DEFAULT_BACKEND_PROVIDER_ORDER:
        config = _backend_model_config(provider, values)
        if config:
            configs.append(config)
    return configs


def _backend_model_config(provider: str, env_values: dict[str, str]) -> dict[str, str] | None:
    spec = BACKEND_MODEL_PROVIDERS.get(provider)
    if not spec:
        return None
    api_key = env_values.get(spec["api_key"], "")
    model = env_values.get(spec["model"]) or spec["default_model"]
    if not (api_key and model):
        return None
    return {
        "provider": provider,
        "base_url": env_values.get(spec["base_url"]) or spec["default_base_url"],
        "model": model,
        "api_key": api_key,
    }


class LocalAgentSettings(BaseSettings):
    """Runtime settings for the local agent app."""

    model_config = SettingsConfigDict(
        env_prefix="WMS_LOCAL_AGENT_",
        env_file=".env",
        extra="ignore",
    )

    api_base_url: str = "https://api.maxsmartwms.online"
    model_provider: str = "openai-compatible"
    model_base_url: str = ""
    model_name: str = ""
    model_api_key: str = ""
    host: str = "127.0.0.1"
    port: int = 8787
    skill_root: Path = default_skill_root()
    audit_log_path: Path = user_data_dir() / "audit.jsonl"

    @property
    def api_v1_url(self) -> str:
        return normalize_wms_api_url(self.api_base_url)

    @property
    def effective_model(self) -> dict[str, str]:
        if self.model_api_key and self.model_name:
            return {
                "provider": self.model_provider,
                "base_url": self.model_base_url,
                "model": self.model_name,
                "api_key": self.model_api_key,
                "source": "local-agent env",
            }
        backend_env = merged_env_values()
        requested = self.model_provider.strip().lower().replace("_", "-")
        normalized_requested = requested.replace("-", "_")
        if normalized_requested in BACKEND_MODEL_PROVIDERS:
            config = _backend_model_config(normalized_requested, backend_env)
            if config:
                return {**config, "source": "agent env"}
        for provider in DEFAULT_BACKEND_PROVIDER_ORDER:
            config = _backend_model_config(provider, backend_env)
            if config:
                return {**config, "source": "agent env"}
        return {
            "provider": self.model_provider,
            "base_url": self.model_base_url,
            "model": self.model_name,
            "api_key": self.model_api_key,
            "source": "not configured",
        }

    @property
    def effective_model_provider(self) -> str:
        return self.effective_model["provider"]

    @property
    def effective_model_base_url(self) -> str:
        return self.effective_model["base_url"]

    @property
    def effective_model_name(self) -> str:
        return self.effective_model["model"]

    @property
    def effective_model_api_key(self) -> str:
        return self.effective_model["api_key"]

    @property
    def effective_model_source(self) -> str:
        return self.effective_model["source"]

    @property
    def backend_model_roster(self) -> list[dict[str, Any]]:
        return backend_model_roster()

    @property
    def backend_model_configs(self) -> list[dict[str, str]]:
        if self.model_api_key and self.model_name:
            return [
                {
                    "provider": self.model_provider,
                    "base_url": self.model_base_url,
                    "model": self.model_name,
                    "api_key": self.model_api_key,
                }
            ]
        return backend_model_configs()
