from __future__ import annotations


def main() -> int:
    from trade_studio.desktop.app import run_desktop_app

    return run_desktop_app()


if __name__ == "__main__":
    raise SystemExit(main())

