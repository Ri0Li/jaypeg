#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Start redis + worker; exit when worker finishes (restart: "no")
docker compose up --build --abort-on-container-exit --exit-code-from worker
