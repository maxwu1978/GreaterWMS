#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_DIR="${HOME}/Library/Application Support/WMS Agent"
VENV_DIR="${INSTALL_DIR}/venv"
LAUNCHER="${HOME}/Desktop/WMS Agent.command"
APP_DIR="${HOME}/Desktop/WMS Agent.app"
APP_CONTENTS="${APP_DIR}/Contents"
APP_MACOS="${APP_CONTENTS}/MacOS"
APP_RESOURCES="${APP_CONTENTS}/Resources"
LAUNCH_AGENT_DIR="${HOME}/Library/LaunchAgents"
LAUNCH_AGENT_PLIST="${LAUNCH_AGENT_DIR}/com.maxsmart.wms-agent.plist"

mkdir -p "${INSTALL_DIR}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Python 3.12 or newer is required. Install it from https://www.python.org/downloads/macos/ and rerun this installer."
  exit 1
fi

"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required.")
PY

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install "${ROOT_DIR}"

if [ ! -f "${INSTALL_DIR}/.env" ]; then
  cp "${ROOT_DIR}/.env.example" "${INSTALL_DIR}/.env"
fi

mkdir -p "${APP_MACOS}" "${APP_RESOURCES}" "${LAUNCH_AGENT_DIR}"
cp "${ROOT_DIR}/install/macos/MaxSmart.icns" "${APP_RESOURCES}/MaxSmart.icns"

cat > "${LAUNCH_AGENT_PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.maxsmart.wms-agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/wms-local-agent</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${INSTALL_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>WMS_LOCAL_AGENT_HOST</key>
    <string>127.0.0.1</string>
    <key>WMS_LOCAL_AGENT_PORT</key>
    <string>8787</string>
  </dict>
  <key>StandardOutPath</key>
  <string>${INSTALL_DIR}/agent.log</string>
  <key>StandardErrorPath</key>
  <string>${INSTALL_DIR}/agent.log</string>
  <key>RunAtLoad</key>
  <false/>
  <key>KeepAlive</key>
  <false/>
</dict>
</plist>
EOF

cat > "${APP_CONTENTS}/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>WMS Agent</string>
  <key>CFBundleIconFile</key>
  <string>MaxSmart</string>
  <key>CFBundleIdentifier</key>
  <string>com.maxsmart.wms-agent</string>
  <key>CFBundleName</key>
  <string>WMS Agent</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
</dict>
</plist>
EOF

cat > "${APP_MACOS}/WMS Agent" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export WMS_LOCAL_AGENT_HOST="\${WMS_LOCAL_AGENT_HOST:-127.0.0.1}"
export WMS_LOCAL_AGENT_PORT="\${WMS_LOCAL_AGENT_PORT:-8787}"
cd "${INSTALL_DIR}"
"${VENV_DIR}/bin/wms-agent-client" > "${INSTALL_DIR}/client.log" 2>&1
EOF

chmod +x "${APP_MACOS}/WMS Agent"
cp "${APP_MACOS}/WMS Agent" "${LAUNCHER}"
chmod +x "${LAUNCHER}"
launchctl bootout "gui/$(id -u)" "${LAUNCH_AGENT_PLIST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${LAUNCH_AGENT_PLIST}" >/dev/null 2>&1 || true

echo "WMS Agent installed."
echo "Config: ${INSTALL_DIR}/.env"
echo "Launcher: ${APP_DIR}"
echo "Fallback launcher: ${LAUNCHER}"
echo "LaunchAgent: ${LAUNCH_AGENT_PLIST}"
