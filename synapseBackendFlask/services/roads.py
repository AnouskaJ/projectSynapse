"""
Google Roads API service
"""
from typing import Dict, Any, List

from ..config import GOOGLE_MAPS_API_KEY
from ..utils.http import http_get

def snap_to_roads(points: List[List[float]], interpolate: bool = True) -> Dict[str, Any]:
    """Snap GPS points to roads using Roads API"""
    if not points or any(len(p) != 2 for p in points):
        return {"error": "invalid_points"}
    
    path = "|".join([f"{p[0]},{p[1]}" for p in points])
    url = "https://roads.googleapis.com/v1/snapToRoads"
    params = {
        "path": path, 
        "interpolate": "true" if interpolate else "false", 
        "key": GOOGLE_MAPS_API_KEY
    }
    
    try:
        data = http_get(url, params=params)
        sp = data.get("snappedPoints", [])[:5]
        return {"snappedPoints": sp, "count": len(sp)}
    except Exception as e:
        return {"error": f"roads_failure:{str(e)}"}