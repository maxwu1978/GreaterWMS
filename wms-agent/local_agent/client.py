"""Native desktop shell for WMS Agent."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .config import LocalAgentSettings, user_data_dir


def _health_url(settings: LocalAgentSettings) -> str:
    return f"http://{settings.host}:{settings.port}/api/health"


def _app_url(settings: LocalAgentSettings) -> str:
    return f"http://{settings.host}:{settings.port}"


def _is_healthy(settings: LocalAgentSettings) -> bool:
    try:
        with urlopen(_health_url(settings), timeout=1) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _start_launch_agent() -> bool:
    if sys.platform != "darwin":
        return False
    plist = Path.home() / "Library" / "LaunchAgents" / "com.maxsmart.wms-agent.plist"
    if not plist.exists():
        return False
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["launchctl", "kickstart", "-k", f"{domain}/com.maxsmart.wms-agent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return True


def _spawn_service(settings: LocalAgentSettings) -> subprocess.Popen:
    log_path = user_data_dir() / "agent.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "WMS_LOCAL_AGENT_HOST": settings.host,
        "WMS_LOCAL_AGENT_PORT": str(settings.port),
    }
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log = log_path.open("ab")
    return subprocess.Popen(
        [sys.executable, "-m", "local_agent.server"],
        cwd=user_data_dir(),
        env=env,
        stdout=log,
        stderr=log,
        creationflags=creationflags,
    )


def ensure_service(settings: LocalAgentSettings) -> subprocess.Popen | None:
    if _is_healthy(settings):
        return None
    started_by_client: subprocess.Popen | None = None
    if not _start_launch_agent():
        started_by_client = _spawn_service(settings)
    for _ in range(30):
        if _is_healthy(settings):
            return started_by_client
        time.sleep(1)
    if started_by_client:
        started_by_client.terminate()
    raise RuntimeError(
        "WMS Agent service did not become ready. Check the local agent log."
    )


def main() -> None:
    settings = LocalAgentSettings()
    service_process = ensure_service(settings)
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "The WMS Agent desktop client is missing pywebview. Re-run the installer."
        ) from exc

    window = webview.create_window(
        "MaxSmart WMS Agent",
        _app_url(settings),
        width=1280,
        height=860,
        min_size=(980, 680),
        text_select=True,
    )
    webview.start(private_mode=False)
    if window:
        pass
    if service_process:
        service_process.terminate()


if __name__ == "__main__":
    main()
