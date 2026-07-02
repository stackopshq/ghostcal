"""Open-Meteo adapter: free, keyless daily forecast + geocoding.

Open-Meteo (https://open-meteo.com) needs no API key and is CORS-restricted, so the browser cannot
call it directly under our strict CSP — this server-side proxy is the only path. Hosts are fixed
constants (not user-supplied), so no SSRF check is needed; redirects are disabled regardless.
"""

from __future__ import annotations

from datetime import date

import httpx

from ghostcal.application.ports.weather import DailyForecast, Place, WeatherError

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_TIMEOUT = 8.0


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


class OpenMeteoClient:
    async def forecast(self, latitude: float, longitude: float, days: int) -> list[DailyForecast]:
        params = {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            ),
            "timezone": "auto",
            "forecast_days": str(days),
        }
        data = await self._get(_FORECAST_URL, params)
        daily = data.get("daily")
        if not isinstance(daily, dict):
            raise WeatherError("malformed forecast response")
        times = _as_list(daily.get("time"))
        codes = _as_list(daily.get("weather_code"))
        tmax = _as_list(daily.get("temperature_2m_max"))
        tmin = _as_list(daily.get("temperature_2m_min"))
        precip = _as_list(daily.get("precipitation_probability_max"))
        try:
            out: list[DailyForecast] = []
            for i in range(len(times)):
                pp = precip[i] if i < len(precip) and precip[i] is not None else None
                out.append(
                    DailyForecast(
                        day=date.fromisoformat(str(times[i])),
                        weather_code=int(str(codes[i])),
                        temp_max=float(str(tmax[i])),
                        temp_min=float(str(tmin[i])),
                        precipitation_probability=int(str(pp)) if pp is not None else None,
                    )
                )
            return out
        except (IndexError, TypeError, ValueError) as exc:
            raise WeatherError(f"could not parse forecast: {exc}") from exc

    async def search(self, query: str) -> list[Place]:
        params = {"name": query, "count": "5", "language": "en", "format": "json"}
        data = await self._get(_GEOCODE_URL, params)
        results = data.get("results")
        if not isinstance(results, list):
            return []
        places: list[Place] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            try:
                places.append(
                    Place(
                        name=str(r["name"]),
                        country=str(r["country"]) if r.get("country") else None,
                        latitude=float(r["latitude"]),
                        longitude=float(r["longitude"]),
                    )
                )
            except KeyError, TypeError, ValueError:
                continue
        return places

    async def _get(self, url: str, params: dict[str, str]) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
                resp = await client.get(url, params=params, headers={"accept": "application/json"})
        except httpx.HTTPError as exc:
            raise WeatherError(str(exc)) from exc
        if resp.status_code != 200:
            raise WeatherError(f"weather API returned {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise WeatherError("weather API returned non-JSON") from exc
        if not isinstance(body, dict):
            raise WeatherError("unexpected weather API response")
        return body
