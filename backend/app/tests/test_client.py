import hashlib
import hmac

import pytest

from app.portal_client import PortalAuthError, PortalClient, PortalError


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body
        self.ok = 200 <= status < 300

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def make_client():
    return PortalClient("https://portal.test", "me@example.com", "pw")


def test_sign_joins_method_path_query_timestamp_with_newlines(monkeypatch):
    monkeypatch.setattr("app.portal_client.time.time", lambda: 1793268045)
    timestamp, signature = PortalClient._sign("dummy-secret", "GET", "/portal/export", "page=1")
    expected = hmac.new(
        b"dummy-secret", b"GET\n/portal/export\npage=1\n1793268045", hashlib.sha256
    ).hexdigest()
    assert timestamp == "1793268045"
    assert signature == expected
    assert len(signature) == 64


def test_login_failure_body_raises_even_with_http_200():
    client = make_client()
    client.session.post = lambda *a, **k: FakeResponse(200, {"type": "failure", "status": 401})
    with pytest.raises(PortalAuthError):
        client.login()


def test_expired_session_logs_in_again_and_retries_once():
    client = make_client()
    client._logged_in = True
    logins = []
    client.login = lambda: logins.append(1)
    responses = [FakeResponse(401, {"error": "unauthorized"}), FakeResponse(200, {"data": []})]
    client.session.request = lambda *a, **k: responses.pop(0)
    assert client._request("GET", "/portal/meters/J1/energy") == {"data": []}
    assert len(logins) == 1


def test_bad_signature_refreshes_secret_once_then_gives_up():
    client = make_client()
    client._logged_in = True
    refreshes = []
    client._get_secret = lambda refresh=False: (refreshes.append(refresh), "secret")[1]
    client.session.request = lambda *a, **k: FakeResponse(401, {"error": "signature_invalid"})
    with pytest.raises(PortalError):
        client._request("GET", "/portal/export", query="page=1", signed=True)
    assert refreshes.count(True) == 1