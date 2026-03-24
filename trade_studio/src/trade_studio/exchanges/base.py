from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from trade_studio.core.models import ExchangeName, ProfileConfig


@dataclass(frozen=True)
class AdapterCapabilities:
    supports_api_keys: bool
    supports_oauth: bool
    supports_spot: bool
    supports_derivatives: bool
    supports_paper_mode: bool


@dataclass(frozen=True)
class CredentialTestResult:
    ok: bool
    message: str


class ExchangeAdapter(ABC):
    name: ExchangeName
    display_name: str

    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        raise NotImplementedError

    @abstractmethod
    def validate_profile(self, profile: ProfileConfig) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def test_credentials(self, api_key: str, api_secret: str) -> CredentialTestResult:
        raise NotImplementedError

