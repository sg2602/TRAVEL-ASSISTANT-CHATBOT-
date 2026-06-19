"""
tools.py — Three travel tools

  get_weather(city, days)        → wttr.in (free, no key)
  get_places(city, category)     → Geoapify (free key)
  get_country_info(country)      → static JSON (no API)
  get_destination_summary(city)  → Groq LLM
"""

import httpx
import json
import os
from zoneinfo import ZoneInfo
from datetime import datetime
from langchain_core.tools import tool

CLIENT = httpx.AsyncClient(timeout=15, headers={"User-Agent": "TravelAssistant/1.0"})

GEOAPIFY_KEY = os.getenv("GEOAPIFY_KEY", "567459a846d7409f8f0b095a20953493")

# ── Static country data ───────────────────────────────────────────────────────
COUNTRY_DATA = {
    "japan": {"capital": "Tokyo", "currency": "JPY (Yen)", "language": "Japanese", "visa": "Visa required for most", "timezone": "Asia/Tokyo", "drive_side": "left"},
    "india": {"capital": "New Delhi", "currency": "INR (Rupee)", "language": "Hindi, English", "visa": "Visa on arrival for many", "timezone": "Asia/Kolkata", "drive_side": "left"},
    "france": {"capital": "Paris", "currency": "EUR (Euro)", "language": "French", "visa": "Schengen visa", "timezone": "Europe/Paris", "drive_side": "right"},
    "usa": {"capital": "Washington D.C.", "currency": "USD (Dollar)", "language": "English", "visa": "ESTA or visa", "timezone": "America/New_York", "drive_side": "right"},
    "thailand": {"capital": "Bangkok", "currency": "THB (Baht)", "language": "Thai", "visa": "Visa on arrival 30 days", "timezone": "Asia/Bangkok", "drive_side": "left"},
    "italy": {"capital": "Rome", "currency": "EUR (Euro)", "language": "Italian", "visa": "Schengen visa", "timezone": "Europe/Rome", "drive_side": "right"},
    "uk": {"capital": "London", "currency": "GBP (Pound)", "language": "English", "visa": "ETA or visa", "timezone": "Europe/London", "drive_side": "left"},
    "germany": {"capital": "Berlin", "currency": "EUR (Euro)", "language": "German", "visa": "Schengen visa", "timezone": "Europe/Berlin", "drive_side": "right"},
    "spain": {"capital": "Madrid", "currency": "EUR (Euro)", "language": "Spanish", "visa": "Schengen visa", "timezone": "Europe/Madrid", "drive_side": "right"},
    "singapore": {"capital": "Singapore", "currency": "SGD (Dollar)", "language": "English, Mandarin, Malay", "visa": "Visa free for many", "timezone": "Asia/Singapore", "drive_side": "left"},
    "dubai": {"capital": "Abu Dhabi", "currency": "AED (Dirham)", "language": "Arabic, English", "visa": "Visa on arrival for many", "timezone": "Asia/Dubai", "drive_side": "right"},
    "australia": {"capital": "Canberra", "currency": "AUD (Dollar)", "language": "English", "visa": "ETA or visa", "timezone": "Australia/Sydney", "drive_side": "left"},
    "canada": {"capital": "Ottawa", "currency": "CAD (Dollar)", "language": "English, French", "visa": "eTA or visa", "timezone": "America/Toronto", "drive_side": "right"},
    "switzerland": {"capital": "Bern", "currency": "CHF (Franc)", "language": "German, French, Italian", "visa": "Schengen visa", "timezone": "Europe/Zurich", "drive_side": "right"},
    "greece": {"capital": "Athens", "currency": "EUR (Euro)", "language": "Greek", "visa": "Schengen visa", "timezone": "Europe/Athens", "drive_side": "right"},
    "turkey": {"capital": "Ankara", "currency": "TRY (Lira)", "language": "Turkish", "visa": "e-Visa", "timezone": "Europe/Istanbul", "drive_side": "right"},
    "indonesia": {"capital": "Jakarta", "currency": "IDR (Rupiah)", "language": "Indonesian", "visa": "Visa on arrival 30 days", "timezone": "Asia/Jakarta", "drive_side": "left"},
    "malaysia": {"capital": "Kuala Lumpur", "currency": "MYR (Ringgit)", "language": "Malay, English", "visa": "Visa free for many", "timezone": "Asia/Kuala_Lumpur", "drive_side": "left"},
    "nepal": {"capital": "Kathmandu", "currency": "NPR (Rupee)", "language": "Nepali", "visa": "Visa on arrival", "timezone": "Asia/Kathmandu", "drive_side": "left"},
    "maldives": {"capital": "Malé", "currency": "MVR (Rufiyaa)", "language": "Dhivehi", "visa": "Free 30 days on arrival", "timezone": "Indian/Maldives", "drive_side": "left"},
}


