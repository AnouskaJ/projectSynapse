"""
Nearby places and lockers tools
"""
import math
from typing import Dict, Any, List, Optional

from ..services.places import search_nearby, get_nearby_restaurants, _places_get, _places_post
from ..services.google_maps import geocode
from ..services.llm import llm
from ..utils.geo import coerce_point
from ..utils.jsonx import safe_json, strip_json_block
from ..logger import get_logger

log = get_logger(__name__)

# Category mappings
CATEGORY_TO_TYPES = {
    "mart": ["convenience_store", "supermarket"],
    "grocery": ["supermarket", "grocery_store"],
    "club": ["night_club"],
    "restaurant": ["restaurant"],
    "pharmacy": ["pharmacy"],
    "hospital": ["hospital"],
    "atm": ["atm"],
    "fuel": ["gas_station"],
    "locker": ["point_of_interest", "post_office", "storage", "convenience_store"],
}

CATEGORY_KEYWORDS = {
    "mart": "mart OR convenience store OR mini market",
    "grocery": "grocery OR supermarket",
    "club": "club OR night club",
    "restaurant": "restaurant",
    "pharmacy": "pharmacy medical store",
    "hospital": "hospital",
    "atm": "atm cash machine",
    "fuel": "fuel station OR petrol pump OR gas station",
    "locker": (
        "parcel locker OR smart locker OR package locker OR package pickup OR "
        "package pickup kiosk OR pickup drop-off point OR PUDO OR amazon locker "
        "OR parcel center OR self-service locker"
    ),
}

LOCKER_TYPES = ["post_office", "convenience_store"]

def _gemini_place_from_text(scenario: str) -> Optional[str]:
    """Extract ONE concise center place from free text"""
    prompt = f"""
    Extract ONE concise place name from the scenario that best represents the search center.
    Return STRICT JSON only:
    {{
    "place_name": "<single place or empty>"
    }}

    Rules:
    - Prefer the most specific, human-readable names (street + area, mall name, etc.).
    - Use human-readable names only (no coordinates/punctuation).

    Scenario:
    {scenario}
    """
    
    try:
        resp = llm.generate_content(prompt)
        data = safe_json(strip_json_block(getattr(resp, "text", "") or "{}"), {}) or {}
        name = (data.get("place_name") or "").strip()
        return name or None
    except Exception:
        return None

def _gemini_category_from_text(scenario: str) -> Optional[str]:
    """Map text to a coarse category used for Places searches"""
    prompt = f"""
    From the scenario, pick ONE category keyword from this list:
    ["mart","club","restaurant","pharmacy","hospital","atm","fuel","grocery"]
    Return STRICT JSON only:
    {{"category":"<one of the list or empty>"}}

    Scenario:
    {scenario}
    """
    
    try:
        resp = llm.generate_content(prompt)
        data = safe_json(strip_json_block(getattr(resp, "text", "") or "{}"), {}) or {}
        cat = (data.get("category") or "").strip().lower()
        return cat or None
    except Exception:
        return None

