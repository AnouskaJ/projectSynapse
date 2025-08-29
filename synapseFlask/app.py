import os, re, json, time, math, traceback, logging
from typing import Any, Dict, Iterable, List, Optional, Tuple
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# ----------------------------- LOGGING --------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("synapse")

# ----------------------------- CONFIG LOADING --------------------------
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
if not os.path.exists(CONFIG_FILE):
    raise RuntimeError("Missing config.json file with API keys.")

with open(CONFIG_FILE, "r") as f:
    cfg = json.load(f)

def get_cfg(key: str, default: str = ""):
    return os.getenv(key, cfg.get(key, default))

# ----------------------------- CONFIG ---------------------------------
GOOGLE_MAPS_API_KEY = get_cfg("GOOGLE_MAPS_API_KEY", "").strip()
GEMINI_API_KEY      = get_cfg("GEMINI_API_KEY", "").strip()
GEMINI_MODEL        = get_cfg("GEMINI_MODEL", "gemini-2.0-flash")

FIREBASE_PROJECT_ID   = get_cfg("FIREBASE_PROJECT_ID", "")
SERVICE_ACCOUNT_FILE  = get_cfg("GOOGLE_APPLICATION_CREDENTIALS", "")

MAX_STEPS            = int(get_cfg("MAX_STEPS", "5"))
MAX_SECONDS          = int(get_cfg("MAX_SECONDS", "120"))
STREAM_DELAY         = float(get_cfg("STREAM_DELAY", "0.10"))
BASELINE_SPEED_KMPH  = float(get_cfg("BASELINE_SPEED_KMPH", "40.0"))

if not GOOGLE_MAPS_API_KEY:
    raise RuntimeError("GOOGLE_MAPS_API_KEY missing in config.json or env")

# ----------------------------- LLM (Gemini) ----------------------------
import google.generativeai as genai
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing in config.json or env")
genai.configure(api_key=GEMINI_API_KEY)
_llm = genai.GenerativeModel(GEMINI_MODEL)

# ----------------------------- GOOGLE AUTH (FCM v1) --------------------
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GARequest
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

def _fcm_access_token() -> str:
    """
    Generate OAuth2 access token using the service account JSON for FCM v1.
    """
    if not SERVICE_ACCOUNT_FILE or not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS file not found for FCM.")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    creds.refresh(GARequest())
    return creds.token

# ----------------------------- HTTP helpers ----------------------------
def http_get(url: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None, timeout: float = 20.0):
    r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def http_post(url: str, json_body: Dict[str, Any], headers: Dict[str, str], timeout: float = 25.0):
    r = requests.post(url, json=json_body, headers=headers, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"ok": True, "text": r.text}

# ----------------------------- UTIL -----------------------------------
def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def sse(data: Any) -> str:
    """
    Server-Sent Events line. Streams STRICT JSON step-by-step.
    """
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
    return f"data: {payload}\n\n"

def strip_json_block(text: str) -> str:
    """
    Return the JSON payload when the model replies in a fenced ```json block.
    Falls back to the original text if no fences are found.
    """
    t = (text or "").strip()
    if "```" in t:
        parts = t.split("```")
        if len(parts) >= 3:
            block = parts[1].strip()
            # If it starts with 'json', drop that first line and return the rest
            if block.lower().startswith("json"):
                block = block.split("\n", 1)[1] if "\n" in block else ""
            return block
    return t
