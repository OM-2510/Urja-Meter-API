from datetime import datetime
from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app import config
from app.portal_client import PortalClient, PortalError
from app.schema import Consumption, Meter, MeterPage
from app.service import MeterService, as_ist

app = FastAPI(title="Urja Meter API", description="Clean and Organized service over Urja Meter Ops Portal")

@lru_cache
def get_service() -> MeterService:
    if not config.BASE_URL:
        raise RuntimeError("Set BASE_URL")
    if not (config.EMAIL and config.PASSWORD):
        raise RuntimeError("Set EMAIL and PASSWORD")
    
    client = PortalClient(config.BASE_URL, config.EMAIL, config.PASSWORD)
    return MeterService(client, config.CACHE_TTL_SECONDS)


@app.exception_handler(PortalError)
async def portal_error_handler(request, exc: PortalError):
    return JSONResponse(status_code=502, content={"error": "portal_unavailable", "detail": str(exc)})


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/meters", response_model=MeterPage, tags=["meters"])
def list_meters(
    q: Optional[str] = Query(None, description="Case-insensitive substring of meter ID or serial number"),
    make: Optional[str] = Query(None, description="Exact match, e.g. HPL, Genus"),
    phase_type: Optional[str] = Query(None, description="single or three"),
    install_status: Optional[str] = Query(None, description="Installed, Faulty or Decommissioned"),
    dt_code: Optional[str] = Query(None, description="Distribution transformer code, e.g. DT-001"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: MeterService = Depends(get_service),
):
    return service.list_meters(q=q, make=make, phase_type=phase_type, install_status=install_status,
                               dt_code=dt_code, page=page, page_size=page_size)


@app.get("/meters/{meter_id}", response_model=Meter, tags=["meters"])
def get_meter(meter_id: str, service: MeterService = Depends(get_service)):
    meter = service.get_meter(meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail=f"Meter {meter_id} not found")
    return meter


@app.get("/meters/{meter_id}/consumption", response_model=Consumption, tags=["meters"])
def get_consumption(
    meter_id: str,
    from_: Optional[datetime] = Query(None, alias="from", description="ISO 8601; naive values are treated as IST"),
    to: Optional[datetime] = Query(None, description="ISO 8601; naive values are treated as IST"),
    service: MeterService = Depends(get_service),
):
    if from_ and to and as_ist(from_) > as_ist(to):
        raise HTTPException(status_code=422, detail="'from' must not be after 'to'")
    result = service.get_consumption(meter_id, from_, to)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Meter {meter_id} not found")
    return result