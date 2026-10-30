import hashlib
import hmac
import threading
import time
from typing import Optional
from urllib.parse import quote

import requests

SESSION_COOKIE = "__Secure-better-auth.session_token"


class PortalError(Exception):
    """The portal failed in a way we could not recover from."""


class PortalAuthError(PortalError):
    """The portal rejected our login."""


class PortalClient:
    def __init__(self, base_url: str, email: str, password: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self._secret: Optional[str] = None  # signingSecret
        self._logged_in = False
        self._lock = threading.RLock()

    def login(self) -> None:
        """POST /login. The portal answers HTTP 200 either way, so read the body."""
        with self._lock:
            self._logged_in = False
            self.session.cookies.clear()
            self._secret = None
            try:
                resp = self.session.post(
                    f"{self.base_url}/login",
                    data={"email": self.email, "password": self.password},
                    headers={"origin": self.base_url},
                    timeout=self.timeout,
                )
                body = resp.json()

            except (requests.RequestException, ValueError) as exc:
                raise PortalError(f"Login request failed: {exc}") from exc
            
            if (
                not isinstance(body, dict)
                or body.get("type") != "redirect"
                or SESSION_COOKIE not in self.session.cookies
            ):
                raise PortalAuthError(
                    "Portal rejected the login (check EMAIL / PASSWORD)"
                )
            self._logged_in = True

    def _get_secret(self, refresh: bool = False) -> str:
        """GET /portal/keys -> signingSecret, cached in memory for the session."""
        with self._lock:
            if self._secret is None or refresh:
                body = self._request("GET", "/portal/keys")
                try:
                    self._secret = body["data"]["signingSecret"]
                except (KeyError, TypeError) as exc:
                    raise PortalError("Unexpected /portal/keys response") from exc
            return self._secret

    @staticmethod
    def _sign(secret: str, method: str, path: str, query: str):
        """HMAC-SHA256 over method, path, query and timestamp joined by newlines."""
        timestamp = str(int(time.time()))
        message = "\n".join([method, path, query, timestamp])
        signature = hmac.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    @staticmethod
    def _error_code(resp) -> Optional[str]:
        try:
            body = resp.json()
        except ValueError:
            return None
        return body.get("error") if isinstance(body, dict) else None

    def _request(self, method: str, path: str, query: Optional[str] = None, signed: bool = False):
        """One portal call. Recovers once from an expired session and once from a bad signature."""
        if not self._logged_in:
            self.login()
        relogged = False
        refreshed = False
        for _ in range(3):  # first try + at most one retry per failure cause
            headers = {}
            if signed:
                secret = self._get_secret()
                timestamp, signature = self._sign(secret, method, path, query or "")
                headers = {"x-timestamp": timestamp, "x-signature": signature}
            url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
            try:
                resp = self.session.request(method, url, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                raise PortalError(f"Portal unreachable: {exc}") from exc

            if resp.status_code == 401:
                error = self._error_code(resp)
                if error == "unauthorized" and not relogged:
                    self.login()
                    relogged = True
                    continue
                if error == "signature_invalid" and signed and not refreshed:
                    self._get_secret(refresh=True)
                    refreshed = True
                    continue
                raise PortalError(f"Portal returned 401 ({error})")
            
            if not resp.ok:
                raise PortalError(f"Portal returned HTTP {resp.status_code}")
            
            try:
                return resp.json()
            except ValueError as exc:
                raise PortalError("Portal returned a non-JSON response") from exc
            
        raise PortalError("Portal request failed after retries")

    def fetch_export(self, page: int = 1) -> dict:
        """Signed bulk call: full meter records with geo and hierarchy."""
        body = self._request("GET", "/portal/export", query=f"page={page}", signed=True)
        if not isinstance(body, dict) or "data" not in body:
            raise PortalError("Unexpected export response")
        return body

    def fetch_energy(self, meter_id: str) -> list:
        """Half-hourly consumption rows for one meter (raw portal strings)."""
        body = self._request("GET", f"/portal/meters/{quote(meter_id, safe='')}/energy")
        try:
            return body["data"]
        except (KeyError, TypeError) as exc:
            raise PortalError("Unexpected energy response") from exc