def tool_places_search_nearby(
    lat_any: Any = None,
    lon_any: Any = None,
    radius_m: int = 2000,
    keyword: Optional[str] = None,
    included_types: Optional[List[str]] = None,
    place_name: Optional[str] = None,
    scenario_text: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Find up to 5 nearby places relevant to a field/vertical."""
    
    # --- Center selection ---
    center = None

    if place_name and str(place_name).strip():
        pt = geocode(place_name.strip())
        if pt:
            center = [pt[0], pt[1]]

    if center is None and scenario_text and str(scenario_text).strip():
        maybe_center_name = _gemini_place_from_text(scenario_text.strip())
        if maybe_center_name:
            pt = geocode(maybe_center_name)
            if pt:
                center = [pt[0], pt[1]]

    if center is None:
        if isinstance(lat_any, (int, float)) and isinstance(lon_any, (int, float)):
            center = [float(lat_any), float(lon_any)]
        else:
            center = coerce_point([lat_any, lon_any]) if (lat_any is not None or lon_any is not None) else None

    if not center:
        return {"error": "invalid_center"}

    # --- Category selection ---
    cat = (category or "").strip().lower() if category else None
    if not cat and scenario_text:
        cat = _gemini_category_from_text(scenario_text)

    types = included_types or (CATEGORY_TO_TYPES.get(cat) if cat else None)
    kw = keyword or (CATEGORY_KEYWORDS.get(cat) if cat else None)

    # If we still have neither types nor keyword, default to a broad keyword
    if not types and not kw:
        kw = "point of interest"

    lat, lon = center
    
    try:
        data = search_nearby(lat, lon, radius_m, kw, types)
        raw = data.get("places") or []

        # Keep top 5; prefer places with rating & more reviews
        def _score(p):
            rating = p.get("rating") or 0
            cnt = p.get("userRatingCount") or 0
            return (rating, math.log(cnt + 1))

        raw.sort(key=_score, reverse=True)
        places = raw[:5]

        out = []
        for p in places:
            out.append({
                "id": p.get("id"),
                "name": (p.get("displayName") or {}).get("text"),
                "address": p.get("formattedAddress"),
                "phone": p.get("nationalPhoneNumber"),
                "website": p.get("websiteUri"),
                "rating": p.get("rating"),
                "userRatingCount": p.get("userRatingCount"),
                "openNow": (((p.get("currentOpeningHours") or {}).get("openNow"))
                            if p.get("currentOpeningHours") else None),
            })
        
        return {
            "count": len(out),
            "places": out,
            "center": {"lat": lat, "lon": lon},
            "resolved_category": cat,
            "used_types": types,
            "used_keyword": kw,
        }
    except Exception as e:
        return {"error": f"places_nearby_failure:{str(e)}"}

def tool_find_nearby_locker(place_name: str,
                            radius_m: Optional[int] = None) -> Dict[str, Any]:
    """
    Find up to 5 parcel-friendly locations near `place_name`, using only the
    primary place types (no keyword, radius optional).
    """

    if not place_name or not str(place_name).strip():
        return {"status": "error", "error": "missing_place_name", "lockers": []}

    # 1 ▸ geocode ---------------------------------------------------------
    center = geocode(place_name.strip())
    if not center:
        return {"status": "error", "error": "geocode_failed", "lockers": []}
    lat, lon = center

    # 2 ▸ build Places request body --------------------------------------
    body = {
        "includedPrimaryTypes": LOCKER_TYPES,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius_m or 1500),  # Use a default if not provided
            }
        }
    }
    field_mask = ",".join([
        "places.id", "places.displayName", "places.formattedAddress",
        "places.rating", "places.userRatingCount",
        "places.currentOpeningHours.openNow", "places.location" # <-- Added places.location
    ])

    try:
        data = _places_post("places:searchNearby", body, field_mask)
        places = data.get("places", [])

        # 3 ▸ rank & trim -------------------------------------------------
        places.sort(
            key=lambda p: (
                p.get("rating", 0),
                math.log((p.get("userRatingCount") or 0) + 1)
            ),
            reverse=True,
        )
        top5 = places[:5]

        lockers = [{
            "id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text"),
            "address": p.get("formattedAddress"),
            "rating": p.get("rating"),
            "user_ratings_total": p.get("userRatingCount"),
            "open_now": (p.get("currentOpeningHours") or {}).get("openNow")
                         if p.get("currentOpeningHours") else None,
            "lat": (p.get("location") or {}).get("latitude"), # <-- Added lat
            "lon": (p.get("location") or {}).get("longitude"), # <-- Added lon
        } for p in top5]

        return {
            "status": "ok",
            "count": len(lockers),
            "lockers": lockers,
            "center": {"lat": lat, "lon": lon},
            "query_place": place_name,
            "used_radius_m": radius_m,
        }

    except Exception as e:
        log.error(f"[find_nearby_locker] failure: {e}")
        return {"status": "error", "error": str(e), "lockers": []}
 
def tool_get_nearby_merchants(lat: float, lon: float, radius_m: int = 2000) -> Dict[str, Any]:
    """Use Google Places to get up to 5 restaurants near given coords."""
    return get_nearby_restaurants(lat, lon, radius_m)

def tool_mark_as_placed(locker_id: str, order_id: str) -> Dict[str, Any]:
    """Mark the order as placed in the selected locker."""
    # TODO: integrate with real locker API
    log.info(f"[locker] placed order {order_id} into locker {locker_id}")
    return {"status": "ok", "order_id": order_id, "locker_id": locker_id}