"""
Geospatial utilities
"""
import math
import re
from typing import List, Optional, Any, Tuple

from ..services.google_maps import geocode

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance between two points in kilometers"""
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def coerce_point(any_val: Any) -> Optional[List[float]]:
    """
    Accepts [lat, lon] or "place string"; returns [lat, lon] or None.
    """
    if isinstance(any_val, (list, tuple)) and len(any_val) == 2:
        try:
            return [float(any_val[0]), float(any_val[1])]
        except Exception:
            return None
    if isinstance(any_val, str) and any_val.strip():
        pt = geocode(any_val.strip())
        if pt:
            return [pt[0], pt[1]]
    return None

def only_place_name(val: Any) -> Optional[str]:
    """
    Accept only human-readable place/address strings.
    - Lists/tuples/dicts like [lat,lon] or {lat,lon} are ignored.
    - Clean up whitespace; return None if blank.
    """
    if isinstance(val, str):
        t = val.strip()
        # discard "lat,lon" shape as a string too
        if t and not re.match(r"^\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*$", t):
            return t
    return None

def estimate_trip_minutes(pick_lat: float, pick_lon: float, drop_lat: float, drop_lon: float, 
                         baseline_speed_kmph: float = 40.0) -> float:
    """Estimate trip duration in minutes using haversine distance and baseline speed"""
    dist_km = haversine_km(pick_lat, pick_lon, drop_lat, drop_lon)
    return round((dist_km / baseline_speed_kmph) * 60.0, 1)