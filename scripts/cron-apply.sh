#!/usr/bin/env bash
# Install or remove crontab entries from .env (CRON_*).
# CRON_START / CRON_STOP use standard 5-field cron: min hour dom month dow
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ROOT}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing .env — copy .env.example first" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

MARKER="# jaypeg-cron"
START_SH="${ROOT}/scripts/job-start.sh"
STOP_SH="${ROOT}/scripts/job-stop.sh"
# Host-owned logs (not result/, which docker often writes as root).
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR"

validate_cron5() {
  local expr="$1"
  local name="$2"
  # Disable glob so '*' in cron fields is not expanded to filenames.
  set -f
  # shellcheck disable=SC2086
  set -- $expr
  set +f
  if [[ $# -ne 5 ]]; then
    echo "${name} must be 5-field cron (min hour dom month dow), got: ${expr}" >&2
    exit 1
  fi
}

strip_old() {
  crontab -l 2>/dev/null | grep -vF "$MARKER" || true
}

_cron_on="$(echo "${CRON_ENABLE:-false}" | tr '[:upper:]' '[:lower:]')"
if [[ "$_cron_on" != "true" && "$_cron_on" != "1" && "$_cron_on" != "yes" && "$_cron_on" != "on" ]]; then
  strip_old | crontab -
  echo "CRON_ENABLE=false — removed jaypeg crontab entries (if any)"
  exit 0
fi

CRON_START="${CRON_START:-0 2 * * *}"
CRON_STOP="${CRON_STOP:-0 6 * * *}"
validate_cron5 "$CRON_START" "CRON_START"
validate_cron5 "$CRON_STOP" "CRON_STOP"

# Times follow the host system clock / crontab timezone (no CRON_TZ override).
tmp="$(mktemp)"
{
  strip_old
  echo "${CRON_START} cd \"${ROOT}\" && /bin/bash \"${START_SH}\" >> \"${LOG_DIR}/cron-start.log\" 2>&1 ${MARKER}"
  echo "${CRON_STOP} cd \"${ROOT}\" && /bin/bash \"${STOP_SH}\" >> \"${LOG_DIR}/cron-stop.log\" 2>&1 ${MARKER}"
} >"$tmp"

crontab "$tmp"
rm -f "$tmp"
echo "installed crontab:"
crontab -l | grep -F "$MARKER" || true