def safe_json(text: str, default: Any = None) -> Any:
    """
    Robust JSON parse with a second-chance object extraction.
    """
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return default

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Straight-line distance in kilometers.
    """
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

# -------------------------- HINT EXTRACTORS ---------------------------
HINT_RE_ORIGIN = re.compile(r"origin\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)
HINT_RE_DEST   = re.compile(r"dest\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)
HINT_RE_ORIGIN_TEXT = re.compile(r"(?:^|[\s,;])origin(?:\s*[:=])\s*([^\n]+)", re.I)
HINT_RE_DEST_TEXT   = re.compile(r"(?:^|[\s,;])dest(?:\s*[:=])\s*([^\n]+)", re.I)
HINT_RE_FROM_TO     = re.compile(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:[,.]|$)", re.I)

def extract_hints(scenario: str, driver_token: Optional[str], passenger_token: Optional[str]) -> Dict[str, Any]:
    """
    Pull out coordinates, place names, and device tokens from a scenario string.
    """
    hints: Dict[str, Any] = {}
    m1 = HINT_RE_ORIGIN.search(scenario); m2 = HINT_RE_DEST.search(scenario)
    if m1 and m2:
        hints["origin"] = [float(m1.group(1)), float(m1.group(2))]
        hints["dest"]   = [float(m2.group(1)), float(m2.group(2))]
    mt1 = HINT_RE_ORIGIN_TEXT.search(scenario); mt2 = HINT_RE_DEST_TEXT.search(scenario)
    if mt1: hints["origin_place"] = mt1.group(1).strip()
    if mt2: hints["dest_place"]   = mt2.group(1).strip()
    mt3 = HINT_RE_FROM_TO.search(scenario)
    if mt3:
        hints.setdefault("origin_place", mt3.group(1).strip())
        hints.setdefault("dest_place",   mt3.group(2).strip())
    if driver_token: hints["driver_token"] = driver_token
    if passenger_token: hints["passenger_token"] = passenger_token
    return hints

# -------------------------- GOOGLE HELPERS ----------------------------
def _gm_headers(field_mask: Optional[str] = None) -> Dict[str, str]:
    """
    Default headers for Google services that use API key in headers.
    """
    h = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY}
    if field_mask:
        h["X-Goog-FieldMask"] = field_mask
    return h

def _routes_post(path: str, body: dict, field_mask: str) -> dict:
    """
    POST wrapper for Routes API.
    """
    url = f"https://routes.googleapis.com/{path}"
    return http_post(url, body, headers=_gm_headers(field_mask))

def _places_post(path: str, body: dict, field_mask: str) -> dict:
    """
    POST wrapper for Places API (New).
    """
    url = f"https://places.googleapis.com/v1/{path}"
    return http_post(url, body, headers=_gm_headers(field_mask))

def _places_get(path: str, field_mask: str) -> dict:
    """
    GET wrapper for Places Details (New).
    """
    url = f"https://places.googleapis.com/v1/{path}"
    return http_get(url, headers=_gm_headers(field_mask))

def _geocode(text: str) -> Optional[tuple[float, float]]:
    """
    Geocode a free-text address/place via Geocoding API.

    Returns: (lat, lon) or None if not found.
    """
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

# ----------------------------- REAL TOOLS ------------------------------
def tool_geocode_place(query: str) -> Dict[str, Any]:
    """
    Resolve textual place/address to coordinates using Geocoding API.
    """
    pt = _geocode(query)
    if not pt:
        return {"found": False}
    lat, lon = pt
    return {"found": True, "lat": lat, "lon": lon, "query": query}

def _seconds_to_minutes_str_dur(sec_str: str) -> float:
    """
    Convert Routes API '123s'/'1234s' to minutes (float).
    """
    try:
        s = float(sec_str.rstrip("s"))
        return round(s / 60.0, 1)
    except Exception:
        return 0.0

def tool_check_traffic(origin: List[float], dest: List[float]) -> Dict[str, Any]:
    """
    Traffic-aware ETA and distance between origin and dest using Routes API.
    """
    if not origin or not dest or len(origin) != 2 or len(dest) != 2:
        return {"error": "invalid_coordinates"}

    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {"location": {"latLng": {"latitude": dest[0], "longitude": dest[1]}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "departureTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "computeAlternativeRoutes": False
    }
    field_mask = "routes.duration,routes.distanceMeters"
    try:
        data = _routes_post("directions/v2:computeRoutes", body, field_mask)
        routes = data.get("routes") or []
        if not routes:
            raise ValueError("no_route")
        r0 = routes[0]
        eta_min = _seconds_to_minutes_str_dur(r0.get("duration", "0s"))
        dist_km = (float(r0.get("distanceMeters", 0.0)) or 0.0) / 1000.0
        baseline_min = (dist_km / BASELINE_SPEED_KMPH) * 60.0 if dist_km else 0.0
        delay_min = max(0.0, round(eta_min - baseline_min, 1))
        return {"etaMin": eta_min, "delayMin": delay_min, "distanceKm": round(dist_km, 2)}
    except Exception as e:
        # fallback: haversine
        dist_km = round(haversine_km(origin[0], origin[1], dest[0], dest[1]), 3)
        eta_min = round((dist_km / BASELINE_SPEED_KMPH) * 60.0, 1) if dist_km else 0.0
        return {"approximate": True, "reason": f"routes_failure:{str(e)}",
                "distanceKm": round(dist_km, 2), "etaMin": eta_min, "delayMin": 0.0}

def tool_calculate_alternative_route(origin: List[float], dest: List[float]) -> Dict[str, Any]:
    """
    Return up to 3 candidate routes and the best ETA improvement using Routes API.
    """
    if not origin or not dest or len(origin) != 2 or len(dest) != 2:
        return {"error": "invalid_coordinates"}

    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {"location": {"latLng": {"latitude": dest[0], "longitude": dest[1]}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "departureTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "computeAlternativeRoutes": True
    }
    field_mask = "routes.duration,routes.distanceMeters"
    try:
        data = _routes_post("directions/v2:computeRoutes", body, field_mask)
        routes = data.get("routes") or []
        if not routes:
            raise ValueError("no_routes")
        out = []
        for r in routes[:3]:
            eta_min = _seconds_to_minutes_str_dur(r.get("duration", "0s"))
            dist_km = (float(r.get("distanceMeters", 0.0)) or 0.0) / 1000.0
            out.append({"etaMin": eta_min, "distanceKm": round(dist_km, 2)})
        base = out[0]["etaMin"]
        best = min(out, key=lambda x: x["etaMin"])
        improvement = max(0.0, round(base - best["etaMin"], 1))
        return {"routes": out, "best": best, "improvementMin": improvement}
    except Exception as e:
        dist_km = round(haversine_km(origin[0], origin[1], dest[0], dest[1]), 3)
        eta_min = round((dist_km / 30.0) * 60.0, 1) if dist_km else 0.0
        return {"routes": [{"etaMin": eta_min, "distanceKm": round(dist_km, 2)}],
                "best": {"etaMin": eta_min, "distanceKm": round(dist_km, 2)},
                "improvementMin": 0.0, "approximate": True,
                "reason": f"routes_failure:{str(e)}"}

def tool_compute_route_matrix(origins: List[List[float]], destinations: List[List[float]]) -> Dict[str, Any]:
    """
    Compute a distance/ETA matrix between multiple origins and destinations (Routes API).
    """
    if not origins or not destinations:
        return {"error": "missing_origins_or_destinations"}

    def wp(pt):
        return {"waypoint": {"location": {"latLng": {"latitude": pt[0], "longitude": pt[1]}}}}

    body = {
        "origins": [wp(o) for o in origins],
        "destinations": [wp(d) for d in destinations],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE"
    }
    field_mask = "originIndex,destinationIndex,duration,distanceMeters,status,condition"
    url_path = "distanceMatrix/v2:computeRouteMatrix"
    try:
        data = _routes_post(url_path, body, field_mask)
        out = []
        for el in data:
            eta_min = _seconds_to_minutes_str_dur(el.get("duration", "0s"))
            dist_km = (float(el.get("distanceMeters", 0.0)) or 0.0) / 1000.0
            out.append({
                "originIndex": el.get("originIndex", 0),
                "destinationIndex": el.get("destinationIndex", 0),
                "etaMin": eta_min,
                "distanceKm": round(dist_km, 2),
                "condition": el.get("condition", "ROUTE_EXISTS"),
                "status": el.get("status", {})
            })
        return {"elements": out}
    except Exception as e:
        return {"error": f"route_matrix_failure:{str(e)}"}

def tool_check_weather(lat: float, lon: float) -> Dict[str, Any]:
    """
    Current weather from Google Weather API.
    """
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

def tool_air_quality(lat: float, lon: float) -> Dict[str, Any]:
    """
    Current air quality from Google Air Quality API.
    """
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

def tool_pollen_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """
    Pollen forecast via Google Pollen API.
    """
    url = "https://pollen.googleapis.com/v1/forecast:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return {"raw": data}
    except Exception as e:
        return {"error": f"pollen_failure:{str(e)}"}

def tool_places_search_nearby(lat: float, lon: float, radius_m: int = 2000, keyword: Optional[str] = None, included_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Nearby Search (Places New) – find places around a location.
    """
    body = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius_m)
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
        places = data.get("places") or []
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
                "openNow": (((p.get("currentOpeningHours") or {}).get("openNow")) if p.get("currentOpeningHours") else None)
            })
        return {"count": len(out), "places": out}
    except Exception as e:
        return {"error": f"places_nearby_failure:{str(e)}"}

