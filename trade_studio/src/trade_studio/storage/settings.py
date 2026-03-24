from __future__ import annotations

import json
from pathlib import Path

from trade_studio.core.models import ProfileConfig, build_default_profile
from trade_studio.paths import profiles_file


class ProfileRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or profiles_file()

    def load_profiles(self) -> list[ProfileConfig]:
        if not self.path.exists():
            profiles = [build_default_profile()]
            self.save_profiles(profiles)
            return profiles

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("profiles file must contain a JSON list")
        return [ProfileConfig.from_dict(item) for item in payload]

    def save_profiles(self, profiles: list[ProfileConfig]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [profile.to_dict() for profile in profiles]
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

