#!/usr/bin/env bash
# SessionStart hook for Claude Code cloud sessions: makes a fresh container studio-ready.
# Idempotent and quiet when everything is already installed.
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0   # local machines manage their own environment
fi

if ! fc-list | grep -q "Noto Sans CJK TC"; then
  (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fonts-noto-cjk) >/dev/null 2>&1 \
    || echo "warning: could not install fonts-noto-cjk" >&2
fi
if ! python3 -c "import studio, cv2, faster_whisper, googleapiclient" 2>/dev/null; then
  python3 -m pip install -q -r requirements.txt >/dev/null 2>&1 && python3 -m pip install -q -e . >/dev/null 2>&1 \
    || echo "warning: pip install failed" >&2
fi
[ -f secrets/env.sh ] && echo "source $PWD/secrets/env.sh" >> "${CLAUDE_ENV_FILE:-/dev/null}"
exit 0
