from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trade_studio.storage.settings import ProfileRepository


class ProfileRepositoryTests(unittest.TestCase):
    def test_repository_bootstraps_default_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles.json"
            repository = ProfileRepository(path)

            profiles = repository.load_profiles()

            self.assertEqual(len(profiles), 1)
            self.assertTrue(path.exists())

    def test_repository_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles.json"
            repository = ProfileRepository(path)

            profiles = repository.load_profiles()
            profiles[0].name = "Custom Kraken Profile"
            repository.save_profiles(profiles)

            restored = repository.load_profiles()
            self.assertEqual(restored[0].name, "Custom Kraken Profile")


if __name__ == "__main__":
    unittest.main()
