"""Weather provider port: a daily forecast and place lookup for a location.

The application depends on this interface; the concrete weather API lives behind the adapter. No
location is ever persisted — the caller passes coordinates per request (kept client-side only).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


class WeatherError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DailyForecast:
    day: date
    weather_code: int  # WMO weather-interpretation code
    temp_max: float
    temp_min: float
    precipitation_probability: int | None


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    country: str | None
    latitude: float
    longitude: float


class WeatherProvider(Protocol):
    async def forecast(self, latitude: float, longitude: float, days: int) -> list[DailyForecast]:
        """Daily forecast for the next ``days`` days. Raises ``WeatherError`` on any failure."""
        ...

    async def search(self, query: str) -> list[Place]:
        """Geocode a free-text place name to candidate coordinates."""
        ...
