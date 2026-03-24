from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIRECTORY_NAME = "TradeStudio"


def application_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIRECTORY_NAME
    if sys.platform.startswith("win"):
        app_data = os.getenv("APPDATA")
        base_dir = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return base_dir / APP_DIRECTORY_NAME
    return Path.home() / ".local" / "share" / APP_DIRECTORY_NAME.lower()


def profiles_file() -> Path:
    return application_data_dir() / "profiles.json"