def tool_place_details(place_id: str) -> Dict[str, Any]:
    """
    Place Details (New).
    """
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
            "openNow": (((p.get("currentOpeningHours") or {}).get("openNow")) if p.get("currentOpeningHours") else None),
            "priceLevel": p.get("priceLevel")
        }
    except Exception as e:
        return {"error": f"place_details_failure:{str(e)}"}

def tool_roads_snap(points: List[List[float]], interpolate: bool = True) -> Dict[str, Any]:
    """
    Snap a sequence of GPS points to the road network (Roads API).
    """
    if not points or any(len(p) != 2 for p in points):
        return {"error": "invalid_points"}

    path = "|".join([f"{p[0]},{p[1]}" for p in points])
    url = "https://roads.googleapis.com/v1/snapToRoads"
    params = {"path": path, "interpolate": "true" if interpolate else "false", "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return {"snappedPoints": data.get("snappedPoints", [])}
    except Exception as e:
        return {"error": f"roads_failure:{str(e)}"}

def tool_time_zone(lat: float, lon: float, timestamp: Optional[int] = None) -> Dict[str, Any]:
    """
    Time Zone for a lat/lon at a given timestamp (default: now).
    """
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
            "status": data.get("status")
        }
    except Exception as e:
        return {"error": f"time_zone_failure:{str(e)}"}

# ------------------------- NOTIFICATIONS (FCM v1) ---------------------
def _fcm_v1_send(token: str, title: str, body: str, data: Optional[dict] = None) -> Dict[str, Any]:
    """
    Send a push message via Firebase Cloud Messaging (HTTP v1).
    """
    if not token:
        return {"delivered": False, "reason": "missing_device_token"}
    access_token = _fcm_access_token()
    url = f"https://fcm.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/messages:send"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    message = {"message": {"token": token, "notification": {"title": title, "body": body}}}
    if data:
        message["message"]["data"] = data
    log.info(f"[tool_fcm_send] sending to token=present title='{title}'")
    try:
        res = http_post(url, message, headers, timeout=10)
        ok = "name" in res
        return {"delivered": bool(ok), "fcmResponse": res}
    except Exception as e:
        return {"delivered": False, "error": str(e)}

def tool_notify_customer(fcm_token: Optional[str], message: str, voucher: bool=False, title: str="Order Update") -> Dict[str, Any]:
    """
    Notify a customer device via FCM v1. (Real Google API call.)
    """
    return _fcm_v1_send(fcm_token or "", title, message, {"voucher": json.dumps(bool(voucher))})

def tool_notify_passenger_and_driver(driver_token: Optional[str], passenger_token: Optional[str], message: str) -> Dict[str, Any]:
    """
    Notify both driver and passenger devices via FCM v1.
    """
    d = _fcm_v1_send(driver_token or "", "Route Update", message) if driver_token else {"delivered": False}
    p = _fcm_v1_send(passenger_token or "", "Route Update", message) if passenger_token else {"delivered": False}
    return {"driverDelivered": d.get("delivered"), "passengerDelivered": p.get("delivered")}

