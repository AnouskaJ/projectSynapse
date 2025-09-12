"""
Roads and routing tools
"""
from typing import Dict, Any, List

from ..services.roads import snap_to_roads
from ..utils.geo import coerce_point

def tool_roads_snap(points: List[List[float]], interpolate: bool = True) -> Dict[str, Any]:
    """Snap GPS points to roads using Roads API"""
    return snap_to_roads(points, interpolate)

def tool_compute_route_matrix(origins: List[Any], destinations: List[Any]) -> Dict[str, Any]:
    """Compute route matrix between multiple origins and destinations"""
    if not origins or not destinations:
        return {"error": "missing_origins_or_destinations"}

    def wp_from_any(val):
        pt = coerce_point(val)  # strictly lat/lon list/tuple or geocoded string
        if not pt:
            raise ValueError("bad_point")
        return {"waypoint": {"location": {"latLng": {"latitude": pt[0], "longitude": pt[1]}}}}

    try:
        body = {
            "origins": [wp_from_any(o) for o in origins],
            "destinations": [wp_from_any(d) for d in destinations],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE"
        }
        # TODO: Implement actual Routes API call for matrix
        return {"status": "ok", "matrix": "not_implemented"}
    except Exception:
        return {"error": "bad_points"}