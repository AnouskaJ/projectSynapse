"""
Weather and Air Quality API services
"""
from typing import Dict, Any

from ..config import GOOGLE_MAPS_API_KEY
from ..utils.http import http_get

def get_weather(lat: float, lon: float) -> Dict[str, Any]:
    """Get current weather conditions"""
    url = "https://weather.googleapis.com/v1/currentConditions:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        cc = (data.get("currentConditions") or {})
        return {
            "tempC": cc.get("temperature", {}).get("value"),
            "temperatureUnit": cc.get("temperature", {}).get("unitCode"),
            "windSpeed": cc.get("wind", {}).get("speed", {}).get("value"),
            "windUnit": cc.get("wind", {}).get("speed", {}).get("unitCode"),
            "shortText": cc.get("shortPhrase"),
            "raw": cc
        }
    except Exception as e:
        return {"error": f"weather_failure:{str(e)}"}

def get_air_quality(lat: float, lon: float) -> Dict[str, Any]:
    """Get current air quality information"""
    url = "https://airquality.googleapis.com/v1/currentConditions:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        aq = data.get("indexes", [{}])[0] if isinstance(data.get("indexes"), list) else {}
        return {
            "code": aq.get("code"),
            "aqi": aq.get("aqi"),
            "category": aq.get("category"),
            "dominantPollutant": aq.get("dominantPollutant"),
            "raw": data
        }
    except Exception as e:
        return {"error": f"air_quality_failure:{str(e)}"}

def get_pollen_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Get pollen forecast information"""
    url = "https://pollen.googleapis.com/v1/forecast:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return {"found": True, "raw": data}
    except Exception as e:
        return {"error": f"pollen_failure:{str(e)}"}