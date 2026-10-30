import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app, get_service
from app.service import MeterService

LEVELS = ("zone", "circle", "division", "subdivision", "substation", "feeder", "dt")


def _rec(meter_id, status, dt="DT-001"):
    return {
        "meterId": meter_id, "serialNo": "SN" + meter_id[-3:], "make": "HPL",
        "phaseType": "single", "installStatus": status, "installType": "Whole Current",
        "build": "legacy", "dtCode": dt,
        "hierarchy": {k: {"code": k.upper(), "name": "Name " + k} for k in LEVELS},
        "geo": {"lat": 26.9, "lng": 75.8},
    }


class FakeClient:
    def fetch_export(self, page=1):
        return {"total": 3, "data": [
            _rec("J100000", "Installed"),
            _rec("J100001", "Faulty"),
            _rec("J100002", "Installed", "DT-002"),
        ]}

    def fetch_energy(self, meter_id):
        return [
            {"timestamp": "30/06/2026 23:00", "kwh": "10.5", "kvah": "11", "voltR": "230"},
            {"timestamp": "30/06/2026 23:30", "kwh": "10.6", "kvah": "11.1", "voltR": "228"},
        ]


@pytest.fixture
def client():
    service = MeterService(FakeClient(), ttl=60)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_meters_returns_page_and_total(client):
    body = client.get("/meters").json()
    assert body["total"] == 3
    assert body["items"][0]["meter_id"] == "J100000"


def test_filter_is_case_insensitive_and_pagination_works(client):
    assert client.get("/meters", params={"install_status": "faulty"}).json()["total"] == 1
    page2 = client.get("/meters", params={"page_size": 2, "page": 2}).json()
    assert len(page2["items"]) == 1


def test_meter_detail_has_nested_hierarchy_and_404_for_unknown(client):
    ok = client.get("/meters/J100000").json()
    assert ok["hierarchy"]["feeder"]["code"] == "FEEDER"
    assert client.get("/meters/NOPE").status_code == 404


def test_consumption_is_normalised_and_filterable(client):
    body = client.get("/meters/J100000/consumption").json()
    assert body["count"] == 2
    assert body["readings"][0]["timestamp"] == "2026-06-30T23:00:00+05:30"
    assert body["readings"][0]["kwh"] == 10.5
    later = client.get("/meters/J100000/consumption",
                       params={"from": "2026-06-30T23:30:00+05:30"}).json()
    assert later["count"] == 1
    assert client.get("/meters/NOPE/consumption").status_code == 404


def test_service_requires_base_url(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", None)
    monkeypatch.setattr(config, "EMAIL", "me@example.com")
    monkeypatch.setattr(config, "PASSWORD", "pw")
    get_service.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="Set BASE_URL"):
            get_service()
    finally:
        get_service.cache_clear()