# ----------------------------- ASSERTIONS ------------------------------
def check_assertion(assertion: Optional[str], observation: Dict[str, Any]) -> bool:
    """
    Simple assertion DSL to auto-evaluate tool outcomes.
    """
    if not assertion: return True
    a = assertion.strip().lower().replace(" ", "")

    if "len(routes)>=1" in a or "routes>=1" in a:
        routes = observation.get("routes")
        return isinstance(routes, list) and len(routes) >= 1

    if "customerack==true" in a:  return bool(observation.get("customerAck"))
    if "delivered==true" in a:    return bool(observation.get("delivered")) or bool(observation.get("driverDelivered")) or bool(observation.get("passengerDelivered"))
    if "approved==true" in a:     return bool(observation.get("approved"))
    if "improvementmin>0" in a:   return isinstance(observation.get("improvementMin"), (int,float)) and observation["improvementMin"] > 0
    if "etadeltamin<=0" in a:     return isinstance(observation.get("etaDeltaMin"), (int,float)) and observation["etaDeltaMin"] <= 0
    if "candidates>0" in a or "count>0" in a:
        v = observation.get("count") or observation.get("candidates")
        if isinstance(v, list): return len(v) > 0
        if isinstance(v, (int,float)): return v > 0
    if "delaymin>=0" in a:        return isinstance(observation.get("delayMin"), (int,float)) and observation["delayMin"] >= 0
    if "hazard==false" in a:      return not bool(observation.get("hazard"))
    if "found==true" in a:        return bool(observation.get("found"))
    if "response!=none" in a:     return observation.get("response") is not None
    if "photos>0" in a:
        v = observation.get("photos")
        return isinstance(v, (int, float)) and v > 0
    if "==" in a and all(op not in a for op in (">", "<", "!=")):
        k, val = a.split("==", 1)
        return str(observation.get(k)) == val
    return True

# ----------------------------- PROMPTS --------------------------------
KIND_LABELS = ["merchant_capacity","recipient_unavailable","traffic","damage_dispute","payment_issue","address_issue","weather","safety","other","unknown"]

CLASSIFY_PROMPT = """
You are Synapse, an expert last-mile logistics coordinator.

Your task is to classify the given scenario into:
- kind → one of {labels}
- severity → one of ["low", "med", "high"]
- uncertainty → a float between 0 and 1 (0 = fully certain, 1 = very uncertain)

Rules:
- Always choose the closest matching kind.
- traffic → jams, accidents, closures, congestion, rerouting
- If the scenario describes a normal trip request with an origin and destination (no disruption is stated), classify it as: traffic
- merchant_capacity → restaurant/kitchen delays, prep times, backlog
- recipient_unavailable → not home, unreachable, refuses, wrong timing
- damage_dispute → spills, broken seals, packaging fault, who’s at fault
- payment_issue → payment failed/pending/need re-auth
- address_issue → wrong/missing address, pin mismatch, navigation issues
- weather → rain/thunderstorm/flood/snow/heat affecting flow
- safety → crash, unsafe area, harassment, emergency
- other → none of the above; use "unknown" only if text is incomprehensible

Output STRICT JSON only (no prose), e.g.:
{{
  "kind": "traffic",
  "severity": "high",
  "uncertainty": 0.2
}}

Scenario:
{scenario}
"""


SCHEMA_SPEC = {
    "type":"object",
    "properties":{
        "intent":{"type":"string"},
        "tool":{"type":"string"},
        "params":{"type":"object"},
        "assertion":{"type":["string","null"]},
        "finish_reason":{"type":"string","enum":["continue","final","escalate"]},
        "final_message":{"type":["string","null"]}
    },
    "required":["intent","tool","params","finish_reason"]
}

SYSTEM_ROLE_TMPL = (
    "You are Synapse, an expert logistics coordinator. Resolve disruptions in at most "
    "{max_steps} steps and under {max_seconds} seconds. Use only provided tools. "
    "Each step must be strict JSON per schema."
)

def tools_manifest_text() -> str:
    return json.dumps([
        {"name":"check_traffic","description":"Traffic-aware ETA/distance via Routes API.","schema":{"origin":"[lat,lon]","dest":"[lat,lon]"}},
        {"name":"calculate_alternative_route","description":"Alternative routes & best improvement via Routes API.","schema":{"origin":"[lat,lon]","dest":"[lat,lon]"}},
        {"name":"compute_route_matrix","description":"Distance/ETA matrix for multiple origins/destinations.","schema":{"origins":"[[lat,lon],...]","destinations":"[[lat,lon],...]"}},
        {"name":"check_weather","description":"Current weather via Google Weather API.","schema":{"lat":"float","lon":"float"}},
        {"name":"air_quality","description":"Current air quality via Air Quality API.","schema":{"lat":"float","lon":"float"}},
        {"name":"pollen_forecast","description":"Pollen forecast via Pollen API.","schema":{"lat":"float","lon":"float"}},
        {"name":"time_zone","description":"Time zone for a lat/lon.","schema":{"lat":"float","lon":"float","timestamp":"int?"}},
        {"name":"places_search_nearby","description":"Nearby places (New) around a point.","schema":{"lat":"float","lon":"float","radius_m":"int","keyword":"str?","included_types":"list[str]?"}},
        {"name":"place_details","description":"Place details (New).","schema":{"place_id":"str"}},
        {"name":"roads_snap","description":"Snap GPS points to roads (Roads API).","schema":{"points":"[[lat,lon],...]","interpolate":"bool?"}},
        {"name":"geocode_place","description":"Geocode a place/address to coordinates.","schema":{"query":"str"}},
        {"name":"notify_customer","description":"Push notify customer via FCM v1.","schema":{"fcm_token":"str","message":"str","voucher":"bool","title":"str"}},
        {"name":"notify_passenger_and_driver","description":"Push notify both via FCM v1.","schema":{"driver_token":"str","passenger_token":"str","message":"str"}}
    ], ensure_ascii=False)

