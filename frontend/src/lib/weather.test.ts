import { afterEach, describe, expect, it, vi } from "vitest";

const authedFetch = vi.fn(async () => []);
vi.mock("@/lib/auth", () => ({ authedFetch: (...args: unknown[]) => authedFetch(...args) }));

import { geocode, getForecast, saveLocation, savedLocation, weatherGlyph } from "@/lib/weather";

afterEach(() => {
  authedFetch.mockClear();
  localStorage.clear();
});

describe("weatherGlyph", () => {
  it("maps WMO codes to distinct glyphs across conditions", () => {
    expect(weatherGlyph(0)).toBe("☀️"); // clear
    expect(weatherGlyph(3)).toBe("☁️"); // overcast
    expect(weatherGlyph(45)).toBe("🌫️"); // fog
    expect(weatherGlyph(63)).toBe("🌧️"); // rain
    expect(weatherGlyph(75)).toBe("🌨️"); // snow
    expect(weatherGlyph(95)).toBe("⛈️"); // thunderstorm
  });

  it("falls back to a thermometer for unmapped codes", () => {
    expect(weatherGlyph(4)).toBe("🌡️"); // a gap between the mapped WMO ranges
  });
});

describe("weather API client", () => {
  it("requests the forecast with lat/lon/days query params", async () => {
    await getForecast(46.2, 6.15, 7);
    const [path] = authedFetch.mock.calls[0] as [string];
    expect(path).toMatch(/^\/v1\/me\/weather\?/);
    expect(path).toContain("lat=46.2");
    expect(path).toContain("lon=6.15");
    expect(path).toContain("days=7");
  });

  it("geocodes under /v1/me/weather/geocode with an encoded query", async () => {
    await geocode("São Paulo");
    expect(authedFetch).toHaveBeenCalledWith("/v1/me/weather/geocode?q=S%C3%A3o%20Paulo");
  });
});

describe("weather location persistence", () => {
  it("round-trips a saved location and clears it on null", () => {
    expect(savedLocation()).toBeNull();
    saveLocation({ name: "Geneva", latitude: 46.2, longitude: 6.15 });
    expect(savedLocation()).toEqual({ name: "Geneva", latitude: 46.2, longitude: 6.15 });
    saveLocation(null);
    expect(savedLocation()).toBeNull();
  });

  it("returns null on corrupt storage rather than throwing", () => {
    localStorage.setItem("gc_weather_loc", "{not json");
    expect(savedLocation()).toBeNull();
  });
});
