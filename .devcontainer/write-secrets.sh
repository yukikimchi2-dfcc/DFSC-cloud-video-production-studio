#!/usr/bin/env bash
# Materialise secrets passed as environment variables into git-ignored files.
set -euo pipefail
mkdir -p secrets
if [ -n "${STUDIO_DRIVE_CREDENTIALS_JSON:-}" ]; then
  umask 077
  printf '%s' "$STUDIO_DRIVE_CREDENTIALS_JSON" > secrets/drive.service-account.json
  echo "export STUDIO_DRIVE_CREDENTIALS=$PWD/secrets/drive.service-account.json" > secrets/env.sh
  echo "Drive credentials written to secrets/ (git-ignored)."
fi