def build_plan_prompt(scenario: str, cls: Dict[str, Any], so_far: List[Dict[str, Any]]) -> str:
    system_role = SYSTEM_ROLE_TMPL.format(max_steps=MAX_STEPS, max_seconds=MAX_SECONDS)
    tools_text = tools_manifest_text()
    so_far_json = json.dumps(so_far, ensure_ascii=False)
    schema_json = json.dumps(SCHEMA_SPEC, ensure_ascii=False)

    # Assertion contract the model MUST follow
    assertion_contract = """
Allowed assertion grammar (choose exactly ONE that matches your tool):
- For geocode_place:         "found==true"
- For check_traffic:         "delayMin>=0"
- For calculate_alternative_route: "improvementMin>=0" (use >0 if you expect a win)
- For compute_route_matrix:  "count>0" or "elements>0"
- For check_weather:         "hazard==false" OR "tempC!=none" (prefer hazard==false)
- For air_quality:           "found==true" (treat presence of an index as found)
- For pollen_forecast:       "found==true" (treat presence of a forecast as found)
- For time_zone:             "found==true" (treat presence of timeZoneId as found)
- For places_search_nearby:  "count>0"
- For place_details:         "found==true"
- For roads_snap:            "count>0" (count snappedPoints)
- For notify_customer:       "delivered==true"
- For notify_passenger_and_driver: "delivered==true"

NEVER invent custom assertions like "lat != null", "place_id != null", etc.
"""

    return (
        f"System:\n{system_role}\n\n"
        f"Scenario: {scenario}\n"
        f"Classification: kind={cls.get('kind')}, severity={cls.get('severity')}, uncertainty={cls.get('uncertainty')}\n"
        f"Steps so far: {so_far_json}\n"
        f"Available tools: {tools_text}\n\n"
        "Pick the NEXT step only.\n"
        "Rules:\n"
        "- Use a tool when applicable; only set tool='none' to ask a clarification question.\n"
        "- Parameters must match each tool schema exactly.\n"
        f"- Assertions MUST follow this contract:\n{assertion_contract}\n"
        "- If the goal is achieved, set finish_reason='final' and provide final_message.\n"
        "- Return STRICT JSON ONLY that matches this JSON Schema:\n"
        f"{schema_json}"
    )

EXAMPLES = [
  {"intent":"check congestion","tool":"check_traffic","params":{"origin":[1.29,103.85],"dest":[1.35,103.87]},"assertion":"delayMin>=0","finish_reason":"continue"},
  {"intent":"reroute","tool":"calculate_alternative_route","params":{"origin":[1.29,103.85],"dest":[1.35,103.87]},"assertion":"improvementMin>0","finish_reason":"continue"},
  {"intent":"inform both","tool":"notify_passenger_and_driver","params":{"message":"Rerouted; new ETA shared."},"assertion":"delivered==true","finish_reason":"final","final_message":"Reroute applied; notifications sent."},
  {"intent":"evaluate alternatives","tool":"calculate_alternative_route","params":{"origin":[1.29,103.85],"dest":[1.35,103.87]},"assertion":"improvementMin>=0","finish_reason":"final","final_message":"No faster route available; keep current route and monitor."}
]

