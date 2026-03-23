#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="${ROOT_DIR}/data/live_auto.pid"
LOG_FILE="${ROOT_DIR}/data/live_auto.log"
ENV_FILE="${HOME}/.coin_partner_env"
CONFIG_FILE="${ROOT_DIR}/config.live-auto.toml"

usage() {
  echo "usage: $0 {start|stop|status|logs}" >&2
  exit 1
}

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
  fi

  if [[ -z "${UPBIT_ACCESS_KEY:-}" || -z "${UPBIT_SECRET_KEY:-}" || -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY, and TELEGRAM_BOT_TOKEN must be loaded." >&2
    echo "Run: source ~/.coin_partner_env" >&2
    exit 1
  fi
}

read_pid() {
  if [[ -f "${PID_FILE}" ]]; then
    tr -d '[:space:]' < "${PID_FILE}"
  fi
}

is_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

start_service() {
  load_env
  mkdir -p "${ROOT_DIR}/data"

  local existing_pid
  existing_pid="$(read_pid)"
  if is_running "${existing_pid}"; then
    echo "live-auto bot is already running. pid=${existing_pid}"
    exit 0
  fi

  cd "${ROOT_DIR}"
  {
    echo ""
    echo "===== $(date '+%Y-%m-%d %H:%M:%S %z') live-auto start ====="
  } >> "${LOG_FILE}"

  nohup env \
    UPBIT_ACCESS_KEY="${UPBIT_ACCESS_KEY}" \
    UPBIT_SECRET_KEY="${UPBIT_SECRET_KEY}" \
    TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}" \
    PYTHONPATH=src \
    python3 -m coin_partner.cli --config "${CONFIG_FILE}" >> "${LOG_FILE}" 2>&1 &

  local pid=$!
  echo "${pid}" > "${PID_FILE}"
  sleep 1

  if is_running "${pid}"; then
    echo "live-auto bot started. pid=${pid}"
    echo "log=${LOG_FILE}"
  else
    echo "live-auto bot failed to stay running. check log=${LOG_FILE}" >&2
    exit 1
  fi
}

stop_service() {
  local pid
  pid="$(read_pid)"
  if ! is_running "${pid}"; then
    echo "live-auto bot is not running."
    : > "${PID_FILE}"
    exit 0
  fi

  kill "${pid}"
  sleep 1
  if is_running "${pid}"; then
    echo "process did not stop yet. pid=${pid}" >&2
    exit 1
  fi

  : > "${PID_FILE}"
  echo "live-auto bot stopped. pid=${pid}"
}

status_service() {
  local pid
  pid="$(read_pid)"
  if is_running "${pid}"; then
    echo "live-auto bot is running. pid=${pid}"
    ps -p "${pid}" -o pid=,etime=,command=
    echo "log=${LOG_FILE}"
  else
    echo "live-auto bot is not running."
    if [[ -s "${PID_FILE}" ]]; then
      echo "stale pid file value=$(read_pid)"
    fi
  fi
}

logs_service() {
  mkdir -p "${ROOT_DIR}/data"
  touch "${LOG_FILE}"
  tail -n 50 -f "${LOG_FILE}"
}

if [[ $# -ne 1 ]]; then
  usage
fi

case "$1" in
  start)
    start_service
    ;;
  stop)
    stop_service
    ;;
  status)
    status_service
    ;;
  logs)
    logs_service
    ;;
  *)
    usage
    ;;
esac
