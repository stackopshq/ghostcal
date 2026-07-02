"""Unit tests for the Open-Meteo adapter parsing (network mocked at the ``_get`` boundary)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from ghostcal.application.ports.weather import WeatherError
from ghostcal.infrastructure.weather.open_meteo import OpenMeteoClient


def _patch_get(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    async def fake_get(self: OpenMeteoClient, url: str, params: dict[str, str]) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(OpenMeteoClient, "_get", fake_get)


async def test_forecast_parses_daily_series(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(
        monkeypatch,
        {
            "daily": {
                "time": ["2026-07-02", "2026-07-03"],
                "weather_code": [3, 61],
                "temperature_2m_max": [24.5, 19.0],
                "temperature_2m_min": [14.0, 12.5],
                "precipitation_probability_max": [10, 80],
            }
        },
    )
    out = await OpenMeteoClient().forecast(46.2, 6.15, 2)
    assert len(out) == 2
    assert out[0].day == date(2026, 7, 2)
    assert out[0].weather_code == 3
    assert out[0].temp_max == 24.5
    assert out[1].precipitation_probability == 80


async def test_forecast_tolerates_missing_precipitation(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(
        monkeypatch,
        {
            "daily": {
                "time": ["2026-07-02"],
                "weather_code": [0],
                "temperature_2m_max": [30.0],
                "temperature_2m_min": [18.0],
            }
        },
    )
    out = await OpenMeteoClient().forecast(46.2, 6.15, 1)
    assert out[0].precipitation_probability is None


async def test_forecast_raises_on_malformed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(monkeypatch, {"error": True})
    with pytest.raises(WeatherError):
        await OpenMeteoClient().forecast(46.2, 6.15, 1)


async def test_search_parses_places_and_skips_bad_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(
        monkeypatch,
        {
            "results": [
                {"name": "Geneva", "country": "Switzerland", "latitude": 46.2, "longitude": 6.14},
                {"name": "Nowhere"},  # missing coords → skipped
            ]
        },
    )
    places = await OpenMeteoClient().search("Geneva")
    assert len(places) == 1
    assert places[0].name == "Geneva"
    assert places[0].country == "Switzerland"


async def test_search_returns_empty_when_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(monkeypatch, {})
    assert await OpenMeteoClient().search("zzz") == []
