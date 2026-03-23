#!/bin/zsh
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MARKET KRW_AMOUNT" >&2
  echo "example: $0 KRW-BTC 10000" >&2
  exit 1
fi

MARKET="$1"
KRW_AMOUNT="$2"

cd "$(dirname "$0")/.."

read -s "UPBIT_ACCESS_KEY?UPBIT_ACCESS_KEY: "
echo
read -s "UPBIT_SECRET_KEY?UPBIT_SECRET_KEY: "
echo
read -s "TELEGRAM_BOT_TOKEN?TELEGRAM_BOT_TOKEN (optional, enter to skip): "
echo

if [[ -z "${UPBIT_ACCESS_KEY}" || -z "${UPBIT_SECRET_KEY}" ]]; then
  echo "UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY are required." >&2
  exit 1
fi

export UPBIT_ACCESS_KEY
export UPBIT_SECRET_KEY
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-disabled-for-manual-order}"

CONFIRMATION="BUY:${MARKET}:${KRW_AMOUNT}"

PYTHONPATH=src python3 -m coin_partner.cli --config config.toml \
  --manual-buy-market "${MARKET}" \
  --manual-buy-krw "${KRW_AMOUNT}" \
  --live-order-confirm "${CONFIRMATION}"
