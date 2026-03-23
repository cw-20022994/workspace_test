"""HTTP client retry tests."""

from pathlib import Path
import tempfile
import unittest

import requests

from stock_report.connectors.http import ConnectorError
from stock_report.connectors.http import HttpClient


class FakeResponse:
    def __init__(
        self,
        *,
        status_code=200,
        text="",
        reason="OK",
        json_payload=None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.reason = reason
        self._json_payload = json_payload if json_payload is not None else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError("status error", response=self)

    def json(self):
        return self._json_payload


class FakeSession:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.headers = {}
        self.calls = 0

    def request(self, method, url, params=None, headers=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class HttpClientTests(unittest.TestCase):
    def test_retries_after_connection_error_then_succeeds(self) -> None:
        slept = []
        client = HttpClient(
            session=FakeSession(
                [
                    requests.ConnectionError("connection reset"),
                    FakeResponse(text="ok"),
                ]
            ),
            cache_enabled=False,
            max_retries=2,
            backoff_seconds=0.1,
            sleep_func=slept.append,
        )

        text = client.get_text("https://example.com/data")

        self.assertEqual(text, "ok")
        self.assertEqual(slept, [0.1])
        self.assertEqual(client.session.calls, 2)

    def test_retries_retryable_http_status_then_succeeds(self) -> None:
        slept = []
        client = HttpClient(
            session=FakeSession(
                [
                    FakeResponse(status_code=503, text="unavailable", reason="Service Unavailable"),
                    FakeResponse(text="healthy"),
                ]
            ),
            cache_enabled=False,
            max_retries=2,
            backoff_seconds=0.2,
            sleep_func=slept.append,
        )

        text = client.get_text("https://example.com/data")

        self.assertEqual(text, "healthy")
        self.assertEqual(slept, [0.2])
        self.assertEqual(client.session.calls, 2)

    def test_raises_connector_error_after_retry_budget_is_exhausted(self) -> None:
        client = HttpClient(
            session=FakeSession(
                [
                    requests.Timeout("timed out"),
                    requests.Timeout("timed out"),
                ]
            ),
            cache_enabled=False,
            max_retries=1,
            backoff_seconds=0.0,
        )

        with self.assertRaises(ConnectorError) as ctx:
            client.get_text("https://example.com/data")

        self.assertIn("after 2 attempt(s)", str(ctx.exception))

    def test_uses_local_cache_for_repeated_get_text_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session = FakeSession([FakeResponse(text="cached body")])
            client = HttpClient(
                session=session,
                cache_dir=tmpdir,
                cache_ttl_seconds=3600,
                now_func=lambda: 100.0,
            )

            first = client.get_text("https://example.com/data", params={"q": "nvda"})
            second = client.get_text("https://example.com/data", params={"q": "nvda"})

            self.assertEqual(first, "cached body")
            self.assertEqual(second, "cached body")
            self.assertEqual(session.calls, 1)
            self.assertTrue(any(Path(tmpdir).iterdir()))

    def test_refetches_after_cache_ttl_expires(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            times = iter([100.0, 105.0, 200.0, 200.0])
            session = FakeSession(
                [
                    FakeResponse(text="old body"),
                    FakeResponse(text="new body"),
                ]
            )
            client = HttpClient(
                session=session,
                cache_dir=tmpdir,
                cache_ttl_seconds=10,
                now_func=lambda: next(times),
            )

            first = client.get_text("https://example.com/data")
            second = client.get_text("https://example.com/data")
            third = client.get_text("https://example.com/data")

            self.assertEqual(first, "old body")
            self.assertEqual(second, "old body")
            self.assertEqual(third, "new body")
            self.assertEqual(session.calls, 2)

    def test_uses_stale_cache_when_network_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            times = iter([100.0, 200.0])
            client = HttpClient(
                session=FakeSession([FakeResponse(text="stale body")]),
                cache_dir=tmpdir,
                cache_ttl_seconds=10,
                now_func=lambda: next(times),
            )
            self.assertEqual(client.get_text("https://example.com/data"), "stale body")

            client.session = FakeSession([requests.ConnectionError("down")])
            client.max_retries = 0
            recovered = client.get_text("https://example.com/data")

            self.assertEqual(recovered, "stale body")
            self.assertEqual(client.session.calls, 1)


if __name__ == "__main__":
    unittest.main()
