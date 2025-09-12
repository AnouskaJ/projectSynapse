"""
Google Maps API services
"""
from typing import Dict, Any, Optional, Tuple
import requests

from ..config import GOOGLE_MAPS_API_KEY
from ..utils.http import http_get, http_post
from ..logger import get_logger

log = get_logger(__name__)

def _gm_headers(field_mask: Optional[str] = None) -> Dict[str, str]:
    """Generate Google Maps API headers"""
    h = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY}
    if field_mask:
        h["X-Goog-FieldMask"] = field_mask
    return h

def geocode(text: str) -> Optional[Tuple[float, float]]:
    """Geocode a text address to lat/lon coordinates"""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": text, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        results = data.get("results") or []
        if not results:
            return None
        loc = results[0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
    except Exception as e:
        log.warning(f"[geocode] failed for '{text}': {e}")
        return None

def get_directions(origin: str, destination: str, mode: str = "driving", 
                  departure_time: str = "now") -> Dict[str, Any]:
    """Get directions between two locations"""
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin, 
        "destination": destination,
        "mode": mode, 
        "region": "in", 
        "language": "en",
        "alternatives": "true", 
        "key": GOOGLE_MAPS_API_KEY,
    }
    if mode == "driving":
        params.update(departure_time=departure_time, traffic_model="best_guess")
    
    response = requests.get(url, params=params, timeout=15)
    return response.json()

def get_time_zone(lat: float, lon: float, timestamp: Optional[int] = None) -> Dict[str, Any]:
    """Get timezone information for coordinates"""
    import time
    if not timestamp:
        timestamp = int(time.time())
    url = "https://maps.googleapis.com/maps/api/timezone/json"
    params = {"location": f"{lat},{lon}", "timestamp": timestamp, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return {
            "timeZoneId": data.get("timeZoneId"),
            "timeZoneName": data.get("timeZoneName"),
            "rawOffset": data.get("rawOffset"),
            "dstOffset": data.get("dstOffset"),
            "status": data.get("status"),
            "found": bool(data.get("timeZoneId"))
        }
    except Exception as e:
        return {"error": f"time_zone_failure:{str(e)}"}