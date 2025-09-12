"""
Traffic and routing tools
"""
import urllib.parse
import requests
import json
import re
from typing import Dict, Any, Optional, List

from ..config import GOOGLE_MAPS_API_KEY, ROUTES_KEY, ROUTES_ENDPOINT
from ..services.google_maps import get_directions
from ..services.llm import llm
from ..utils.geo import only_place_name
from ..utils.jsonx import safe_json, strip_json_block
from ..logger import get_logger

log = get_logger(__name__)

ROUTES_KEY = GOOGLE_MAPS_API_KEY
ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

# Hint extractors
HINT_RE_ORIGIN = re.compile(r"origin\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)
HINT_RE_DEST   = re.compile(r"dest\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)

def extract_hints(scenario: str, driver_token: Optional[str], passenger_token: Optional[str]) -> Dict[str, Any]:
    """
    Build hints from the scenario.
    - Accept numeric origin/dest if explicitly given (origin=lat,lon / dest=lat,lon).
    - Always ask Gemini to infer origin_place/dest_place from the scenario text.
    """
    hints: Dict[str, Any] = {}

    # Numeric coordinates (optional)
    m1, m2 = HINT_RE_ORIGIN.search(scenario), HINT_RE_DEST.search(scenario)
    if m1 and m2:
        hints["origin"] = [float(m1.group(1)), float(m1.group(2))]
        hints["dest"]   = [float(m2.group(1)), float(m2.group(2))]

    # Gemini-derived places
    rd = _gemini_route_from_text(scenario)
    if rd.get("origin_place"):
        hints["origin_place"] = rd["origin_place"]
    if rd.get("dest_place"):
        hints["dest_place"] = rd["dest_place"]

    if driver_token:    hints["driver_token"] = driver_token
    if passenger_token: hints["passenger_token"] = passenger_token
    hints["scenario_text"] = scenario
    return hints

def _gemini_route_from_text(scenario: str) -> Dict[str, Optional[str]]:
    """
    Ask Gemini to extract one origin and one destination place *name* from free text.
    Returns {"origin_place": str|None, "dest_place": str|None}
    """
    prompt = f"""
        Extract exactly TWO concise place names from the scenario: the pickup/origin and the dropoff/destination.

        Return STRICT JSON only:
        {{
        "origin_place": "<origin place name or empty if unknown>",
        "dest_place": "<destination place name or empty if unknown>"
        }}

        Rules:
        - Prefer the most specific, human-readable names (street + area, mall name, etc.).
        - If only one place is mentioned, treat it as the destination and leave origin empty.
        - Do not include coordinates or extra punctuation.

        Scenario:
        {scenario}
        """
    try:
        resp = llm.generate_content(prompt)
        text = getattr(resp, "text", "") or "{}"
        data = safe_json(strip_json_block(text), {}) or {}
        op = (data.get("origin_place") or "").strip() or None
        dp = (data.get("dest_place") or "").strip() or None
        return {"origin_place": op, "dest_place": dp}
    except Exception:
        return {"origin_place": None, "dest_place": None}

def _extract_places_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract origin and destination place names from text using LLM"""
    rd = _gemini_route_from_text(text or "")
    return (rd.get("origin_place"), rd.get("dest_place"))
"""
Traffic and routing tools
"""
import urllib.parse
import requests
import json
from typing import Dict, Any, Optional, List

from ..config import GOOGLE_MAPS_API_KEY, ROUTES_KEY, ROUTES_ENDPOINT
from ..services.google_maps import get_directions
from ..services.llm import llm
from ..utils.geo import only_place_name
from ..utils.jsonx import safe_json, strip_json_block
from ..logger import get_logger

log = get_logger(__name__)

ROUTES_KEY = GOOGLE_MAPS_API_KEY
ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

def _extract_places_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract origin and destination place names from text using LLM"""
    prompt = f"""
    Extract exactly TWO concise place names from the scenario: the pickup/origin and the dropoff/destination.

    Return STRICT JSON only:
    {{
    "origin_place": "<origin place name or empty if unknown>",
    "dest_place": "<destination place name or empty if unknown>"
    }}

    Rules:
    - Prefer the most specific, human-readable names (street + area, mall name, etc.).
    - If only one place is mentioned, treat it as the destination and leave origin empty.
    - Do not include coordinates or extra punctuation.

    Scenario:
    {text}
    """
    
    try:
        resp = llm.generate_content(prompt)
        text = getattr(resp, "text", "") or "{}"
        data = safe_json(strip_json_block(text), {}) or {}
        op = (data.get("origin_place") or "").strip() or None
        dp = (data.get("dest_place") or "").strip() or None
        return (op, dp)
    except Exception:
        return (None, None)

def tool_check_traffic(
    origin_any: Optional[str] = None,
    dest_any: Optional[str] = None,
    travel_mode: str = "DRIVE",
    scenario_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Traffic-aware ETA between two place names (Google Directions).
    Adds: map.embedUrl → ready for <iframe>.
    """
    try:
        # Clean / fallback extraction
        o_name = (only_place_name(origin_any) or "").strip()
        d_name = (only_place_name(dest_any) or "").strip()

        if (not o_name or not d_name) and scenario_text:
            try:
                gx_o, gx_d = _extract_places_from_text(scenario_text)
                o_name = o_name or (gx_o or "").strip()
                d_name = d_name or (gx_d or "").strip()
            except Exception:
                pass

        if not o_name or not d_name:
            return {"status": "error", "error": "missing_place_names",
                    "origin_place": o_name or None, "dest_place": d_name or None}

        # Mode mapping
        mode = {
            "DRIVE":"driving","DRIVING":"driving","CAR":"driving",
            "WALK":"walking","WALKING":"walking",
            "BIKE":"bicycling","BICYCLE":"bicycling","BICYCLING":"bicycling",
            "TRANSIT":"transit","TWO_WHEELER":"driving",
        }.get((travel_mode or "DRIVE").strip().upper(), "driving")

        # Call Directions API
        data = get_directions(o_name, d_name, mode, "now")
        
        if data.get("status") != "OK" or not data.get("routes"):
            return {"status": "error", "error": "directions_failed",
                    "origin_place": o_name, "dest_place": d_name, "raw": data}

        # Parse first route + steps
        leg = data["routes"][0]["legs"][0]
        norm_sec = (leg["duration"]).get("value", 0)
        traf_sec = (leg.get("duration_in_traffic") or {}).get("value", norm_sec)

        steps = [{
            "instructions": s.get("html_instructions"),
            "distance_m": (s.get("distance") or {}).get("value"),
            "duration_sec": (s.get("duration") or {}).get("value"),
            "start_location": s.get("start_location"),
            "end_location": s.get("end_location"),
            "polyline": (s.get("polyline") or {}).get("points"),
        } for s in leg.get("steps", [])]

        # Build Embed URL
        embed_url = (
            "https://www.google.com/maps/embed/v1/directions"
            f"?key={GOOGLE_MAPS_API_KEY}"
            f"&origin={urllib.parse.quote_plus(o_name)}"
            f"&destination={urllib.parse.quote_plus(d_name)}"
            f"&mode={mode}"
        )

        # Return
        bounds = data["routes"][0].get("bounds")
        ne, sw = bounds.get("northeast"), bounds.get("southwest") if bounds else (None, None)
        map_bounds = {"south": sw["lat"], "west": sw["lng"], "north": ne["lat"], "east": ne["lng"]} if ne and sw else None

        return {
            "status": "ok",
            "origin_place": o_name, "dest_place": d_name, "mode": mode,
            "duration_min": round(norm_sec/60), "duration_traffic_min": round(traf_sec/60),
            "distance_km": round((leg.get("distance") or {}).get("value", 0)/1000, 2),
            "steps": steps,
            "map": {
                "kind": "directions",
                "bounds": map_bounds,
                "polyline": data["routes"][0]["overview_polyline"]["points"],
                "embedUrl": embed_url,
            },
        }

    except Exception as e:
        return {"status": "error", "error": f"traffic_check_failure:{e}",
                "origin_place": origin_any, "dest_place": dest_any}

def tool_calculate_alternative_route(
    origin_any: Optional[str] = None,
    dest_any: Optional[str] = None,
    travel_mode: str = "DRIVE",
    scenario_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Get main + alternate routes via Routes API (computeAlternativeRoutes=True)."""

    # Resolve free-form names
    o_name = (only_place_name(origin_any) or "").strip()
    d_name = (only_place_name(dest_any) or "").strip()
    
    if (not o_name or not d_name) and scenario_text:
        try:
            gx_o, gx_d = _extract_places_from_text(scenario_text)
            o_name = o_name or (gx_o or "").strip()
            d_name = d_name or (gx_d or "").strip()
        except Exception:
            pass
    
    if not o_name or not d_name:
        return {"status": "error", "error": "missing_place_names",
                "origin_place": o_name or None, "dest_place": d_name or None}

    # Minimal POST body with computeAlternativeRoutes
    body = {
        "origin": {"address": o_name},
        "destination": {"address": d_name},
        "travelMode": travel_mode.upper(),
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
    }

    # Use the correct field mask
    field_mask = "routes.duration,routes.distanceMeters,routes.routeLabels,routes.polyline.encodedPolyline,routes.legs.startLocation,routes.legs.endLocation"

    try:
        resp = requests.post(
            ROUTES_ENDPOINT,
            params={"key": ROUTES_KEY},
            data=json.dumps(body),
            headers={
                "Content-Type": "application/json",
                "X-Goog-FieldMask": field_mask,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

    except requests.exceptions.RequestException as e:
        return {"status": "error", "error": f"routes_api_failed: {e}",
                "raw": str(e), "origin_place": o_name, "dest_place": d_name}

    # Parse every returned route
    routes_out: List[Dict[str, Any]] = []
    best_time = float('inf')
    default_duration = None
    all_points = []

    if not data.get("routes"):
        return {"status": "error", "error": "no_routes_found",
                "origin_place": o_name, "dest_place": d_name}

    for r in data["routes"]:
        duration_min = round(int(r["duration"][:-1]) / 60)
        poly = r["polyline"]["encodedPolyline"]
        label = r.get("routeLabels", ["DEFAULT_ROUTE"])[0]

        if label == "DEFAULT_ROUTE":
            default_duration = duration_min

        if duration_min < best_time:
            best_time = duration_min

        routes_out.append({
            "summary": label,
            "durationMin": duration_min,
            "trafficMin": duration_min,
            "distance_km": round(r["distanceMeters"] / 1000, 1),
            "polyline": poly,
        })

        for leg in r.get("legs", []):
            start_loc = leg.get("startLocation", {}).get("latLng", {})
            end_loc = leg.get("endLocation", {}).get("latLng", {})
            if start_loc:
                all_points.append({"lat": start_loc["latitude"], "lng": start_loc["longitude"]})
            if end_loc:
                all_points.append({"lat": end_loc["latitude"], "lng": end_loc["longitude"]})

    # Manually calculate bounds from start and end points of all legs
    if all_points:
        min_lat = min(p["lat"] for p in all_points)
        max_lat = max(p["lat"] for p in all_points)
        min_lon = min(p["lng"] for p in all_points)
        max_lon = max(p["lng"] for p in all_points)
        map_bounds = {"south": min_lat, "west": min_lon, "north": max_lat, "east": max_lon}
    else:
        map_bounds = None

    improvement = max(0, (default_duration or 0) - best_time)

    return {
        "status": "ok",
        "origin_place": o_name,
        "dest_place": d_name,
        "mode": travel_mode.lower(),
        "improvementMin": improvement,
        "map": {
            "kind": "directions",
            "routes": routes_out,
            "bounds": map_bounds,
        },
    }