from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URLS = {
    "real": "https://openapi.koreainvestment.com:9443",
    "demo": "https://openapivts.koreainvestment.com:29443",
}


@dataclass(frozen=True)
class KISCredentials:
    app_key: str
    app_secret: str
    cano: str
    account_product_code: str
    env: str = "demo"
    hts_id: str = ""
    customer_type: str = "P"
    base_url: Optional[str] = None

    @property
    def resolved_base_url(self) -> str:
        return self.base_url or DEFAULT_BASE_URLS[self.env]


@dataclass(frozen=True)
class KISResponse:
    status_code: int
    headers: Dict[str, str]
    body: Dict[str, Any]

    def is_ok(self) -> bool:
        return str(self.body.get("rt_cd", "")) == "0"

    def error_code(self) -> str:
        return str(self.body.get("msg_cd", ""))

    def error_message(self) -> str:
        return str(self.body.get("msg1", ""))


def resolve_kis_tr_id(tr_id: str, env: str) -> str:
    if env == "demo" and tr_id and tr_id[0] in ("T", "J", "C"):
        return "V" + tr_id[1:]
    return tr_id


class KISAuthSession:
    def __init__(
        self,
        credentials: KISCredentials,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self._access_token: Optional[str] = None
        self._access_token_expires_at: Optional[datetime] = None

    def issue_access_token(self, force: bool = False) -> str:
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._access_token
            and self._access_token_expires_at
            and now < self._access_token_expires_at - timedelta(minutes=5)
        ):
            return self._access_token

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret,
        }
        response = self._raw_request(
            "POST",
            "/oauth2/tokenP",
            body=payload,
            auth_required=False,
        )
        token = str(response.body["access_token"])
        expires_raw = response.body.get("access_token_token_expired")
        if expires_raw:
            expires_at = datetime.strptime(str(expires_raw), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        else:
            expires_at = now + timedelta(hours=12)
        self._access_token = token
        self._access_token_expires_at = expires_at
        return token

    def issue_websocket_approval_key(self) -> str:
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.credentials.app_key,
            "secretkey": self.credentials.app_secret,
        }
        response = self._raw_request(
            "POST",
            "/oauth2/Approval",
            body=payload,
            auth_required=False,
        )
        return str(response.body["approval_key"])

    def issue_hashkey(self, payload: Mapping[str, Any]) -> str:
        response = self._raw_request(
            "POST",
            "/uapi/hashkey",
            body=dict(payload),
            auth_required=True,
            include_transaction_headers=False,
        )
        return str(response.body["HASH"])

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        tr_id: str = "",
        params: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        tr_cont: str = "",
        use_hash: bool = False,
    ) -> KISResponse:
        return self._raw_request(
            method,
            endpoint,
            tr_id=tr_id,
            params=params,
            body=body,
            tr_cont=tr_cont,
            auth_required=True,
            include_transaction_headers=bool(tr_id),
            use_hash=use_hash,
        )

    def _raw_request(
        self,
        method: str,
        endpoint: str,
        *,
        tr_id: str = "",
        params: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        tr_cont: str = "",
        auth_required: bool = True,
        include_transaction_headers: bool = True,
        use_hash: bool = False,
    ) -> KISResponse:
        base_url = self.credentials.resolved_base_url
        url = f"{base_url}{endpoint}"
        if params:
            encoded = urlencode({key: str(value) for key, value in params.items()})
            url = f"{url}?{encoded}"

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret,
        }
        if auth_required:
            headers["authorization"] = f"Bearer {self.issue_access_token()}"
        if include_transaction_headers and tr_id:
            headers["tr_id"] = resolve_kis_tr_id(tr_id, self.credentials.env)
            headers["custtype"] = self.credentials.customer_type
            headers["tr_cont"] = tr_cont
        if use_hash and body:
            headers["hashkey"] = self.issue_hashkey(body)

        data = None
        if body is not None:
            data = json.dumps(dict(body)).encode("utf-8")

        request = Request(url, data=data, headers=headers, method=method.upper())
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = response.read().decode("utf-8")
                    headers_map = {key.lower(): value for key, value in response.headers.items()}
                    body_map = json.loads(payload) if payload else {}
                    return KISResponse(
                        status_code=response.status,
                        headers=headers_map,
                        body=body_map,
                    )
            except HTTPError as exc:
                should_retry = exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries
                last_error = exc
                if should_retry:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                message = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"KIS request failed with HTTP {exc.code}: {message}") from exc
            except URLError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * attempt)
                    continue
                raise RuntimeError(f"KIS request failed: {exc.reason}") from exc

        raise RuntimeError(f"KIS request failed after retries: {last_error}")  # pragma: no cover
