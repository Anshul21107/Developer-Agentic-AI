import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from .state import AgentState
from ..llm import get_llm

WEATHER_SUMMARY_PROMPT = """Rephrase ONLY the provided weather context.
Do not add or invent information.
Format as a short heading and 2-3 bullets."""


def _extract_location(user_input: str) -> str | None:
    match = re.search(
        r"\b(?:in|for|of)\s+([a-zA-Z\s]+)", user_input, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return None


async def _geocode_location(client: httpx.AsyncClient, location: str) -> dict | None:
    response = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("results") or []
    return results[0] if results else None


async def _fetch_weather(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict:
    response = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code,wind_speed_10m",
        },
    )
    response.raise_for_status()
    return response.json()


async def weather_tool_node(state: AgentState) -> dict:
    user_input = state.get("user_input", "")
    location = _extract_location(user_input)
    if not location:
        return {
            "tool_context": "Weather request detected but no location found.",
            "agent": "weather_agent",
        }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            geo = await _geocode_location(client, location)
            if not geo:
                return {
                    "tool_context": f"No location match found for '{location}'.",
                    "agent": "weather_agent",
                }
            weather = await _fetch_weather(client, geo["latitude"], geo["longitude"])
        except Exception:
            return {
                "tool_context": "Unable to fetch weather data right now.",
                "agent": "weather_agent",
            }

    current = weather.get("current") or {}
    temperature = current.get("temperature_2m")
    wind = current.get("wind_speed_10m")
    code = current.get("weather_code")
    place = geo.get("name")
    region = geo.get("admin1")
    country = geo.get("country")
    location_label = ", ".join(part for part in [place, region, country] if part)

    context = (
        f"**{location_label}**\n\n"
        f"**Weather:**\n\n"
        f"- Temperature: {temperature}C\n"
        f"- Wind: {wind} km/h\n"
    )
    llm = get_llm(streaming=False)
    response = await llm.ainvoke(
        [SystemMessage(content=WEATHER_SUMMARY_PROMPT), HumanMessage(content=context)]
    )
    summary = (response.content or "").strip()
    if not summary:
        summary = context
    return {"tool_context": summary, "agent": "weather_agent"}