# ----------------------------- AGENT ----------------------------------
class SynapseAgent:
    """
    Planner-executor loop with Gemini for planning and Google APIs as tools.
    Streams SSE events: classification → steps → summary.
    """
    def __init__(self, llm):
        self.llm = llm

    def classify(self, scenario: str) -> Dict[str, Any]:
        # Make labels JSON-safe for the prompt
        prompt = CLASSIFY_PROMPT.format(labels=json.dumps(KIND_LABELS), scenario=scenario)
        log.info(f"[classify] Prompt being sent:\n{prompt}...")  # log first 500 chars of prompt

        try:
            resp = self.llm.generate_content(prompt)
            resp_text = getattr(resp, "text", "") or "{}"
            log.info(f"[classify] Raw Gemini response:\n{resp_text}")
            parsed = safe_json(strip_json_block(resp_text), {}) or {}
            log.info(f"[classify] Parsed JSON: {parsed}")
        except Exception as e:
            log.error(f"[gemini_error:classify] {e}")
            parsed = {}

        # Extract kind
        raw_kind = (parsed.get("kind") or "").lower()
        if raw_kind not in [k.lower() for k in KIND_LABELS]:
            log.warning(f"[classify] Model returned unknown kind: '{raw_kind}' → defaulting to 'unknown'")
            kind = "unknown"
        else:
            kind = raw_kind

        severity = parsed.get("severity", "med")
        try:
            uncertainty = float(parsed.get("uncertainty", 0.3))
        except Exception:
            uncertainty = 0.3

        result = {"kind": kind, "severity": severity, "uncertainty": uncertainty}
        log.info(f"[classify] Final classification: {result}")
        return result

    def propose_next(self, scenario: str, cls: Dict[str, Any], so_far: List[Dict[str, Any]]) -> Dict[str, Any]:
            prompt = build_plan_prompt(scenario, cls, so_far)
            try:
                resp = self.llm.generate_content(prompt)
                raw = getattr(resp, "text", "") or "{}"
                parsed = safe_json(strip_json_block(raw), {}) or {}
            except Exception as e:
                log.error(f"[gemini_error:propose_next] {e}")
                parsed = {}
            if not parsed or "tool" not in parsed:
                print("\n[PLAN RAW OUTPUT]\n", locals().get("raw", "<no_raw>"), "\n")
            return parsed or {}

    def execute_tool(self, name: str, params: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
        meta = TOOLS.get(name)
        if not meta:
            return {"error": f"unknown tool: {name}"}, "unknown"
        fn = meta["fn"]
        try:
            obs = fn(**{k: v for k, v in params.items()})
            return obs, None
        except Exception as e:
            log.error(f"[tool_error] {name}: {e}")
            return {"error": str(e)}, "exception"

    def _policy_next(self, kind: str, steps_done: int, hints: Dict[str, Any]) -> Optional[tuple]:
        """
        Deterministic rails to ensure progress when the model punts.
        """
        if kind == "traffic":
            origin = hints.get("origin"); dest = hints.get("dest")
            if not origin or not dest:
                if steps_done == 0:
                    return ("clarify","none",{"question":"Provide origin/dest as 'origin=lat,lon dest=lat,lon' or place names."}, None, "continue", None)
                return None
            if steps_done == 0:
                return ("check congestion","check_traffic",{"origin":origin,"dest":dest},"delayMin>=0","continue",None)
            if steps_done == 1:
                return ("reroute","calculate_alternative_route",{"origin":origin,"dest":dest},"improvementMin>0","continue",None)
            if steps_done == 2:
                msg = "Rerouted to faster path; updated ETA shared."
                return ("inform both","notify_passenger_and_driver",
                        {"driver_token": hints.get("driver_token"),
                         "passenger_token": hints.get("passenger_token"),
                         "message": msg},
                        "delivered==true","final","Reroute applied; passengers notified.")
            return None

        if kind == "merchant_capacity":
            if steps_done == 0:
                latlon = hints.get("origin") or hints.get("dest")
                if latlon:
                    return ("suggest alt merchant","places_search_nearby",
                            {"lat":latlon[0],"lon":latlon[1],"radius_m":2000,"keyword":"restaurant"},
                            "count>0","continue",None)
            if steps_done == 1:
                return ("notify","notify_customer",
                        {"fcm_token": hints.get("customer_token") or hints.get("passenger_token"),
                         "message":"Delays at current merchant. Suggested alternatives nearby.",
                         "voucher": True, "title":"Delay notice"},
                        "delivered==true","final","Customer informed; alternatives shared.")
            return None

        if kind == "recipient_unavailable":
            if steps_done == 0:
                return ("notify recipient","notify_customer",
                        {"fcm_token": hints.get("passenger_token"), "message":"Driver is at your address. Should we leave with concierge or neighbor?", "voucher": False, "title":"Delivery attempt"},
                        "delivered==true","continue",None)
            if steps_done == 1:
                return ("safe drop-off advisory","none",{}, None,"final","If no response, use building concierge as safe drop (policy).")
            return None

        if kind == "damage_dispute":
            if steps_done == 0:
                return ("notify","notify_customer",
                        {"fcm_token": hints.get("passenger_token"),
                         "message":"We're reviewing your damage report. Please upload photos in-app.",
                         "voucher": True, "title":"Support"},
                        "delivered==true","final","Customer notified to upload evidence; support engaged.")
            return None
        return None

    def resolve_stream(self, scenario: str, hints: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
        """
        Orchestrate classification → iterative plan → tool execution,
        yielding SSE-friendly JSON events: classification, step (per tool), summary
        """
        hints = hints or {}
        t0 = time.time()
        cls = self.classify(scenario)
        yield {"type": "classification", "at": now_iso(), "data": cls}

        steps: List[Dict[str, Any]] = []
        outcome = None
        final_message_from_step = None

        for i in range(1, MAX_STEPS+1):
            if (time.time() - t0) > MAX_SECONDS:
                outcome = {"outcome":"escalated","summary":"time_budget_exceeded"}
                break

            proposal = self.propose_next(scenario, cls, steps)
            intent = (proposal.get("intent") or "").strip() or "unspecified"
            tool   = (proposal.get("tool") or "").strip() or "none"
            params = proposal.get("params", {}) or {}
            assertion = proposal.get("assertion")
            finish_reason = proposal.get("finish_reason", "continue")
            final_message = proposal.get("final_message")

            # rails if the model punts
            if tool == "none" and intent == "unspecified":
                policy = self._policy_next(cls.get("kind","unknown"), len(steps), hints)
                if policy is not None:
                    intent, tool, params, assertion, finish_reason, final_message = policy

            # auto-inject from hints
            if tool in ("check_traffic","calculate_alternative_route"):
                params.setdefault("origin", hints.get("origin"))
                params.setdefault("dest", hints.get("dest"))
            elif tool == "notify_passenger_and_driver":
                params.setdefault("driver_token", hints.get("driver_token"))
                params.setdefault("passenger_token", hints.get("passenger_token"))
                params.setdefault("message", "Rerouted; updated ETA shared.")

            step_entry = {"idx": i, "intent": intent, "tool": tool, "params": params, "assertion": assertion, "ts": now_iso()}

            # Short-circuit: no-tool step
            if tool == "none":
                step_entry["observation"] = {"note": "no tool executed"}
                step_entry["success"] = True
            # Skip notify if no tokens
            elif tool == "notify_passenger_and_driver" and not (params.get("driver_token") or params.get("passenger_token")):
                step_entry["observation"] = {"note": "no device tokens; skipping notification"}
                step_entry["success"] = True
            else:
                obs, err = self.execute_tool(tool, params)
                success = check_assertion(assertion, obs)
                step_entry["observation"] = obs
                step_entry["success"] = success

                # narrative nudge
                if tool == "calculate_alternative_route":
                    imp = step_entry["observation"].get("improvementMin")
                    if isinstance(imp, (int, float)) and imp <= 0 and not final_message:
                        final_message = "No faster route available. Staying on current route."

            steps.append(step_entry)
            yield {"type": "step", "at": now_iso(), "data": step_entry}

            if finish_reason in ("final","escalate"):
                if step_entry["success"]:
                    final_message_from_step = final_message
                    outcome = {"outcome": "resolved" if finish_reason=="final" else "escalated",
                               "summary": final_message or ""}
                    break

            time.sleep(STREAM_DELAY)

        if outcome is None:
            outcome = {"outcome": "resolved" if steps else "escalated", "summary": ""}

        # Compose truthful summary
        notes = []
        s = next((s for s in steps if s["tool"] == "check_traffic" and s.get("success")), None)
        if s:
            o = s["observation"]
            notes.append(f"ETA ~{o.get('etaMin')} min (delay {o.get('delayMin')} min).")
        s = next((s for s in steps if s["tool"] == "calculate_alternative_route"), None)
        if s:
            imp = s["observation"].get("improvementMin") if isinstance(s.get("observation"), dict) else None
            if isinstance(imp, (int, float)) and imp > 0:
                notes.append("Applied faster route.")
            else:
                notes.append("No faster route; staying course.")
        s_notify = next((s for s in steps if s["tool"] == "notify_passenger_and_driver"), None)
        if s_notify and not (s_notify["params"].get("driver_token") or s_notify["params"].get("passenger_token")):
            notes.append("Could not notify (no device tokens).")
        elif s_notify and s_notify.get("success") and isinstance(s_notify.get("observation"), dict):
            if s_notify["observation"].get("driverDelivered") or s_notify["observation"].get("passengerDelivered"):
                notes.append("Notifications delivered.")

        summary_text = (final_message_from_step or outcome.get("summary") or "").strip()
        if not summary_text:
            summary_text = " ".join(n for n in notes if n) or ""

        yield {"type": "summary","at": now_iso(),
               "data": {"scenario": scenario, "classification": cls,
                        "plan": [f"{s['intent']}::{s['tool']}" for s in steps],
                        "outcome": outcome["outcome"], "summary": summary_text,
                        "metrics": {"totalSeconds": int(time.time()-t0), "steps": len(steps)}}}

    def resolve_sync(self, scenario: str, hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Synchronous runner for tests. Returns a trace array.
        """
        trace = []
        for evt in self.resolve_stream(scenario, hints=hints or {}):
            trace.append(evt)
        return {"trace": trace}

# ----------------------------- TOOL REGISTRY ---------------------------
TOOLS: Dict[str, Dict[str, Any]] = {
    "check_traffic": {"fn": tool_check_traffic, "desc": "ETA/naive delay via Routes API.", "schema": {"origin":"[lat,lon]","dest":"[lat,lon]"}},
    "calculate_alternative_route": {"fn": tool_calculate_alternative_route, "desc": "Alternative routes & improvement (Routes API).", "schema": {"origin":"[lat,lon]","dest":"[lat,lon]"}},
    "compute_route_matrix": {"fn": tool_compute_route_matrix, "desc": "Route matrix (Routes API).", "schema": {"origins":"[[lat,lon],...]","destinations":"[[lat,lon],...]"}},
    "check_weather": {"fn": tool_check_weather, "desc": "Current weather (Google Weather API).", "schema": {"lat":"float","lon":"float"}},
    "air_quality": {"fn": tool_air_quality, "desc": "Current air quality (Air Quality API).", "schema": {"lat":"float","lon":"float"}},
    "pollen_forecast": {"fn": tool_pollen_forecast, "desc": "Pollen forecast (Pollen API).", "schema": {"lat":"float","lon":"float"}},
    "time_zone": {"fn": tool_time_zone, "desc": "Time zone for location (Time Zone API).", "schema": {"lat":"float","lon":"float","timestamp":"int?"}},
    "places_search_nearby": {"fn": tool_places_search_nearby, "desc": "Nearby places (New).", "schema": {"lat":"float","lon":"float","radius_m":"int","keyword":"str?","included_types":"list[str]?"}},
    "place_details": {"fn": tool_place_details, "desc": "Place details (New).", "schema": {"place_id":"str"}},
    "roads_snap": {"fn": tool_roads_snap, "desc": "Snap GPS points to roads.", "schema": {"points":"[[lat,lon],...]","interpolate":"bool?"}},
    "geocode_place": {"fn": tool_geocode_place, "desc": "Geocode a place/address.", "schema": {"query":"str"}},
    "notify_customer": {"fn": tool_notify_customer, "desc": "Push notify customer (FCM v1).", "schema": {"fcm_token":"str","message":"str","voucher":"bool","title":"str"}},
    "notify_passenger_and_driver": {"fn": tool_notify_passenger_and_driver, "desc": "Push notify both (FCM v1).", "schema": {"driver_token":"str","passenger_token":"str","message":"str"}}
}

# ----------------------------- FLASK APP -------------------------------
app = Flask(__name__)
CORS(app)
agent = SynapseAgent(_llm)

@app.route("/api/health")
def health():
    """
    Health/config check.
    """
    return jsonify({
        "ok": True,
        "model": GEMINI_MODEL,
        "project": FIREBASE_PROJECT_ID,
        "googleKeySet": bool(GOOGLE_MAPS_API_KEY)
    })

@app.route("/api/tools")
def tools():
    """
    Returns the tool catalog (for UI introspection).
    """
    return jsonify({"tools": [{"name": k, "desc": v["desc"], "schema": v["schema"]} for k,v in TOOLS.items()]})

@app.route("/api/agent/run")
def run_stream():
    """
    GET /api/agent/run
    Query params:
      - scenario: free-text description (you can also embed hints)
      - origin, dest: "lat,lon" pairs (optional)
      - origin_place, dest_place: names to geocode if coords not provided (optional)
      - driver_token, passenger_token: FCM device tokens (optional)

    Streams step-by-step JSON (SSE) until summary, then [DONE].
    """
    scenario = (request.args.get("scenario") or "").strip()
    if not scenario:
        return jsonify({"error":"missing scenario"}), 400

    origin_q = request.args.get("origin")
    dest_q   = request.args.get("dest")
    driver_token    = request.args.get("driver_token")
    passenger_token = request.args.get("passenger_token")
    origin_place_q  = request.args.get("origin_place")
    dest_place_q    = request.args.get("dest_place")

    # append hints for transparency
    if origin_q and dest_q:
        scenario += f"\n\n(Hint: origin={origin_q}, dest={dest_q})"
    if origin_place_q and dest_place_q:
        scenario += f"\n\n(Hint: origin_place={origin_place_q}, dest_place={dest_place_q})"
    if driver_token or passenger_token:
        scenario += f"\n\n(Hint: driver_token={'…' if driver_token else 'none'}, passenger_token={'…' if passenger_token else 'none'})"

    hints = extract_hints(scenario, driver_token, passenger_token)

    # override from query params if provided
    if origin_q and dest_q:
        try:
            lat1, lon1 = map(float, origin_q.split(","))
            lat2, lon2 = map(float, dest_q.split(","))
            hints["origin"] = [lat1, lon1]
            hints["dest"]   = [lat2, lon2]
        except Exception:
            pass
    if origin_place_q:
        hints["origin_place"] = origin_place_q
    if dest_place_q:
        hints["dest_place"]   = dest_place_q

    # geocode with Google if coords still missing
    if not hints.get("origin") and hints.get("origin_place"):
        pt = _geocode(hints["origin_place"])
        if pt:
            hints["origin"] = [pt[0], pt[1]]
    if not hints.get("dest") and hints.get("dest_place"):
        pt = _geocode(hints["dest_place"])
        if pt:
            hints["dest"] = [pt[0], pt[1]]

    def generate():
        try:
            for evt in agent.resolve_stream(scenario, hints=hints):
                yield sse(evt)
            yield sse("[DONE]")
        except Exception as e:
            yield sse({"type":"error","at":now_iso(),"data":{"message":str(e),"trace":traceback.format_exc()}})
            yield sse("[DONE]")

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control":"no-cache",
        "Connection":"keep-alive",
        "X-Accel-Buffering":"no"
    }
    return Response(generate(), headers=headers)

@app.route("/api/agent/resolve", methods=["POST"])
def resolve_sync_endpoint():
    """
    POST /api/agent/resolve
    JSON body:
      scenario (str), optional driver_token/passenger_token,
      either origin/dest as [lat,lon], or origin_place/dest_place to geocode.
    Returns a synchronous JSON trace array (useful for tests).
    """
    data = request.get_json(force=True) or {}
    scenario = (data.get("scenario") or "").strip()
    if not scenario:
        return jsonify({"error":"missing scenario"}), 400
    driver_token = data.get("driver_token")
    passenger_token = data.get("passenger_token")
    origin = data.get("origin")  # [lat,lon]
    dest   = data.get("dest")    # [lat,lon]
    origin_place = data.get("origin_place")
    dest_place   = data.get("dest_place")

    # geocode if missing
    if (not origin or not dest):
        if not origin and origin_place:
            pt = _geocode(origin_place)
            if pt:
                origin = [pt[0], pt[1]]
        if not dest and dest_place:
            pt = _geocode(dest_place)
            if pt:
                dest = [pt[0], pt[1]]

    # embed hints
    if origin and dest:
        scenario += f"\n\n(Hint: origin={origin[0]},{origin[1]}, dest={dest[0]},{dest[1]})"
    if origin_place or dest_place:
        scenario += f"\n\n(Hint: origin_place={origin_place or '—'}, dest_place={dest_place or '—'})"

    hints = {"origin": origin, "dest": dest, "driver_token": driver_token, "passenger_token": passenger_token}
    if origin_place:
        hints["origin_place"] = origin_place
    if dest_place:
        hints["dest_place"]   = dest_place

    result = agent.resolve_sync(scenario, hints=hints)
    return jsonify(result)

# Optional: test FCM v1
@app.route("/api/fcm/send_test", methods=["POST"])
def fcm_send_test():
    data = request.get_json(force=True) or {}
    token = data.get("token")
    title = data.get("title","Test")
    body  = data.get("body","Hello from Synapse")
    if not token:
        return jsonify({"error":"missing token"}), 400
    res = _fcm_v1_send(token, title, body)
    return jsonify(res)

if __name__ == "__main__":
    # Run:  python app.py
    app.run(host="0.0.0.0", port=5000, debug=False)
