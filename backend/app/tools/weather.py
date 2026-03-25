"""Weather tool — fetches real-time weather from Open-Meteo."""

import httpx


async def _geocode(client: httpx.AsyncClient, location: str) -> dict | None:
    resp = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if results:
        return results[0]
    # Fallback: try just the first word (city name without state/country)
    first_word = location.split()[0] if " " in location else None
    if first_word:
        resp = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": first_word, "count": 1, "language": "en", "format": "json"},
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        return results[0] if results else None
    return None


async def _forecast(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    resp = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,wind_speed_10m",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def get_weather(location: str) -> dict:
    """Return structured weather data for *location*."""
    async with httpx.AsyncClient(timeout=10) as client:
        geo = await _geocode(client, location)
        if not geo:
            return {"error": f"No location match found for '{location}'."}

        weather = await _forecast(client, geo["latitude"], geo["longitude"])

    current = weather.get("current") or {}
    place = geo.get("name")
    region = geo.get("admin1")
    country = geo.get("country")
    location_label = ", ".join(p for p in [place, region, country] if p)

    return {
        "location": location_label,
        "temperature_c": current.get("temperature_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "weather_code": current.get("weather_code"),
    }
