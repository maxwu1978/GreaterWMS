#!/usr/bin/env bash
set -euo pipefail

REMOTE_URL="${GREATERWMS_DEPLOY_REPO:-https://github.com/maxwu1978/GreaterWMS.git}"
TARGET_BRANCH="${GREATERWMS_RENDER_BRANCH:-codex/sn-receiving}"

python3 scripts/verify_greaterwms_target.py \
  --remote-url "$REMOTE_URL" \
  --target-branch "$TARGET_BRANCH"

echo "Pushing GreaterWMS HEAD to $REMOTE_URL:$TARGET_BRANCH"
git push "$REMOTE_URL" "HEAD:$TARGET_BRANCH"

cat <<'EOF'
Push complete. Render should deploy the GreaterWMS service asynchronously:
  greaterwms-v2-test3-sn
  https://greaterwms-v2-test3-sn.onrender.com

Verify after Render finishes:
  curl -fsS https://greaterwms-v2-test3-sn.onrender.com/
EOF
