"""
Environment monitoring tools (weather, air quality, etc.)
"""
from typing import Dict, Any, Optional
import time

from ..services.weather_air import get_weather, get_air_quality, get_pollen_forecast
from ..services.google_maps import get_time_zone

def tool_check_weather(lat: float, lon: float) -> Dict[str, Any]:
    """Get current weather conditions"""
    return get_weather(lat, lon)

def tool_air_quality(lat: float, lon: float) -> Dict[str, Any]:
    """Get current air quality information"""
    return get_air_quality(lat, lon)

def tool_pollen_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Get pollen forecast information"""
    return get_pollen_forecast(lat, lon)

def tool_time_zone(lat: float, lon: float, timestamp: Optional[int] = None) -> Dict[str, Any]:
    """Get time zone for location"""
    return get_time_zone(lat, lon, timestamp)

def tool_geocode_place(query: str) -> Dict[str, Any]:
    """Geocode a place name to coordinates"""
    from ..services.google_maps import geocode
    pt = geocode(query)
    if not pt:
        return {"found": False}
    lat, lon = pt
    return {"found": True, "lat": lat, "lon": lon, "query": query}