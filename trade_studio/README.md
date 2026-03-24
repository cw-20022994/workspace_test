# Trade Studio

Trade Studio is a new desktop trading product scaffold for exchange-supported automation.

This project is intentionally separate from `coin_partner`.
It starts from an exchange-agnostic architecture so the product can support a sellable desktop app without carrying Upbit-specific assumptions.

## Current Scope

- PySide6 desktop shell
- Exchange-neutral profile model
- Kraken adapter scaffold
- JSON profile storage
- Basic validation and tests

## Project Layout

```text
trade_studio/
  src/trade_studio/
    bootstrap.py
    paths.py
    core/
    desktop/
    exchanges/
    storage/
  tests/
```

## Quick Start

```bash
cd /Users/jeongnis-si/workspace_test/trade_studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
trade-studio
```

## Initial Product Direction

- Desktop-first app
- Strategy templates with parameter customization
- Strict risk controls before live trading
- Exchange adapters isolated behind a common interface
- User secrets stored outside plain-text config files

## Next Build Steps

1. Implement Kraken authentication and market data adapter.
2. Replace placeholder desktop tabs with editable forms.
3. Add backtest and paper-trading services.
4. Add encrypted secret storage through OS keychain integration.

