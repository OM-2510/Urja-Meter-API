import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .schema import Consumption, GeoPoint, Hierarchy, Level, Meter, MeterPage, Reading

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
LEVELS = ("zone", "circle", "division", "subdivision", "substation", "feeder", "dt")


class TTLCache:
    """Tiny in-memory cache: an entry expires `ttl` seconds after it is stored."""
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._items = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            self._items.pop(key, None)
            return None

    def set(self, key, value):
        with self._lock:
            self._items[key] = (time.monotonic() + self.ttl, value)


def _num(value) -> Optional[float]:
    """Portal numbers arrive as strings; return None if one is missing or unreadable."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _level(raw) -> Optional[Level]:
    return Level(code=raw.get("code"), name=raw.get("name")) if raw else None


def _to_meter(rec: dict) -> Meter:
    # Only meterId is required; every other field falls back to None.
    h = rec.get("hierarchy")
    hierarchy = Hierarchy(**{k: _level(h.get(k)) for k in LEVELS}) if h else None
    g = rec.get("geo") or {}
    lat, lng = _num(g.get("lat")), _num(g.get("lng"))
    geo = GeoPoint(lat=lat, lng=lng) if lat is not None and lng is not None else None
    return Meter(
        meter_id=rec["meterId"],
        serial_no=rec.get("serialNo"),
        make=rec.get("make"),
        phase_type=rec.get("phaseType"),
        install_status=rec.get("installStatus"),
        install_type=rec.get("installType"),
        build=rec.get("build"),
        dt_code=rec.get("dtCode"),
        hierarchy=hierarchy,
        geo=geo,
    )


def _to_reading(raw: dict) -> Reading:
    # Only the timestamp is required; unreadable values become None.
    stamp = datetime.strptime(raw["timestamp"], "%d/%m/%Y %H:%M").replace(tzinfo=IST)
    return Reading(
        timestamp=stamp,
        kwh=_num(raw.get("kwh")),
        kvah=_num(raw.get("kvah")),
        volt_r=_num(raw.get("voltR")),
    )


def _parse_all(raw_rows, convert, what: str) -> list:
    """Convert every record; skip (and log) only records missing their identity field."""
    out, skipped = [], 0
    for row in raw_rows:
        try:
            out.append(convert(row))
        except (KeyError, TypeError, ValueError, AttributeError):
            skipped += 1
    if skipped:
        log.warning("Skipped %d malformed %s record(s)", skipped, what)
    return out


def _eq(value, wanted) -> bool:
    return wanted is None or (value or "").lower() == wanted.lower()


def as_ist(dt: datetime) -> datetime:
    """Treat a naive datetime as IST so it can be compared with timezone-aware ones."""
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


class MeterService:
    def __init__(self, client, ttl: float = 300):
        self.client = client
        self._export_cache = TTLCache(ttl)
        self._energy_cache = TTLCache(ttl)
        self._fetch_lock = threading.Lock()

    def _meters(self) -> List[Meter]:
        cached = self._export_cache.get("meters")
        if cached is not None:
            return cached
        with self._fetch_lock:  # one portal export call even under concurrent requests
            cached = self._export_cache.get("meters")
            if cached is not None:
                return cached
            raw = self.client.fetch_export(1)
            meters = _parse_all(raw["data"], _to_meter, "meter")
            meters.sort(key=lambda m: m.meter_id)
            self._export_cache.set("meters", meters)
            return meters

    def list_meters(self, *, q=None, make=None, phase_type=None, install_status=None,
                    dt_code=None, page=1, page_size=20) -> MeterPage:
        items = self._meters()
        if q:
            needle = q.lower()
            items = [
                m for m in items
                if needle in m.meter_id.lower() or needle in (m.serial_no or "").lower()
            ]
        items = [
            m for m in items
            if _eq(m.make, make) and _eq(m.phase_type, phase_type)
            and _eq(m.install_status, install_status) and _eq(m.dt_code, dt_code)
        ]
        start = (page - 1) * page_size
        return MeterPage(items=items[start:start + page_size], total=len(items),
                         page=page, page_size=page_size)

    def get_meter(self, meter_id: str) -> Optional[Meter]:
        return next((m for m in self._meters() if m.meter_id == meter_id), None)

    def get_consumption(self, meter_id: str, start: Optional[datetime] = None,
                        end: Optional[datetime] = None) -> Optional[Consumption]:
        if self.get_meter(meter_id) is None:  # unknown meter: never ask the portal
            return None
        readings = self._energy_cache.get(meter_id)
        if readings is None:
            readings = _parse_all(self.client.fetch_energy(meter_id), _to_reading, "reading")
            self._energy_cache.set(meter_id, readings)
        if start:
            readings = [r for r in readings if r.timestamp >= as_ist(start)]
        if end:
            readings = [r for r in readings if r.timestamp <= as_ist(end)]
        return Consumption(meter_id=meter_id, count=len(readings), readings=readings)