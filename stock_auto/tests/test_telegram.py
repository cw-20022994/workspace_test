from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from stock_auto.adapters.notify.telegram import TelegramBotClient, TelegramCredentials


class _FakeHTTPResponse:
    def __init__(self, payload, *, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class TelegramBotClientTest(unittest.TestCase):
    def test_get_updates_uses_expected_query(self) -> None:
        credentials = TelegramCredentials(bot_token="telegram-token")
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["timeout"] = timeout
            return _FakeHTTPResponse(
                {
                    "ok": True,
                    "result": [{"update_id": 1, "message": {"chat": {"id": 12345}}}],
                }
            )

        client = TelegramBotClient(credentials)
        with patch("stock_auto.adapters.notify.telegram.urlopen", side_effect=fake_urlopen):
            result = client.get_updates(limit=5, timeout=2, allowed_updates=["message"])

        self.assertEqual(result[0]["update_id"], 1)
        self.assertEqual(captured["method"], "GET")
        self.assertIn("/bottelegram-token/getUpdates", captured["url"])
        self.assertIn("limit=5", captured["url"])
        self.assertIn("timeout=2", captured["url"])
        self.assertIn("allowed_updates=%5B%22message%22%5D", captured["url"])
        self.assertEqual(captured["timeout"], 30.0)

    def test_send_message_posts_expected_payload(self) -> None:
        credentials = TelegramCredentials(bot_token="telegram-token", chat_id="12345")
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeHTTPResponse(
                {
                    "ok": True,
                    "result": {"message_id": 99, "chat": {"id": 12345}, "text": "ping"},
                }
            )

        client = TelegramBotClient(credentials)
        with patch("stock_auto.adapters.notify.telegram.urlopen", side_effect=fake_urlopen):
            result = client.send_message(text="ping", parse_mode="HTML")

        self.assertEqual(result["message_id"], 99)
        self.assertEqual(captured["method"], "POST")
        self.assertIn("/bottelegram-token/sendMessage", captured["url"])
        self.assertEqual(
            captured["payload"],
            {
                "chat_id": "12345",
                "text": "ping",
                "disable_notification": False,
                "parse_mode": "HTML",
            },
        )


if __name__ == "__main__":
    unittest.main()
