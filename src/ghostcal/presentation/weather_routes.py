"""Weather proxy endpoints (Open-Meteo).

The browser can't reach Open-Meteo directly under our strict CSP, so these authenticated endpoints
proxy the forecast and geocoding calls. The location is supplied per request and never persisted —
the client keeps the chosen place in local storage only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ghostcal.application.ports.weather import WeatherError
from ghostcal.infrastructure.weather import OpenMeteoClient
from ghostcal.presentation.dashboard_routes import Member, current_member
from ghostcal.presentation.schemas import PlaceOut, WeatherDayOut

router = APIRouter(prefix="/v1/me/weather", tags=["weather"])
_client = OpenMeteoClient()

_MAX_DAYS = 16


@router.get("", response_model=list[WeatherDayOut])
async def get_weather(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    days: int = Query(default=7, ge=1, le=_MAX_DAYS),
    _member: Member = Depends(current_member),
) -> list[WeatherDayOut]:
    try:
        forecast = await _client.forecast(lat, lon, days)
    except WeatherError as exc:
        raise HTTPException(status_code=502, detail=f"weather unavailable: {exc}") from exc
    return [WeatherDayOut.model_validate(f, from_attributes=True) for f in forecast]


@router.get("/geocode", response_model=list[PlaceOut])
async def geocode(
    q: str = Query(min_length=2, max_length=120),
    _member: Member = Depends(current_member),
) -> list[PlaceOut]:
    try:
        places = await _client.search(q)
    except WeatherError as exc:
        raise HTTPException(status_code=502, detail=f"geocoding unavailable: {exc}") from exc
    return [PlaceOut.model_validate(p, from_attributes=True) for p in places]
