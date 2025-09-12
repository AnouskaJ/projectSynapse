"""
Google Places API services
"""
from typing import Dict, Any, List, Optional
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

def _places_post(path: str, body: dict, field_mask: str) -> dict:
    """POST request to Places API"""
    url = f"https://places.googleapis.com/v1/{path}"
    return http_post(url, body, headers=_gm_headers(field_mask))

def _places_get(path: str, field_mask: str) -> dict:
    """GET request to Places API"""
    url = f"https://places.googleapis.com/v1/{path}"
    return http_get(url, headers=_gm_headers(field_mask))

def search_nearby(lat: float, lon: float, radius_m: int = 2000, 
                  keyword: Optional[str] = None, 
                  included_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """Search for places near coordinates"""
    body = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius_m),
            }
        }
    }
    
    if keyword:
        body["keyword"] = keyword
    if included_types:
        body["includedPrimaryTypes"] = included_types

    field_mask = ",".join([
        "places.id","places.displayName","places.formattedAddress",
        "places.nationalPhoneNumber","places.websiteUri","places.rating",
        "places.userRatingCount","places.currentOpeningHours.openNow",
    ])

    try:
        data = _places_post("places:searchNearby", body, field_mask)
        return data
    except Exception as e:
        log.error(f"[search_nearby] failure: {e}")
        return {"error": str(e), "places": []}

def get_place_details(place_id: str) -> Dict[str, Any]:
    """Get detailed information about a place"""
    field_mask = ",".join([
        "id","displayName","formattedAddress","nationalPhoneNumber","websiteUri",
        "rating","userRatingCount","currentOpeningHours.openNow","priceLevel"
    ])
    
    try:
        data = _places_get(f"places/{place_id}", field_mask)
        p = data or {}
        return {
            "id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text"),
            "address": p.get("formattedAddress"),
            "phone": p.get("nationalPhoneNumber"),
            "website": p.get("websiteUri"),
            "rating": p.get("rating"),
            "userRatingCount": p.get("userRatingCount"),
            "openNow": (((p.get("currentOpeningHours") or {}).get("openNow")) 
                       if p.get("currentOpeningHours") else None),
            "priceLevel": p.get("priceLevel")
        }
    except Exception as e:
        return {"error": f"place_details_failure:{str(e)}"}

def get_nearby_restaurants(lat: float, lon: float, radius_m: int = 2000) -> Dict[str, Any]:
    """Get nearby restaurants using legacy Places API"""
    import requests
    
    try:
        places_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat},{lon}",
            "radius": radius_m,
            "type": "restaurant",
            "key": GOOGLE_MAPS_API_KEY,
        }
        resp = requests.get(places_url, params=params, timeout=15).json()

        results = resp.get("results", [])
        merchants = []
        for p in results[:5]:
            loc = p["geometry"]["location"]
            merchants.append({
                "id": p["place_id"],
                "name": p["name"],
                "address": p["vicinity"],
                "rating": p.get("rating"),
                "user_ratings_total": p.get("user_ratings_total"),
                "lat": loc["lat"],
                "lng": loc["lng"], 
            })

        return {"count": len(merchants), "merchants": merchants}

    except Exception as e:
        return {"count": 0, "merchants": [], "error": str(e)}