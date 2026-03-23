from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TelegramCredentials:
    bot_token: str
    chat_id: Optional[str] = None


class TelegramBotClient:
    def __init__(
        self,
        credentials: TelegramCredentials,
        *,
        base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def get_me(self) -> Dict[str, object]:
        result = self._request_json("GET", "getMe")
        assert isinstance(result, dict)
        return result

    def get_updates(
        self,
        *,
        limit: int = 10,
        timeout: int = 0,
        allowed_updates: Optional[List[str]] = None,
    ) -> List[Dict[str, object]]:
        query = {
            "limit": str(limit),
            "timeout": str(timeout),
        }
        if allowed_updates is not None:
            query["allowed_updates"] = json.dumps(allowed_updates)
        result = self._request_json("GET", "getUpdates", query=query)
        assert isinstance(result, list)
        return result

    def send_message(
        self,
        *,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
    ) -> Dict[str, object]:
        target_chat_id = chat_id or self.credentials.chat_id
        if not target_chat_id:
            raise RuntimeError(
                "Telegram chat_id is required. Set TELEGRAM_CHAT_ID or pass --chat-id."
            )

        payload: Dict[str, object] = {
            "chat_id": target_chat_id,
            "text": text,
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        result = self._request_json("POST", "sendMessage", payload=payload)
        assert isinstance(result, dict)
        return result

    def _request_json(
        self,
        method: str,
        api_method: str,
        *,
        query: Optional[Dict[str, str]] = None,
        payload: Optional[Dict[str, object]] = None,
    ):
        url = f"{self.base_url}/bot{self.credentials.bot_token}/{api_method}"
        if query:
            url = f"{url}?{urlencode(query)}"

        data = None
        headers = {
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=method)

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read().decode("utf-8")
                    parsed = json.loads(body) if body else {}
                    if not isinstance(parsed, dict):
                        raise RuntimeError("Telegram response is not a JSON object")
                    if not parsed.get("ok", False):
                        description = parsed.get("description", "unknown error")
                        error_code = parsed.get("error_code", "unknown")
                        raise RuntimeError(
                            f"Telegram request failed with HTTP {response.status}: {error_code} {description}"
                        )
                    return parsed.get("result")
            except HTTPError as exc:
                should_retry = exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries
                last_error = exc
                message = exc.read().decode("utf-8", errors="ignore")
                if should_retry:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                raise RuntimeError(
                    f"Telegram request failed with HTTP {exc.code}: {message}"
                ) from exc
            except URLError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                raise RuntimeError(f"Telegram request failed: {exc.reason}") from exc

        raise RuntimeError(f"Telegram request failed after retries: {last_error}")  # pragma: no cover