# ── Tool 1: Weather ───────────────────────────────────────────────────────────
@tool
async def get_weather(city: str) -> str:
    """Get current weather and forecast for a city using wttr.in. days must be an integer between 1 and 3."""
      # add this line
    days=3 
    try:
        days = int(days)
        resp = await CLIENT.get(f"https://wttr.in/{city}?format=j1")
        data = resp.json()

        current = data["current_condition"][0]
        temp_c = current["temp_C"]
        feels_c = current["FeelsLikeC"]
        humidity = current["humidity"]
        wind = current["windspeedKmph"]
        desc = current["weatherDesc"][0]["value"]

        result = (
            f"🌤️ Weather in {city}\n"
            f"Now: {temp_c}°C (feels like {feels_c}°C) | {desc}\n"
            f"💧 Humidity: {humidity}% | 💨 Wind: {wind} km/h\n\n"
        )

        days = min(days, 3)
        result += "📅 Forecast:\n"
        for i, day in enumerate(data["weather"][:days]):
            date = day["date"]
            max_c = day["maxtempC"]
            min_c = day["mintempC"]
            day_desc = day["hourly"][4]["weatherDesc"][0]["value"]
            rain = day["hourly"][4]["chanceofrain"]
            result += f"  {date}: {day_desc}, {min_c}°C–{max_c}°C, 🌧️ {rain}% rain chance\n"

        return result
    except Exception as e:
        return f"Could not fetch weather for {city}: {str(e)}"


# ── Tool 2: Places ────────────────────────────────────────────────────────────
CATEGORY_MAP = {
    "restaurant":  "catering.restaurant",
    "hotel":       "accommodation.hotel",
    "hostel":      "accommodation.hostel",
    "museum":      "entertainment.museum",
    "attraction":  "tourism.attraction",
    "monument":    "tourism.attraction",
    "cafe":        "catering.cafe",
    "bar":         "catering.bar",
    "park":        "leisure.park",
    "hospital":    "healthcare.hospital",
    "pharmacy":    "healthcare.pharmacy",
    "airport":     "airport",
    "shopping":    "commercial.shopping_mall",
}

@tool
async def get_places(city: str, category: str = "attraction") -> str:
    """
    Search for places in a city by category.
    Categories: restaurant, hotel, hostel, museum, attraction, monument,
                cafe, bar, park, hospital, pharmacy, airport, shopping
    """
    try:
        # Step 1: geocode city
        geo_resp = await CLIENT.get(
            "https://api.geoapify.com/v1/geocode/search",
            params={"text": city, "limit": 1, "apiKey": GEOAPIFY_KEY}
        )
        geo_data = geo_resp.json()
        if not geo_data.get("features"):
            return f"Could not find city: {city}"

        feature = geo_data["features"][0]
        bbox = feature.get("bbox")
        coords = feature["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]

        # Use bbox if available, else fall back to circle
        if bbox:
            west, south, east, north = bbox
            area_filter = f"rect:{west},{south},{east},{north}"
        else:
            area_filter = f"circle:{lon},{lat},15000"

        # Step 2: search places
        cat = CATEGORY_MAP.get(category.lower(), "tourism.attraction")
        places_resp = await CLIENT.get(
            "https://api.geoapify.com/v2/places",
            params={
                "categories": cat,
                "filter": area_filter,
                "limit": 8,
                "apiKey": GEOAPIFY_KEY
            }
        )
        places_data = places_resp.json()
        features = places_data.get("features", [])

        if not features:
            return f"No {category} places found in {city}."

        lines = [f"📍 Top {category.title()}s in {city}:\n"]
        for i, f in enumerate(features):
            props = f.get("properties", {})
            name = props.get("name", "Unnamed")
            address = props.get("formatted", "Address not available")
            lines.append(f"{i+1}. {name}\n   📌 {address}")

        return "\n".join(lines)
    except Exception as e:
        return f"Could not search places in {city}: {str(e)}"

# ── Tool 3: Country Info ──────────────────────────────────────────────────────
@tool
async def get_country_info(country: str) -> str:
    """
    Get travel information about a country: capital, currency, language,
    visa requirements, timezone, and current local time.
    """
    key = country.lower().strip()
    # try to match partial names
    matched = None
    for k in COUNTRY_DATA:
        if k in key or key in k:
            matched = k
            break

    if not matched:
        return (
            f"Country '{country}' not in local database. "
            f"Available: {', '.join(COUNTRY_DATA.keys())}"
        )

    info = COUNTRY_DATA[matched]

    # Get local time using Python's zoneinfo
    try:
        local_time = datetime.now(ZoneInfo(info["timezone"])).strftime("%I:%M %p, %A")
    except Exception:
        local_time = "N/A"

    return (
        f"🌍 {country.title()}\n"
        f"🏙️  Capital:   {info['capital']}\n"
        f"💰 Currency:  {info['currency']}\n"
        f"🗣️  Language:  {info['language']}\n"
        f"🛂 Visa:      {info['visa']}\n"
        f"⏰ Local time: {local_time}\n"
        f"🚗 Drive side: {info['drive_side']}"
    )


# ── Export ────────────────────────────────────────────────────────────────────
TOOLS = [get_weather, get_places, get_country_info]