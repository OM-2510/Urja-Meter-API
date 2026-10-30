from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

class Level(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None


class Hierarchy(BaseModel):
    zone: Optional[Level] = None
    circle: Optional[Level] = None
    division: Optional[Level] = None
    subdivision: Optional[Level] = None
    substation: Optional[Level] = None
    feeder: Optional[Level] = None
    dt: Optional[Level] = None


class GeoPoint(BaseModel):
    lat: float
    lng: float


class Meter(BaseModel):
    meter_id: str                     
    serial_no: Optional[str] = None
    make: Optional[str] = None
    phase_type: Optional[str] = None
    install_status: Optional[str] = None
    install_type: Optional[str] = None
    build: Optional[str] = None
    dt_code: Optional[str] = None
    hierarchy: Optional[Hierarchy] = None
    geo: Optional[GeoPoint] = None


class MeterPage(BaseModel):
    items: List[Meter]
    total: int
    page: int
    page_size: int


class Reading(BaseModel):
    timestamp: datetime              
    kwh: Optional[float] = None
    kvah: Optional[float] = None
    volt_r: Optional[float] = None


class Consumption(BaseModel):
    meter_id: str
    count: int
    readings: List[Reading]