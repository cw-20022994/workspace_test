from __future__ import annotations

from trade_studio.core.models import ExchangeName, ProfileConfig
from trade_studio.exchanges.base import AdapterCapabilities, CredentialTestResult, ExchangeAdapter


class KrakenAdapter(ExchangeAdapter):
    name = ExchangeName.KRAKEN
    display_name = "Kraken"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_api_keys=True,
            supports_oauth=True,
            supports_spot=True,
            supports_derivatives=False,
            supports_paper_mode=True,
        )

    def validate_profile(self, profile: ProfileConfig) -> list[str]:
        errors = profile.validate()
        if profile.exchange != self.name:
            errors.append("Profile exchange does not match the Kraken adapter.")
        if profile.base_currency not in {"USD", "EUR", "USDT"}:
            errors.append("Kraken scaffold currently expects USD, EUR, or USDT quote currency.")
        return errors

    def test_credentials(self, api_key: str, api_secret: str) -> CredentialTestResult:
        if not api_key.strip() or not api_secret.strip():
            return CredentialTestResult(False, "API key and secret are required.")
        return CredentialTestResult(
            False,
            "Credential check is not wired yet. The adapter scaffold is ready for Kraken REST or OAuth integration.",
        )

