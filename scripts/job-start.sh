#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Cron has a minimal PATH; ensure docker is reachable.
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# Prefer prebuilt image from the registry (no local Dockerfile required).
docker compose pull
# Start redis + worker; exit when worker finishes (restart: "no")
docker compose up --abort-on-container-exit --exit-code-from worker
