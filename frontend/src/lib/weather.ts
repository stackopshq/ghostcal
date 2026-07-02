// Weather API client + helpers.
//
// The forecast and geocoding calls are proxied by our backend (the browser can't reach Open-Meteo
// under the strict CSP). The chosen location lives only in local storage — it is never sent to or
// persisted by the server beyond the per-request coordinates needed to fetch a forecast.

import { authedFetch } from "@/lib/auth";

export type WeatherDay = {
  day: string; // ISO date (YYYY-MM-DD)
  weather_code: number;
  temp_max: number;
  temp_min: number;
  precipitation_probability: number | null;
};

export type Place = {
  name: string;
  country: string | null;
  latitude: number;
  longitude: number;
};

export type WeatherLocation = { name: string; latitude: number; longitude: number };

const STORAGE_KEY = "gc_weather_loc";

export function getForecast(lat: number, lon: number, days = 10): Promise<WeatherDay[]> {
  const qs = new URLSearchParams({ lat: String(lat), lon: String(lon), days: String(days) });
  return authedFetch<WeatherDay[]>(`/v1/me/weather?${qs}`);
}

export function geocode(query: string): Promise<Place[]> {
  return authedFetch<Place[]>(`/v1/me/weather/geocode?q=${encodeURIComponent(query)}`);
}

export function savedLocation(): WeatherLocation | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as WeatherLocation) : null;
  } catch {
    return null;
  }
}

export function saveLocation(loc: WeatherLocation | null): void {
  if (loc) localStorage.setItem(STORAGE_KEY, JSON.stringify(loc));
  else localStorage.removeItem(STORAGE_KEY);
}

// WMO weather-interpretation code → a compact emoji glyph.
export function weatherGlyph(code: number): string {
  if (code === 0) return "☀️";
  if (code === 1 || code === 2) return "⛅";
  if (code === 3) return "☁️";
  if (code === 45 || code === 48) return "🌫️";
  if (code >= 51 && code <= 57) return "🌦️";
  if (code >= 61 && code <= 67) return "🌧️";
  if (code >= 71 && code <= 77) return "🌨️";
  if (code >= 80 && code <= 82) return "🌦️";
  if (code === 85 || code === 86) return "🌨️";
  if (code >= 95) return "⛈️";
  return "🌡️";
}
