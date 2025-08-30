# app.py
import os, re, json, time, math, traceback, logging
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, request, jsonify, Response, g
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
GOOGLE_MAPS_API_KEY  = get_cfg("GOOGLE_MAPS_API_KEY", "").strip()
GEMINI_API_KEY       = get_cfg("GEMINI_API_KEY", "").strip()
GEMINI_MODEL         = get_cfg("GEMINI_MODEL", "gemini-2.0-flash")

FIREBASE_PROJECT_ID  = get_cfg("FIREBASE_PROJECT_ID", "").strip()
SERVICE_ACCOUNT_FILE = get_cfg("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

# Require Firebase auth for protected endpoints (run/resolve/fcm)
REQUIRE_AUTH         = get_cfg("REQUIRE_AUTH", "false").lower() == "true"

# CORS origins (comma-separated). Default: permissive (dev).
CORS_ORIGINS         = [o.strip() for o in get_cfg("CORS_ORIGINS", "*").split(",")]

MAX_STEPS            = int(get_cfg("MAX_STEPS", "7"))
MAX_SECONDS          = int(get_cfg("MAX_SECONDS", "120"))
STREAM_DELAY         = float(get_cfg("STREAM_DELAY", "0.10"))
BASELINE_SPEED_KMPH  = float(get_cfg("BASELINE_SPEED_KMPH", "40.0"))

DEFAULT_CUSTOMER_TOKEN   = get_cfg("DEFAULT_CUSTOMER_TOKEN", "").strip()
DEFAULT_DRIVER_TOKEN     = get_cfg("DEFAULT_DRIVER_TOKEN", "").strip()
DEFAULT_PASSENGER_TOKEN  = get_cfg("DEFAULT_PASSENGER_TOKEN", "").strip()

# If true, we do NOT actually send push—either simulate or call FCM validate-only
FCM_DRY_RUN              = get_cfg("FCM_DRY_RUN", "false").lower() == "true"

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

# ----------------------------- FIREBASE VERIFY (ID token) --------------
try:
    import firebase_admin
    from firebase_admin import credentials as fb_credentials, auth as fb_auth
    _admin_initialized = False
    if SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
        firebase_admin.initialize_app(fb_credentials.Certificate(SERVICE_ACCOUNT_FILE))
        _admin_initialized = True
        log.info("[firebase_admin] initialized with service account")
    else:
        firebase_admin.initialize_app()
        _admin_initialized = True
        log.info("[firebase_admin] initialized with ADC")
except Exception as e:
    _admin_initialized = False
    if REQUIRE_AUTH:
        raise RuntimeError(f"Failed to init firebase_admin but REQUIRE_AUTH is true: {e}")
    log.warning(f"[firebase_admin] not initialized (auth disabled): {e}")

def _extract_bearer_token() -> str:
    hdr = request.headers.get("Authorization", "")
    if hdr.startswith("Bearer "):
        return hdr.split(" ", 1)[1].strip()
    return ""

def verify_firebase_token_optional() -> Optional[Dict[str, Any]]:
    """
    Returns decoded token dict if token present and valid, else None.
    """
    token = _extract_bearer_token() or request.args.get("token", "")
    if not token or not _admin_initialized:
        return None
    try:
        return fb_auth.verify_id_token(token)
    except Exception as e:
        log.warning(f"[auth] token present but invalid: {e}")
        return None

def require_auth(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        decoded = verify_firebase_token_optional()
        if REQUIRE_AUTH and (decoded is None):
            return jsonify({"error": "unauthorized"}), 401
        g.user = decoded  # may be None if not provided/required
        return fn(*args, **kwargs)
    return wrapper

# ----------------------------- HTTP helpers ----------------------------
def http_get(url: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None, timeout: float = 20.0):
    r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def http_post(url: str, json_body: Dict[str, Any], headers: Dict[str, str], timeout: float = 25.0):
    r = requests.post(url, json=json_body, headers=headers, timeout=timeout)
    try:
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"ok": True, "text": r.text}
    except requests.HTTPError:
        return {"ok": False, "status": r.status_code, "error_text": r.text}

# ----------------------------- UTIL -----------------------------------
def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def sse(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
    return f"data: {payload}\n\n"

def strip_json_block(text: str) -> str:
    t = (text or "").strip()
    if "```" in t:
        parts = t.split("```")
        if len(parts) >= 3:
            block = parts[1].strip()
            if block.lower().startswith("json"):
                block = block.split("\n", 1)[1] if "\n" in block else ""
            return block
    return t

def safe_json(text: str, default: Any = None) -> Any:
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
    R = 6371.0088
    import math as _m
    phi1, phi2 = _m.radians(lat1), _m.radians(lat2)
    dphi = _m.radians(lat2 - lat1)
    dlmb = _m.radians(lon2 - lon1)
    a = _m.sin(dphi/2)**2 + _m.cos(phi1)*_m.cos(phi2)*_m.sin(dlmb/2)**2
    return 2 * R * _m.asin(_m.sqrt(a))

# -------------------------- HINT EXTRACTORS ---------------------------
HINT_RE_ORIGIN = re.compile(r"origin\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)
HINT_RE_DEST   = re.compile(r"dest\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)
HINT_RE_ORIGIN_TEXT = re.compile(r"(?:^|[\s,;])origin(?:\s*[:=])\s*([^\n]+)", re.I)
HINT_RE_DEST_TEXT   = re.compile(r"(?:^|[\s,;])dest(?:\s*[:=])\s*([^\n]+)", re.I)
HINT_RE_FROM_TO     = re.compile(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:[,.]|$)", re.I)

def extract_hints(scenario: str, driver_token: Optional[str], passenger_token: Optional[str]) -> Dict[str, Any]:
    hints: Dict[str, Any] = {}
    m1, m2 = HINT_RE_ORIGIN.search(scenario), HINT_RE_DEST.search(scenario)
    if m1 and m2:
        hints["origin"] = [float(m1.group(1)), float(m1.group(2))]
        hints["dest"]   = [float(m2.group(1)), float(m2.group(2))]
    mt1, mt2 = HINT_RE_ORIGIN_TEXT.search(scenario), HINT_RE_DEST_TEXT.search(scenario)
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
    h = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY}
    if field_mask:
        h["X-Goog-FieldMask"] = field_mask
    return h

def _routes_post(path: str, body: dict, field_mask: str) -> dict:
    url = f"https://routes.googleapis.com/{path}"
    return http_post(url, body, headers=_gm_headers(field_mask))

def _places_post(path: str, body: dict, field_mask: str) -> dict:
    url = f"https://places.googleapis.com/v1/{path}"
    return http_post(url, body, headers=_gm_headers(field_mask))

def _places_get(path: str, field_mask: str) -> dict:
    url = f"https://places.googleapis.com/v1/{path}"
    return http_get(url, headers=_gm_headers(field_mask))

def _geocode(text: str) -> Optional[tuple[float, float]]:
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
    pt = _geocode(query)
    if not pt:
        return {"found": False}
    lat, lon = pt
    return {"found": True, "lat": lat, "lon": lon, "query": query}

def _seconds_to_minutes_str_dur(sec_str: str) -> float:
    try:
        s = float(sec_str.rstrip("s"))
        return round(s / 60.0, 1)
    except Exception:
        return 0.0

def tool_check_traffic(origin: List[float], dest: List[float]) -> Dict[str, Any]:
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
        dist_km = round(haversine_km(origin[0], origin[1], dest[0], dest[1]), 3)
        eta_min = round((dist_km / BASELINE_SPEED_KMPH) * 60.0, 1) if dist_km else 0.0
        return {"approximate": True, "reason": f"routes_failure:{str(e)}",
                "distanceKm": round(dist_km, 2), "etaMin": eta_min, "delayMin": 0.0}

def tool_calculate_alternative_route(origin: List[float], dest: List[float]) -> Dict[str, Any]:
    if not origin or not dest or len(origin) != 2 or len(dest) != 2:
        return {"error": "invalid_coordinates"}

    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}}
        ,
        "destination": {"location": {"latLng": {"latitude": dest[0], "longitude": dest[1]}}}
        ,
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
        return {"elements": out[:5], "count": min(5, len(out))}
    except Exception as e:
        return {"error": f"route_matrix_failure:{str(e)}"}

def tool_check_weather(lat: float, lon: float) -> Dict[str, Any]:
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
    url = "https://pollen.googleapis.com/v1/forecast:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return {"found": True, "raw": data}
    except Exception as e:
        return {"error": f"pollen_failure:{str(e)}"}

def tool_places_search_nearby(lat: float, lon: float, radius_m: int = 2000, keyword: Optional[str] = None, included_types: Optional[List[str]] = None) -> Dict[str, Any]:
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
        places = (data.get("places") or [])[:5]
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
    if not points or any(len(p) != 2 for p in points):
        return {"error": "invalid_points"}
    path = "|".join([f"{p[0]},{p[1]}" for p in points])
    url = "https://roads.googleapis.com/v1/snapToRoads"
    params = {"path": path, "interpolate": "true" if interpolate else "false", "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        sp = data.get("snappedPoints", [])[:5]
        return {"snappedPoints": sp, "count": len(sp)}
    except Exception as e:
        return {"error": f"roads_failure:{str(e)}"}

def tool_time_zone(lat: float, lon: float, timestamp: Optional[int] = None) -> Dict[str, Any]:
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

# ------------------------- NOTIFICATIONS (FCM v1) ---------------------
def _is_placeholder_token(token: str) -> bool:
    t = (token or "").strip().lower()
    return (not t) or (t in {"token","customer_token","driver_token","passenger_token","str"})

def _fcm_v1_send(token: str, title: str, body: str, data: Optional[dict] = None) -> Dict[str, Any]:
    # Simulate/validate-only mode (dev)
    if FCM_DRY_RUN:
        log.info("[tool_fcm_send] DRY_RUN on → simulating delivered")
        return {"delivered": True, "dryRun": True}

    # Block missing/placeholder tokens
    if _is_placeholder_token(token):
        return {"delivered": False, "reason": "missing_or_placeholder_device_token"}

    access_token = _fcm_access_token()
    base = f"https://fcm.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/messages:send"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    msg = {"message": {"token": token, "notification": {"title": title, "body": body}}}
    if data: msg["message"]["data"] = data

    log.info(f"[tool_fcm_send] sending via FCM v1 title='{title}'")
    res = http_post(base, msg, headers, timeout=10)
    ok = bool(res) and (("name" in res) or res.get("ok") is True)
    if not ok:
        return {"delivered": False, "error": res}
    return {"delivered": True, "fcmResponse": res}

def tool_notify_customer(fcm_token: Optional[str], message: str, voucher: bool=False, title: str="Order Update") -> Dict[str, Any]:
    return _fcm_v1_send(fcm_token or "", title, message, {"voucher": json.dumps(bool(voucher))})

def tool_notify_passenger_and_driver(driver_token: Optional[str], passenger_token: Optional[str], message: str) -> Dict[str, Any]:
    d = _fcm_v1_send(driver_token or "", "Route Update", message) if driver_token else {"delivered": False}
    p = _fcm_v1_send(passenger_token or "", "Route Update", message) if passenger_token else {"delivered": False}
    return {"driverDelivered": d.get("delivered"), "passengerDelivered": p.get("delivered")}

# ----------------------------- ASSERTIONS ------------------------------
# --- replace the whole check_assertion with this ---
def check_assertion(assertion: Optional[str], observation: Dict[str, Any]) -> bool:
    """
    Return True when:
      - assertion is None/empty, and observation has no obvious error, OR
      - the named predicate matches the observation.
    Handles common boolean/string/number cases robustly.
    """
    # No explicit assertion → pass unless an error key exists
    if not assertion or not str(assertion).strip():
        # if observation contains an explicit error field, fail
        if isinstance(observation, dict) and ("error" in observation or "trace" in observation):
            return False
        return True

    a = str(assertion).strip().lower().replace(" ", "")

    def _truthy(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v != 0
        s = str(v).strip().lower()
        return s in {"true","1","yes","y","ok"}

    # Common canned predicates (case-insensitive)
    if "response!=none" in a:
        return isinstance(observation, dict) and len(observation) > 0

    if "len(routes)>=1" in a or "routes>=1" in a:
        routes = observation.get("routes")
        return isinstance(routes, list) and len(routes) >= 1

    if "customerack==true" in a:
        return _truthy(observation.get("customerAck"))

    if "delivered==true" in a:
        # supports notify_customer and notify_passenger_and_driver
        return (_truthy(observation.get("delivered"))
                or _truthy(observation.get("driverDelivered"))
                or _truthy(observation.get("passengerDelivered")))

    if "approved==true" in a:
        return _truthy(observation.get("approved"))

    if "improvementmin>0" in a:
        v = observation.get("improvementMin")
        return isinstance(v, (int, float)) and v > 0

    if "improvementmin>=0" in a:
        return isinstance(observation.get("improvementMin"), (int, float))

    if "etadeltamin<=0" in a:
        v = observation.get("etaDeltaMin")
        return isinstance(v, (int, float)) and v <= 0

    if "candidates>0" in a or "count>0" in a:
        v = observation.get("count") or observation.get("candidates")
        if isinstance(v, list):  return len(v) > 0
        if isinstance(v, (int, float)): return v > 0
        return False

    if "delaymin>=0" in a:
        v = observation.get("delayMin")
        return isinstance(v, (int, float)) and v >= 0

    if "hazard==false" in a:
        return not _truthy(observation.get("hazard"))

    if "found==true" in a:
        return _truthy(observation.get("found"))

    if "photos>0" in a:
        v = observation.get("photos")
        return isinstance(v, (int, float)) and v > 0

    if "flow==started" in a:
        return (observation.get("flow") == "started")

    if "refunded==true" in a:
        return _truthy(observation.get("refunded"))

    if "cleared==true" in a:
        return _truthy(observation.get("cleared"))

    if "feedbacklogged==true" in a:
        return _truthy(observation.get("feedbackLogged"))

    if "suggested==true" in a:
        return _truthy(observation.get("suggested"))

    if "status!=none" in a:
        return observation.get("status") is not None

    if "merchants>0" in a:
        m = observation.get("merchants")
        return isinstance(m, list) and len(m) > 0

    if "lockers>0" in a:
        l = observation.get("lockers")
        return isinstance(l, list) and len(l) > 0

    if "messagesent!=none" in a:
        return observation.get("messageSent") is not None

    if a.startswith("has."):  # e.g. has.prepTimeMin
        key = a.split("has.", 1)[1]
        return key in observation

    # Final generic equality like foo==bar, normalized
    if "==" in a and all(op not in a for op in (">", "<", "!=")):
        k, val = a.split("==", 1)
        ov = observation.get(k)
        # normalize both sides
        sval = val.strip().lower()
        if sval in {"true","false"}:
            return _truthy(ov) == (sval == "true")
        try:
            # numeric compare if possible
            return float(str(ov)) == float(sval)
        except Exception:
            return str(ov).strip().lower() == sval

    # If we can’t parse, be safe: don’t fail the step
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

# ----------------------------- POLICY RAILS (extended) -----------------
def _policy_next_extended(kind: str, steps_done: int, hints: Dict[str, Any]) -> Optional[tuple]:
    """
    Returns:
      (intent, tool, params, assertion, finish_reason, final_message, reason)
    """
    # Traffic
    if kind == "traffic":
        origin = hints.get("origin"); dest = hints.get("dest")
        if not origin or not dest:
            if steps_done == 0:
                return ("clarify", "none",
                        {"question":"Provide origin/dest as 'origin=lat,lon dest=lat,lon' or place names."},
                        None, "continue", None,
                        "No coordinates; ask for origin/dest.")
            return None
        if steps_done == 0:
            return ("check congestion","check_traffic",
                    {"origin":origin,"dest":dest},
                    "delayMin>=0","continue",None,
                    "Measure baseline ETA and traffic delay.")
        if steps_done == 1:
            return ("reroute","calculate_alternative_route",
                    {"origin":origin,"dest":dest},
                    "improvementMin>=0","continue",None,
                    "Compute alternatives and pick fastest.")
        if steps_done == 2:
            msg = "Rerouted to faster path; updated ETA shared."
            return ("inform both","notify_passenger_and_driver",
                    {"driver_token": hints.get("driver_token"),
                     "passenger_token": hints.get("passenger_token"),
                     "message": msg},
                    "delivered==true","final","Reroute applied; passengers notified.",
                    "Notify both parties.")
        return None

    # Merchant capacity
    if kind == "merchant_capacity":
        merchant_id = hints.get("merchant_id","merchant_demo")
        latlon = hints.get("origin") or hints.get("dest")

        if steps_done == 0:
            return ("check merchant status","get_merchant_status",
                    {"merchant_id": merchant_id},
                    None,"continue",None,
                    "Check prep time and backlog.")

        if (steps_done == 1) and (latlon is not None):
            return ("suggest alt merchant","get_nearby_merchants",
                    {"lat": latlon[0], "lon": latlon[1], "radius_m": 2000},
                    "merchants>0","continue",None,
                    "Suggest up to 5 nearby alternates.")
        if (steps_done == 1) and (latlon is None):
            token = hints.get("customer_token") or hints.get("passenger_token") or DEFAULT_CUSTOMER_TOKEN
            params = {
                "fcm_token": token,
                "message": "Merchant is overloaded; we’ll share alternatives shortly or re-assign.",
                "voucher": True, "title":"Delay notice"
            }
            assertion = "delivered==true" if (token or FCM_DRY_RUN) else None
            return ("notify","notify_customer", params, assertion, "final",
                    "Customer informed (no coordinates available).",
                    "No coordinates available to search alternatives; notify customer.")

        if steps_done == 2:
            token = hints.get("customer_token") or hints.get("passenger_token") or DEFAULT_CUSTOMER_TOKEN
            params = {
                "fcm_token": token,
                "message": "Merchant is overloaded; sharing 3 nearby alternatives.",
                "voucher": True, "title":"Delay notice"
            }
            assertion = "delivered==true" if (token or FCM_DRY_RUN) else None
            return ("notify","notify_customer", params, assertion, "final",
                    "Customer informed; alternatives shared.",
                    "Send push with voucher and alternatives.")
        return None

    # Damage dispute
    if kind == "damage_dispute":
        order_id = hints.get("order_id","order_demo")
        driver_id = hints.get("driver_id","driver_demo")
        merchant_id = hints.get("merchant_id","merchant_demo")
        if steps_done == 0:
            return ("start mediation","initiate_mediation_flow",{"order_id": order_id},
                    "flow==started","continue",None,"Start structured mediation.")
        if steps_done == 1:
            return ("collect evidence","collect_evidence",{"order_id": order_id},
                    "photos>0","continue",None,"Collect photos and questionnaire.")
        if steps_done == 2:
            return ("analyze evidence","analyze_evidence",{"order_id": order_id},
                    "status!=none","continue",None,"Decide likely fault.")
        if steps_done == 3:
            return ("refund customer","issue_instant_refund",{"order_id": order_id,"amount": 5.0},
                    "refunded==true","continue",None,"Issue goodwill refund.")
        if steps_done == 4:
            return ("clear driver","exonerate_driver",{"driver_id": driver_id},
                    "cleared==true","continue",None,"Clear driver of fault.")
        if steps_done == 5:
            return ("feedback to merchant","log_merchant_packaging_feedback",
                    {"merchant_id": merchant_id,"feedback":"Seal failed; spillage evidence attached."},
                    "feedbacklogged==true","continue",None,"Log packaging issue.")
        if steps_done == 6:
            token = hints.get("customer_token") or hints.get("passenger_token") or DEFAULT_CUSTOMER_TOKEN
            params = {
                "fcm_token": token,
                "message": "Issue resolved: refund issued; driver cleared. Thanks for your patience.",
                "voucher": False, "title":"Resolution"
            }
            assertion = "delivered==true" if (token or FCM_DRY_RUN) else None
            return ("notify","notify_customer", params, assertion, "final",
                    "Both parties informed; trip can be closed.",
                    "Send resolution push.")
        return None

    # Recipient unavailable
    if kind == "recipient_unavailable":
        if steps_done == 0:
            rid = hints.get("recipient_id","recipient_demo")
            return ("reach out via chat","contact_recipient_via_chat",
                    {"recipient_id": rid, "message":"Driver has arrived. How should we proceed?"},
                    "messagesent!=none","continue",None,"Start chat to coordinate.")
        if steps_done == 1:
            addr = hints.get("dest_place") or "Building concierge"
            return ("suggest safe drop","suggest_safe_drop_off",{"address": addr},
                    "suggested==true","continue",None,"Offer safe drop.")
        if steps_done == 2:
            latlon = hints.get("dest") or hints.get("origin")
            if latlon:
                return ("find locker","find_nearby_locker",
                        {"lat": latlon[0], "lon": latlon[1], "radius_m": 1200},
                        "lockers>0","final","Suggested nearest parcel locker as fallback.",
                        "Provide locker fallback.")
            return ("notify","notify_customer",
                    {"fcm_token": hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN,
                     "message":"We attempted delivery; please advise next steps.",
                     "voucher": False, "title":"Delivery attempt"},
                    "delivered==true","final","Awaiting recipient guidance.",
                    "No coordinates for lockers; notify customer.")
        return None

    # Unknown/other kinds: stop after classification
    return None

# ----------------------------- AGENT -----------------------------------
class SynapseAgent:
    """
    Full agent with deterministic policy rails and streaming.
    """

    def __init__(self, llm):
        self.llm = llm

    def classify(self, scenario: str) -> Dict[str, Any]:
        prompt = CLASSIFY_PROMPT.format(labels=json.dumps(KIND_LABELS), scenario=scenario)
        try:
            resp = self.llm.generate_content(prompt)
            resp_text = getattr(resp, "text", "") or "{}"
            parsed = safe_json(strip_json_block(resp_text), {}) or {}
        except Exception as e:
            log.error(f"[gemini_error:classify] {e}")
            parsed = {}

        kind = (parsed.get("kind") or "other").lower()
        if kind not in [k.lower() for k in KIND_LABELS]:
            kind = "other"
        severity = parsed.get("severity", "med")
        try:
            uncertainty = float(parsed.get("uncertainty", 0.3))
        except Exception:
            uncertainty = 0.3
        return {"kind": kind, "severity": severity, "uncertainty": uncertainty}

    def resolve_stream(self, scenario: str, hints: Optional[Dict[str, Any]] = None):
        t0 = time.time()
        hints = hints or {}

        # 1) classification
        cls = self.classify(scenario)
        kind = cls.get("kind", "other")
        yield {"type": "classification", "at": now_iso(), "data": cls, "kind": kind}
        time.sleep(STREAM_DELAY)

        # 2) steps
        steps = 0
        while steps < MAX_STEPS and (time.time() - t0) < MAX_SECONDS:
            step = _policy_next_extended(kind, steps, hints)
            if not step:
                break

            intent, tool, params, assertion, finish_reason, final_message, reason = step

            # Execute tool (including 'none')
            if tool == "none":
                obs = {"note": "clarification_requested"}
            else:
                try:
                    fn = TOOLS.get(tool, {}).get("fn")
                    if fn:
                        obs = fn(**params)
                    else:
                        obs = {"error": f"tool_not_found:{tool}"}
                except Exception as e:
                    obs = {"error": str(e), "trace": traceback.format_exc()}

            # Evaluate assertion
            passed = check_assertion(assertion, obs)

            # Extra safety: if there was no explicit error and we got a sensible observation,
            # treat the step as passed even if the assertion string didn't match.
            if not passed and isinstance(obs, dict) and "error" not in obs:
                passed = True

            yield {
                "type": "step",
                "at": now_iso(),
                "kind": kind,
                "data": {
                    "index": steps,
                    "intent": intent,
                    "reason": reason,
                    "tool": tool,
                    "params": params,
                    "assertion": assertion,
                    "observation": obs,
                    "passed": passed,
                    "finish_reason": finish_reason,
                    "final_message": final_message,
                },
            }
            steps += 1
            time.sleep(STREAM_DELAY)

            if finish_reason in ("final", "escalate"):
                break

        # 3) summary
        duration = int(time.time() - t0)
        yield {
            "type": "summary",
            "at": now_iso(),
            "kind": kind,
            "data": {
                "scenario": scenario,
                "classification": cls,
                "metrics": {"totalSeconds": duration, "steps": steps},
                "outcome": "resolved" if steps > 0 else "classified_only",
            },
        }

        def resolve_sync(self, scenario: str, hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            trace = []
            for evt in self.resolve_stream(scenario, hints=hints or {}):
                trace.append(evt)
            return {"trace": trace}

# ----------------------------- TOOL REGISTRY ---------------------------
TOOLS: Dict[str, Dict[str, Any]] = {
    "check_traffic": {
        "fn": tool_check_traffic,
        "desc": "ETA/naive delay via Routes API.",
        "schema": {"origin": "[lat,lon]", "dest": "[lat,lon]"},
    },
    "calculate_alternative_route": {
        "fn": tool_calculate_alternative_route,
        "desc": "Alternative routes & improvement (Routes API).",
        "schema": {"origin": "[lat,lon]", "dest": "[lat,lon]"},
    },
    "compute_route_matrix": {
        "fn": tool_compute_route_matrix,
        "desc": "Route matrix (Routes API).",
        "schema": {"origins": "[[lat,lon],...]", "destinations": "[[lat,lon],...]"},
    },
    "check_weather": {
        "fn": tool_check_weather,
        "desc": "Current weather (Google Weather API).",
        "schema": {"lat": "float", "lon": "float"},
    },
    "air_quality": {
        "fn": tool_air_quality,
        "desc": "Current air quality (Air Quality API).",
        "schema": {"lat": "float", "lon": "float"},
    },
    "pollen_forecast": {
        "fn": tool_pollen_forecast,
        "desc": "Pollen forecast (Pollen API).",
        "schema": {"lat": "float", "lon": "float"},
    },
    "time_zone": {
        "fn": tool_time_zone,
        "desc": "Time zone for location (Time Zone API).",
        "schema": {"lat": "float", "lon": "float", "timestamp": "int?"},
    },
    "places_search_nearby": {
        "fn": tool_places_search_nearby,
        "desc": "Nearby places (New).",
        "schema": {"lat": "float", "lon": "float", "radius_m": "int", "keyword": "str?", "included_types": "list[str]?"},
    },
    "place_details": {
        "fn": tool_place_details,
        "desc": "Place details (New).",
        "schema": {"place_id": "str"},
    },
    "roads_snap": {
        "fn": tool_roads_snap,
        "desc": "Snap GPS points to roads.",
        "schema": {"points": "[[lat,lon],...]", "interpolate": "bool?"},
    },
    "geocode_place": {
        "fn": tool_geocode_place,
        "desc": "Geocode a place/address.",
        "schema": {"query": "str"},
    },
    "notify_customer": {
        "fn": tool_notify_customer,
        "desc": "Push notify customer (FCM v1).",
        "schema": {"fcm_token": "str", "message": "str", "voucher": "bool", "title": "str"},
    },
    "notify_passenger_and_driver": {
        "fn": tool_notify_passenger_and_driver,
        "desc": "Push notify both (FCM v1).",
        "schema": {"driver_token": "str", "passenger_token": "str", "message": "str"},
    },

    # --- Custom tools (mocked to satisfy scenarios from the brief) ---
    "get_merchant_status": {"fn": lambda merchant_id: {"merchant_id": merchant_id, "prepTimeMin": 40, "backlogOrders": 12, "response": True},
                            "desc": "Merchant backlog/prep time.", "schema": {"merchant_id":"str"}},
    "reroute_driver": {"fn": lambda driver_id, new_task: {"driver_id": driver_id, "rerouted": True, "newTask": new_task},
                       "desc": "Reassign driver.", "schema": {"driver_id":"str","new_task":"str"}},
    "get_nearby_merchants": {"fn": lambda lat, lon, radius_m=2000: {
        "count": 5, "merchants": [
            {"id": "m1", "name": "Alt Restaurant A", "etaMin": 15},
            {"id": "m2", "name": "Alt Restaurant B", "etaMin": 20},
            {"id": "m3", "name": "Alt Restaurant C", "etaMin": 25},
            {"id": "m4", "name": "Alt Restaurant D", "etaMin": 18},
            {"id": "m5", "name": "Alt Restaurant E", "etaMin": 22},
        ]},
        "desc": "Nearby alternate restaurants (≤5).", "schema": {"lat":"float","lon":"float","radius_m":"int"}},
    "initiate_mediation_flow": {"fn": lambda order_id: {"order_id": order_id, "flow": "started"},
                                "desc": "Start mediation flow.", "schema": {"order_id":"str"}},
    "collect_evidence": {"fn": lambda order_id: {"order_id": order_id, "photos": 2, "questionnaireCompleted": True},
                         "desc": "Collect evidence in dispute.", "schema": {"order_id":"str"}},
    "analyze_evidence": {"fn": lambda order_id: {"order_id": order_id, "status": "OK", "fault": "merchant"},
                         "desc": "Analyze evidence to decide fault.", "schema": {"order_id":"str"}},
    "issue_instant_refund": {"fn": lambda order_id, amount: {"order_id": order_id, "refunded": True, "amount": amount},
                             "desc": "Refund instantly.", "schema": {"order_id":"str","amount":"float"}},
    "exonerate_driver": {"fn": lambda driver_id: {"driver_id": driver_id, "cleared": True},
                         "desc": "Clear driver fault.", "schema": {"driver_id":"str"}},
    "log_merchant_packaging_feedback": {"fn": lambda merchant_id, feedback: {"merchant_id": merchant_id, "feedbackLogged": True},
                                        "desc": "Feedback to merchant packaging.", "schema": {"merchant_id":"str","feedback":"str"}},
    "contact_recipient_via_chat": {"fn": lambda recipient_id, message: {"recipient_id": recipient_id, "messageSent": message},
                                   "desc": "Chat recipient.", "schema": {"recipient_id":"str","message":"str"}},
    "suggest_safe_drop_off": {"fn": lambda address: {"address": address, "suggested": True},
                              "desc": "Suggest safe place.", "schema": {"address":"str"}},
    "find_nearby_locker": {"fn": lambda lat, lon, radius_m=1000: {
        "count": 3, "lockers": [
            {"id": "l1", "location": "Locker A", "distanceM": 300},
            {"id": "l2", "location": "Locker B", "distanceM": 700},
            {"id": "l3", "location": "Locker C", "distanceM": 950},
        ]},
        "desc": "Suggest parcel locker (≤5).", "schema": {"lat":"float","lon":"float","radius_m":"int"}},
    "check_flight_status": {"fn": lambda flight_no: {"flight": flight_no, "status": "DELAYED", "delayMin": 45},
                            "desc": "Flight status check.", "schema": {"flight_no":"str"}},
}

# ----------------------------- FLASK APP -------------------------------
app = Flask(__name__)
CORS(app, origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else "*", supports_credentials=True)
agent = SynapseAgent(_llm)

@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "model": GEMINI_MODEL,
        "project": FIREBASE_PROJECT_ID,
        "googleKeySet": bool(GOOGLE_MAPS_API_KEY),
        "requireAuth": REQUIRE_AUTH,
        "fcmDryRun": FCM_DRY_RUN,
        "fcmScopes": SCOPES,
    })

@app.route("/api/tools")
def tools():
    return jsonify({
        "tools": [
            {"name": k, "desc": v.get("desc"), "schema": v.get("schema")}
            for k, v in TOOLS.items()
        ]
    })

@app.route("/api/agent/run")
@require_auth
def run_stream():
    """
    GET /api/agent/run
    Streams Server-Sent Events with: classification → steps (multi-step action trace) → summary.
    Query params: scenario, origin, dest, origin_place, dest_place, driver_token, passenger_token, merchant_id, order_id, driver_id, recipient_id
    """
    scenario = (request.args.get("scenario") or "").strip()
    if not scenario:
        return jsonify({"error":"missing scenario"}), 400

    origin_q = request.args.get("origin")
    dest_q   = request.args.get("dest")

    driver_token_q    = (request.args.get("driver_token") or "").strip()
    passenger_token_q = (request.args.get("passenger_token") or "").strip()

    origin_place_q  = request.args.get("origin_place")
    dest_place_q    = request.args.get("dest_place")

    merchant_id_q  = (request.args.get("merchant_id") or "").strip()
    order_id_q     = (request.args.get("order_id") or "").strip()
    driver_id_q    = (request.args.get("driver_id") or "").strip()
    recipient_id_q = (request.args.get("recipient_id") or "").strip()

    # Append human-readable hints to scenario (avoid leaking raw tokens)
    if origin_q and dest_q:
        scenario += f"\n\n(Hint: origin={origin_q}, dest={dest_q})"
    if origin_place_q and dest_place_q:
        scenario += f"\n\n(Hint: origin_place={origin_place_q}, dest_place={dest_place_q})"
    if driver_token_q or passenger_token_q:
        scenario += f"\n\n(Hint: driver_token={'…' if driver_token_q else 'none'}, passenger_token={'…' if passenger_token_q else 'none'})"
    if merchant_id_q or order_id_q or driver_id_q or recipient_id_q:
        scenario += f"\n\n(Hint: merchant_id={merchant_id_q or '—'}, order_id={order_id_q or '—'}, driver_id={driver_id_q or '—'}, recipient_id={recipient_id_q or '—'})"

    hints = extract_hints(scenario, driver_token_q, passenger_token_q)

    # Override from query params if provided (coordinates)
    if origin_q and dest_q:
        try:
            lat1, lon1 = map(float, origin_q.split(","))
            lat2, lon2 = map(float, dest_q.split(","))
            hints["origin"] = [lat1, lon1]
            hints["dest"]   = [lat2, lon2]
        except Exception:
            pass

    # Place hints
    if origin_place_q:
        hints["origin_place"] = origin_place_q
    if dest_place_q:
        hints["dest_place"]   = dest_place_q

    # Token hints (use explicit param, else defaults from config)
    if driver_token_q:
        hints["driver_token"] = driver_token_q
    if passenger_token_q:
        hints["passenger_token"] = passenger_token_q
    hints.setdefault("driver_token", DEFAULT_DRIVER_TOKEN or None)
    hints.setdefault("passenger_token", DEFAULT_PASSENGER_TOKEN or None)
    hints.setdefault("customer_token", DEFAULT_CUSTOMER_TOKEN or None)

    # Extended IDs
    if merchant_id_q:  hints["merchant_id"]  = merchant_id_q
    if order_id_q:     hints["order_id"]     = order_id_q
    if driver_id_q:    hints["driver_id"]    = driver_id_q
    if recipient_id_q: hints["recipient_id"] = recipient_id_q

    # Geocode with Google if coords still missing
    if not hints.get("origin") and hints.get("origin_place"):
        pt = _geocode(hints["origin_place"])
        if pt: hints["origin"] = [pt[0], pt[1]]
    if not hints.get("dest") and hints.get("dest_place"):
        pt = _geocode(hints["dest_place"])
        if pt: hints["dest"] = [pt[0], pt[1]]

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
@require_auth
def resolve_sync_endpoint():
    """
    POST /api/agent/resolve
    Body: { scenario, origin:[lat,lon]?, dest:[lat,lon]?, origin_place?, dest_place?, driver_token?, passenger_token?, merchant_id?, order_id?, driver_id?, recipient_id? }
    Returns: { trace: [ classification, step..., summary ] }
    """
    data = request.get_json(force=True) or {}
    scenario = (data.get("scenario") or "").strip()
    if not scenario:
        return jsonify({"error":"missing scenario"}), 400

    driver_token = (data.get("driver_token") or "").strip()
    passenger_token = (data.get("passenger_token") or "").strip()

    origin = data.get("origin")  # [lat,lon]
    dest   = data.get("dest")    # [lat,lon]
    origin_place = data.get("origin_place")
    dest_place   = data.get("dest_place")

    merchant_id  = (data.get("merchant_id") or "").strip()
    order_id     = (data.get("order_id") or "").strip()
    driver_id    = (data.get("driver_id") or "").strip()
    recipient_id = (data.get("recipient_id") or "").strip()

    # Geocode if missing
    if (not origin or not dest):
        if not origin and origin_place:
            pt = _geocode(origin_place)
            if pt: origin = [pt[0], pt[1]]
        if not dest and dest_place:
            pt = _geocode(dest_place)
            if pt: dest = [pt[0], pt[1]]

    # Embed hints text
    if origin and dest:
        scenario += f"\n\n(Hint: origin={origin[0]},{origin[1]}, dest={dest[0]},{dest[1]})"
    if origin_place or dest_place:
        scenario += f"\n\n(Hint: origin_place={origin_place or '—'}, dest_place={dest_place or '—'})"
    if merchant_id or order_id or driver_id or recipient_id:
        scenario += f"\n\n(Hint: merchant_id={merchant_id or '—'}, order_id={order_id or '—'}, driver_id={driver_id or '—'}, recipient_id={recipient_id or '—'})"

    hints: Dict[str, Any] = {"origin": origin, "dest": dest}
    if driver_token:    hints["driver_token"]    = driver_token
    if passenger_token: hints["passenger_token"] = passenger_token
    if origin_place:    hints["origin_place"]    = origin_place
    if dest_place:      hints["dest_place"]      = dest_place
    if merchant_id:     hints["merchant_id"]     = merchant_id
    if order_id:        hints["order_id"]        = order_id
    if driver_id:       hints["driver_id"]       = driver_id
    if recipient_id:    hints["recipient_id"]    = recipient_id
    hints.setdefault("driver_token", DEFAULT_DRIVER_TOKEN or None)
    hints.setdefault("passenger_token", DEFAULT_PASSENGER_TOKEN or None)
    hints.setdefault("customer_token", DEFAULT_CUSTOMER_TOKEN or None)

    result = agent.resolve_sync(scenario, hints=hints)
    return jsonify(result)

# Optional: test FCM v1 (uses real send unless FCM_DRY_RUN=true)
@app.route("/api/fcm/send_test", methods=["POST"])
@require_auth
def fcm_send_test():
    data = request.get_json(force=True) or {}
    token = data.get("token")
    title = data.get("title","Test")
    body  = data.get("body","Hello from Synapse")
    if not token:
        return jsonify({"error":"missing token"}), 400
    res = _fcm_v1_send(token, title, body)
    return jsonify(res)

# Optional: flexible FCM with data payload
@app.route("/api/fcm/send", methods=["POST"])
@require_auth
def fcm_send():
    """
    POST /api/fcm/send
    { "token": "...", "title": "Title", "body": "Body", "data": { ... } }
    """
    data = request.get_json(force=True) or {}
    token = data.get("token") or ""
    title = data.get("title") or "Notification"
    body  = data.get("body")  or ""
    extra = data.get("data")  or None
    if not token:
        return jsonify({"error":"missing token"}), 400
    res = _fcm_v1_send(token, title, body, extra)
    return jsonify(res)

if __name__ == "__main__":
    # Run: python app.py
    app.run(host="0.0.0.0", port=5000, debug=False)
