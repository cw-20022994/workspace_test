from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from stock_auto.adapters.auth.kis_auth import KISAuthSession, KISCredentials


class _FakeResponse:
    def __init__(self, payload: dict, *, headers: dict | None = None, status: int = 200) -> None:
        self.payload = payload
        self.headers = headers or {}
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class KISAuthSessionTest(unittest.TestCase):
    def test_request_issues_token_and_prefixes_demo_tr_id(self) -> None:
        credentials = KISCredentials(
            app_key="app-key",
            app_secret="app-secret",
            cano="12345678",
            account_product_code="01",
            env="demo",
        )
        session = KISAuthSession(credentials)
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            if request.full_url.endswith("/oauth2/tokenP"):
                return _FakeResponse(
                    {
                        "access_token": "token-123",
                        "access_token_token_expired": "2099-01-01 00:00:00",
                    }
                )
            return _FakeResponse({"rt_cd": "0", "output": []}, headers={"tr_cont": ""})

        with patch("stock_auto.adapters.auth.kis_auth.urlopen", side_effect=fake_urlopen):
            response = session.request("GET", "/uapi/test", tr_id="TTTS3018R")

        self.assertTrue(response.is_ok())
        self.assertEqual(len(requests), 2)
        header_map = {key.lower(): value for key, value in requests[1].header_items()}
        self.assertEqual(header_map["authorization"], "Bearer token-123")
        self.assertEqual(header_map["tr_id"], "VTTS3018R")


if __name__ == "__main__":
    unittest.main()
