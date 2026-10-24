#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Stop worker only; leave redis up so queue/resume state stays warm.
docker compose stop worker >/dev/null 2>&1 || true
