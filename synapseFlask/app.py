# --- Standard Library Imports ---
import os
import re
import json
import time
import math
import traceback
import logging
import uuid
import base64
import shutil
import mimetypes
from typing import Any, Dict, List, Optional
from functools import wraps
from threading import Lock

# --- Third-party Imports ---
import requests
from flask import Flask, request, jsonify, Response, g
from flask_cors import CORS
from werkzeug.utils import secure_filename

# ----------------------------- GLOBALS ---------------------------------
# In-memory store for clarification sessions
CLARIFY_SESSIONS: Dict[str, Any] = {}

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

# ---- Dummy orders store (used for driver reroute) --------------------
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

def _load_orders() -> Dict[str, Any]:
    """Loads the orders from the orders.json file."""
    if not os.path.exists(ORDERS_FILE):
        raise FileNotFoundError(f"Required data file not found: {ORDERS_FILE}")
    with open(ORDERS_FILE, "r") as f:
        return json.load(f)

def _save_orders(data: Dict[str, Any]) -> None:
    """Saves the provided order data to the orders.json file."""
    with open(ORDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ----------------------------- LLM (Gemini) ----------------------------
from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_API_KEY)

class LLMWrapper:
    def __init__(self, client, model):
        self.client = client
        self.model = model

    def generate_content(self, contents, **kwargs):
        # Support both string and list for backward compat
        if isinstance(contents, str):
            contents = [contents]
        return self.client.models.generate_content(
            model=self.model,
            contents=contents,
            **kwargs
        )

_llm = LLMWrapper(client, GEMINI_MODEL)

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
def http_get(url: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None, timeout: float = 20.0) -> Dict:
    """Performs an HTTP GET request and returns the JSON response."""
    r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
    r.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
    return r.json()

def http_post(url: str, json_body: Dict[str, Any], headers: Dict[str, str], timeout: float = 25.0) -> Dict:
    """Performs an HTTP POST request, handling errors gracefully."""
    try:
        r = requests.post(url, json=json_body, headers=headers, timeout=timeout)
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {"ok": True, "status": r.status_code}
        return r.json()
    except requests.exceptions.HTTPError as http_err:
        log.error(f"HTTP error occurred: {http_err} - {r.text}")
        return {"ok": False, "status": r.status_code, "error": "http_error", "details": r.text}
    except requests.exceptions.RequestException as req_err:
        log.error(f"Request failed: {req_err}")
        return {"ok": False, "error": "request_failed", "details": str(req_err)}

# ----------------------------- UTIL -----------------------------------
def now_iso() -> str:
    """Returns the current time in ISO 8601 format."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def sse(data: Any) -> str:
    """Formats data as a Server-Sent Event string."""
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
    return f"data: {payload}\n\n"

def safe_json(text: str, default: Any = None) -> Any:
    """Safely parses a JSON string, stripping markdown code blocks if present."""
    text = (text or "").strip()
    match = re.search(r"```(json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    json_str = match.group(2) if match else text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        log.warning("Failed to decode JSON.")
        return default if default is not None else {}

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the distance between two points on Earth in kilometers."""
    R = 6371.0088  # Earth radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2)**2
    return 2 * R * math.asin(math.sqrt(a))

# --- Interactive session storage ---
SESSIONS: Dict[str, Any] = {}
SESSIONS_LOCK = Lock()

def _session_save(session_id: str, payload: Dict[str, Any]) -> None:
    with SESSIONS_LOCK:
        SESSIONS[session_id] = payload

def _session_load(session_id: str) -> Optional[Dict[str, Any]]:
    with SESSIONS_LOCK:
        return SESSIONS.get(session_id)

def _session_delete(session_id: str) -> None:
    with SESSIONS_LOCK:
        SESSIONS.pop(session_id, None)

def _merge_answers(hints: Dict[str, Any], answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if answers and isinstance(answers, dict):
        existing = hints.get("answers", {})
        existing.update(answers)
        hints["answers"] = existing
    return hints

def _truthy_str(v: Any) -> Optional[bool]:
    """Converts a string-like value to a boolean, handling various truthy inputs."""
    if isinstance(v, bool): return v
    if v is None: return None
    s = str(v).strip().lower()
    if s in {"y", "yes", "true", "1"}: return True
    if s in {"n", "no", "false", "0"}: return False
    return None

# --- Evidence helpers ---
UPLOADS_ROOT = os.path.join(os.path.dirname(__file__), "uploads")
EVIDENCE_ROOT = os.path.join(os.path.dirname(__file__), "evidence")
os.makedirs(UPLOADS_ROOT, exist_ok=True)
os.makedirs(EVIDENCE_ROOT, exist_ok=True)

def _save_evidence_images(order_id: str, images: list[str] | None) -> list[str]:
    """Saves evidence images from various sources to a dedicated order directory."""
    saved_paths = []
    if not images:
        return saved_paths
    
    order_dir = os.path.join(EVIDENCE_ROOT, order_id)
    os.makedirs(order_dir, exist_ok=True)

    for i, src in enumerate(images):
        try:
            timestamp = int(time.time() * 1000)
            filepath_base = os.path.join(order_dir, f"evidence_{timestamp}_{i}")
            
            if isinstance(src, str) and src.startswith("data:image/"):
                header, b64_data = src.split(",", 1)
                mime_type = header.split(';')[0].split(':')[1]
                ext = mimetypes.guess_extension(mime_type) or ".jpg"
                filepath = filepath_base + ext
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(b64_data))
                saved_paths.append(filepath)

            # SECURITY FIX: Only allow copying files that are already in UPLOADS_ROOT
            elif isinstance(src, str) and os.path.exists(src):
                # Ensure the source path is within the allowed UPLOADS_ROOT directory
                if os.path.commonpath([os.path.abspath(src), UPLOADS_ROOT]) == UPLOADS_ROOT:
                    ext = os.path.splitext(src)[1] or ".jpg"
                    filepath = filepath_base + ext
                    shutil.copyfile(src, filepath)
                    saved_paths.append(filepath)
                else:
                    log.warning(f"Security: Blocked attempt to access unauthorized path: {src}")

        except Exception as e:
            log.warning(f"[evidence] Failed to save image source #{i} for order {order_id}: {e}")
            
    return saved_paths

def _load_evidence_files(order_id: str) -> list[str]:
    """Loads all evidence file paths for a given order, sorted by most recent."""
    order_dir = os.path.join(EVIDENCE_ROOT, order_id)
    if not os.path.isdir(order_dir):
        return []
    files = [os.path.join(order_dir, f) for f in os.listdir(order_dir) if os.path.isfile(os.path.join(order_dir, f))]
    files.sort(key=os.path.getmtime, reverse=True)
    return files

# -------------------------- HINT AND LOCATION HELPERS ---------------------------

HINT_RE_ORIGIN = re.compile(r"origin\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)
HINT_RE_DEST   = re.compile(r"dest\s*=\s*([0-9.+-]+)\s*,\s*([0-9.+-]+)", re.I)

def extract_hints(scenario: str, driver_token: Optional[str], passenger_token: Optional[str]) -> Dict[str, Any]:
    """
    Builds a dictionary of hints from the initial scenario text.
    It extracts numeric coordinates via regex and infers place names using an LLM helper.
    """
    hints: Dict[str, Any] = {"scenario_text": scenario}
    if driver_token:    hints["driver_token"] = driver_token
    if passenger_token: hints["passenger_token"] = passenger_token

    # Extract numeric coordinates (e.g., origin=13.0,80.2) if explicitly provided
    m1 = HINT_RE_ORIGIN.search(scenario)
    m2 = HINT_RE_DEST.search(scenario)
    if m1 and m2:
        hints["origin"] = [float(m1.group(1)), float(m1.group(2))]
        hints["dest"]   = [float(m2.group(1)), float(m2.group(2))]

    # Use Gemini to infer human-readable place names from the text
    rd = _gemini_route_from_text(scenario)
    if rd.get("origin_place"):
        hints["origin_place"] = rd["origin_place"]
    if rd.get("dest_place"):
        hints["dest_place"] = rd["dest_place"]

    return hints

# -------------------------- HELPER FUNCTIONS ---------------------------
# These are helper functions used by the main tools below.

def _gemini_route_from_text(scenario: str) -> Dict[str, Optional[str]]:
    """Asks Gemini to extract one origin and one destination place name from free text."""
    prompt = f'Extract origin and destination place names from the text. Return STRICT JSON only: {{"origin_place": "<origin>", "dest_place": "<destination>"}}\n\nScenario: {scenario}'
    try:
        resp = _llm.generate_content(prompt)
        return safe_json(getattr(resp, "text", ""), {})
    except Exception as e:
        log.error(f"[_gemini_route_from_text] failed: {e}")
        return {}

def _gemini_place_from_text(scenario: str) -> Optional[str]:
    """Extracts a single central place name from text to anchor "nearby" searches."""
    prompt = f'Extract ONE concise place name from the scenario. Return STRICT JSON only: {{"place_name": "<place>"}}\n\nScenario: {scenario}'
    try:
        resp = _llm.generate_content(prompt)
        data = safe_json(getattr(resp, "text", ""), {})
        return (data.get("place_name") or "").strip() or None
    except Exception as e:
        log.error(f"[_gemini_place_from_text] failed: {e}")
        return None

def _gemini_category_from_text(scenario: str) -> Optional[str]:
    """Maps free text to a predefined category for Google Places searches."""
    categories = ["mart", "club", "restaurant", "pharmacy", "hospital", "atm", "fuel", "grocery"]
    prompt = f'From the scenario, pick ONE category from this list: {json.dumps(categories)}. Return STRICT JSON only: {{"category": "<choice>"}}\n\nScenario: {scenario}'
    try:
        resp = _llm.generate_content(prompt)
        data = safe_json(getattr(resp, "text", ""), {})
        return (data.get("category") or "").strip().lower() or None
    except Exception as e:
        log.error(f"[_gemini_category_from_text] failed: {e}")
        return None

def _gm_headers(field_mask: Optional[str] = None) -> Dict[str, str]:
    """Constructs standard headers for Google Maps API calls."""
    h = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY, "Content-Type": "application/json"}
    if field_mask:
        h["X-Goog-FieldMask"] = field_mask
    return h

def _routes_post(path: str, body: dict, field_mask: str) -> dict:
    """Makes a POST request to the Google Routes API."""
    url = f"https://routes.googleapis.com/{path}"
    return http_post(url, body, headers=_gm_headers(field_mask))

def _places_post(path: str, body: dict, field_mask: str) -> dict:
    """Makes a POST request to the Google Places API."""
    url = f"https://places.googleapis.com/v1/{path}"
    return http_post(url, body, headers=_gm_headers(field_mask))

def _places_get(path: str, field_mask: str) -> dict:
    """Makes a GET request to the Google Places API."""
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

def _only_place_name(val: Any) -> Optional[str]:
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

def _purge_evidence(order_id: str) -> int:
    """Deletes all saved evidence files for an order. Returns count of removed files."""
    odir = os.path.join(EVIDENCE_ROOT, order_id)
    if not os.path.isdir(odir): return 0
    count = 0
    for f in os.listdir(odir):
        p = os.path.join(odir, f)
        try:
            if os.path.isfile(p):
                os.remove(p)
                count += 1
        except Exception as e:
            log.warning(f"[evidence] purge failed for {p}: {e}")
    return count

# -------------------------- TOOL DEFINITIONS ---------------------------
# These are the actual tools the agent can call.

def tool_notify_resolution(driver_token: Optional[str], customer_token: Optional[str], message: str) -> Dict[str, Any]:
    """Sends a final resolution notification to both the driver and the customer."""
    d_res = _fcm_v1_send(driver_token or "", "Dispute Resolution", message)
    c_res = _fcm_v1_send(customer_token or "", "Dispute Resolution", message)
    return {"driver_notified": d_res.get("delivered"), "customer_notified": c_res.get("delivered")}

def tool_initiate_mediation_flow(order_id: str) -> Dict[str, Any]:
    """Starts a dispute mediation flow by purging any old evidence for the order."""
    removed = _purge_evidence(order_id)
    return {"order_id": order_id, "flow": "started", "purgedFiles": removed}

def tool_collect_evidence(order_id: str, images: Optional[List[str]] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """Saves evidence images and notes for a given order."""
    saved = _save_evidence_images(order_id, images or [])
    # In a real app, notes would be saved to a database. Here we just acknowledge it.
    return {
        "order_id": order_id,
        "photos_saved": len(saved),
        "files": saved[-5:],
        "notes_provided": bool(notes),
    }

def tool_analyze_evidence(order_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
    """Analyzes evidence images using the vision model to determine fault."""
    image_files = _load_evidence_files(order_id)
    if not image_files:
        return {"order_id": order_id, "status": "NO_EVIDENCE", "rationale": "No images were found to analyze."}

    # Use the more efficient Part.from_uri for local files
    image_parts = [types.Part.from_uri(path, mime_type=(mimetypes.guess_type(path)[0] or "image/jpeg")) for path in image_files]
    
    prompt = (
        "You are a dispute resolution specialist for a delivery service. Analyze the provided images and notes for a damaged/spilled package. "
        "Determine the most likely party at fault (merchant, driver, or unclear). Provide a rationale and suggest feedback for the merchant if applicable. "
        "Return ONLY a valid JSON object with the following structure:\n"
        "{\n"
        '  "fault": "merchant|driver|unclear",\n'
        '  "confidence": <float from 0.0 to 1.0>,\n'
        '  "refund_reasonable": <true|false>,\n'
        '  "rationale": "A brief explanation for your decision.",\n'
        '  "packaging_feedback": "Constructive feedback for the merchant if their packaging was poor, otherwise null."\n'
        "}"
    )
    
    contents = [prompt] + image_parts
    if notes:
        contents.append(f"\nAdditional Notes: {notes}")

    try:
        response = _llm.generate_content(contents)
        data = safe_json(response.text, {})
        data["order_id"] = order_id
        data["status"] = "OK"
        return data
    except Exception as e:
        log.error(f"[tool_analyze_evidence] Gemini API call failed: {e}")
        return {"order_id": order_id, "status": "ERROR", "rationale": f"Model error: {e}"}

def tool_geocode_place(query: str) -> Dict[str, Any]:
    """Converts a query string (address or place name) into coordinates."""
    pt = _geocode(query)
    if not pt:
        return {"found": False, "query": query}
    return {"found": True, "lat": pt[0], "lon": pt[1], "query": query}

def tool_check_traffic(origin_any: Any, dest_any: Any, travel_mode: str = "DRIVE") -> Dict[str, Any]:
    """Gets traffic-aware ETA between two points (place names or coordinates)."""
    try:
        o_name = _only_place_name(origin_any) or f"{origin_any[0]},{origin_any[1]}"
        d_name = _only_place_name(dest_any) or f"{dest_any[0]},{dest_any[1]}"
        
        data = http_get("https://maps.googleapis.com/maps/api/directions/json",
            params={"origin": o_name, "destination": d_name, "mode": travel_mode.lower(), "departure_time": "now", "key": GOOGLE_MAPS_API_KEY})
        
        if data.get("status") != "OK":
            return {"error": "directions_failed", "status": data.get("status")}
        
        leg = data["routes"][0]["legs"][0]
        normal_sec = leg.get("duration", {}).get("value", 0)
        traffic_sec = (leg.get("duration_in_traffic") or {}).get("value", normal_sec)
        
        return {
            "status": "ok", "origin_place": leg.get("start_address"), "dest_place": leg.get("end_address"),
            "normalMin": round(normal_sec / 60, 1), "trafficMin": round(traffic_sec / 60, 1),
            "delayMin": round(max(0, (traffic_sec - normal_sec) / 60), 1), "summary": data["routes"][0].get("summary"),
        }
    except Exception as e:
        return {"error": f"traffic_check_failure:{e}"}

# ... (continuing from the previous code block)

def tool_calculate_alternative_route(origin_any: Any, dest_any: Any, travel_mode: str = "DRIVE") -> Dict[str, Any]:
    """
    Finds alternative routes and calculates the potential time saved compared to the default route.
    """
    try:
        o_name = _only_place_name(origin_any) or f"{origin_any[0]},{origin_any[1]}"
        d_name = _only_place_name(dest_any) or f"{dest_any[0]},{dest_any[1]}"

        data = http_get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params={
                "origin": o_name, "destination": d_name, "mode": travel_mode.lower(),
                "alternatives": "true", "departure_time": "now", "key": GOOGLE_MAPS_API_KEY
            }
        )

        if data.get("status") != "OK":
            return {"error": "directions_failed", "status": data.get("status")}
        
        routes_out = []
        traffic_times_min = []
        for route in data.get("routes", []):
            leg = route["legs"][0]
            traffic_sec = (leg.get("duration_in_traffic") or leg.get("duration", {})).get("value", 0)
            traffic_min = round(traffic_sec / 60, 1)
            routes_out.append({"summary": route.get("summary"), "trafficMin": traffic_min})
            traffic_times_min.append(traffic_min)
        
        if not traffic_times_min:
            return {"error": "no_routes_found"}

        current_route_time = traffic_times_min[0]
        best_route_time = min(traffic_times_min)
        improvement = round(max(0, current_route_time - best_route_time), 1)

        return {"status": "ok", "routes": routes_out, "improvementMin": improvement}
    except Exception as e:
        return {"error": f"alt_route_failure:{e}"}

def tool_compute_route_matrix(origins: List[Any], destinations: List[Any]) -> Dict[str, Any]:
    """MOCK: Returns a matrix of travel times between origins and destinations."""
    # This is a mock implementation. A real one would call the Routes API.
    if not origins or not destinations:
        return {"error": "missing origins or destinations"}
    return {
        "status": "ok",
        "matrix": [
            {"originIndex": 0, "destinationIndex": 0, "duration": "1200s", "distanceMeters": 5000}
        ]
    }

def tool_check_weather(lat: float, lon: float) -> Dict[str, Any]:
    """Gets current weather conditions for a specific location."""
    url = "https://weather.googleapis.com/v1/currentConditions:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return data.get("currentConditions", {})
    except Exception as e:
        return {"error": f"weather_failure:{str(e)}"}

def tool_air_quality(lat: float, lon: float) -> Dict[str, Any]:
    """Gets the current air quality index for a specific location."""
    url = "https://airquality.googleapis.com/v1/currentConditions:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        # The API returns a list of indexes, we typically only need the first one.
        return data.get("indexes", [{}])[0]
    except Exception as e:
        return {"error": f"air_quality_failure:{str(e)}"}

def tool_pollen_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Gets the pollen forecast for a specific location."""
    url = "https://pollen.googleapis.com/v1/forecast:lookup"
    params = {"location.latitude": lat, "location.longitude": lon, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return {"found": True, "dailyInfo": data.get("dailyInfo", [])[:3]} # Return forecast for next 3 days
    except Exception as e:
        return {"error": f"pollen_failure:{str(e)}"}

def tool_find_nearby_locker(place_name: str, radius_m: int = 2000) -> Dict[str, Any]:
    """Finds secure parcel lockers near a given place name."""
    coords = _geocode(place_name)
    if not coords:
        return {"count": 0, "lockers": [], "error": f"Could not find location for '{place_name}'"}
    
    lat, lon = coords
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lon}",
        "radius": radius_m,
        "keyword": "parcel locker OR package pickup",
        "key": GOOGLE_MAPS_API_KEY
    }
    try:
        data = http_get(url, params=params)
        lockers = [
            {"id": p.get("place_id"), "name": p.get("name"), "address": p.get("vicinity")}
            for p in data.get("results", [])
        ]
        return {"count": len(lockers), "lockers": lockers[:5]} # Return top 5
    except Exception as e:
        return {"count": 0, "lockers": [], "error": str(e)}

# --- Data for Places Search Tool ---
CATEGORY_TO_TYPES = {
    "mart":       ["convenience_store", "supermarket"],
    "grocery":    ["supermarket", "grocery_store"],
    "club":       ["night_club"],
    "restaurant": ["restaurant"],
    "pharmacy":   ["pharmacy"],
    "hospital":   ["hospital"],
    "atm":        ["atm"],
    "fuel":       ["gas_station"],
}
CATEGORY_KEYWORDS = {
    "mart": "convenience store", "grocery": "grocery supermarket", "club": "night club",
    "restaurant": "restaurant", "pharmacy": "pharmacy", "hospital": "hospital",
    "atm": "atm", "fuel": "gas station petrol pump",
}

def tool_places_search_nearby(
    lat: float, lon: float, category: str, radius_m: int = 2500, keyword: Optional[str] = None
) -> Dict[str, Any]:
    """Finds up to 5 nearby places based on a category and location."""
    body = {
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radius_m)}
        }
    }
    cat = (category or "").strip().lower()
    body["includedPrimaryTypes"] = CATEGORY_TO_TYPES.get(cat)
    body["keyword"] = keyword or CATEGORY_KEYWORDS.get(cat)

    if not body.get("includedPrimaryTypes") and not body.get("keyword"):
        return {"error": "invalid_category", "message": "A valid category or keyword is required."}

    field_mask = "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount"
    try:
        data = _places_post("places:searchNearby", body, field_mask)
        return {"count": len(data.get("places", [])), "places": data.get("places", [])}
    except Exception as e:
        return {"error": f"places_nearby_failure:{str(e)}"}

def tool_place_details(place_id: str) -> Dict[str, Any]:
    """Gets detailed information about a specific place using its Place ID."""
    field_mask = "id,displayName,formattedAddress,nationalPhoneNumber,websiteUri,rating,userRatingCount,priceLevel"
    try:
        return _places_get(f"places/{place_id}", field_mask)
    except Exception as e:
        return {"error": f"place_details_failure:{str(e)}"}

def tool_roads_snap(points: List[List[float]]) -> Dict[str, Any]:
    """Snaps a series of GPS coordinates to the nearest roads."""
    if not points or any(len(p) != 2 for p in points):
        return {"error": "invalid_points_format"}
    path = "|".join([f"{p[0]},{p[1]}" for p in points])
    url = "https://roads.googleapis.com/v1/snapToRoads"
    params = {"path": path, "interpolate": "true", "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return {"snappedPoints": data.get("snappedPoints", [])}
    except Exception as e:
        return {"error": f"roads_failure:{str(e)}"}

def tool_time_zone(lat: float, lon: float, timestamp: Optional[int] = None) -> Dict[str, Any]:
    """Gets the time zone for a specific location."""
    if not timestamp:
        timestamp = int(time.time())
    url = "https://maps.googleapis.com/maps/api/timezone/json"
    params = {"location": f"{lat},{lon}", "timestamp": timestamp, "key": GOOGLE_MAPS_API_KEY}
    try:
        data = http_get(url, params=params)
        return data if data.get("status") == "OK" else {"error": data.get("errorMessage")}
    except Exception as e:
        return {"error": f"time_zone_failure:{str(e)}"}

def tool_get_nearby_merchants(lat: float, lon: float, radius_m: int = 2000) -> Dict[str, Any]:
    """Uses Google Places to find up to 5 nearby restaurants."""
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lon}",
        "radius": radius_m,
        "type": "restaurant",
        "key": GOOGLE_MAPS_API_KEY,
    }
    try:
        data = http_get(url, params=params)
        merchants = [
            {
                "id": p.get("place_id"),
                "name": p.get("name"),
                "address": p.get("vicinity"),
                "rating": p.get("rating", 0),
                "user_ratings_total": p.get("user_ratings_total", 0),
            }
            for p in data.get("results", [])
        ]
        return {"count": len(merchants), "merchants": merchants[:5]} # Return top 5
    except Exception as e:
        log.error(f"[get_nearby_merchants] failed: {e}")
        return {"count": 0, "merchants": [], "error": str(e)}

def _estimate_trip_minutes(pick_lat: float, pick_lon: float, drop_lat: float, drop_lon: float) -> float:
    """Estimates travel time based on distance and a baseline speed."""
    dist_km = haversine_km(pick_lat, pick_lon, drop_lat, drop_lon)
    return round((dist_km / BASELINE_SPEED_KMPH) * 60.0, 1)

def tool_assign_short_nearby_order(driver_id: str, driver_lat: float, driver_lon: float,
                                   radius_km: float = 6.0, max_total_minutes: float = 25.0) -> Dict[str, Any]:
    """
    Finds and assigns the best quick, nearby order to a driver from the local orders file.
    """
    data = _load_orders()
    candidates = []
    for o in data.get("orders", []):
        if o.get("status") != "pending":
            continue
        
        p = o["pickup"]
        d = o["dropoff"]
        dist_to_pick = haversine_km(driver_lat, driver_lon, p["lat"], p["lon"])
        
        if dist_to_pick <= radius_km:
            job_minutes = _estimate_trip_minutes(p["lat"], p["lon"], d["lat"], d["lon"])
            total_minutes = round(job_minutes + (dist_to_pick / BASELINE_SPEED_KMPH) * 60.0, 1)
            if total_minutes <= max_total_minutes:
                candidates.append({
                    "order": o, "distToPickupKm": round(dist_to_pick, 2),
                    "jobMinutes": job_minutes, "totalMinutes": total_minutes
                })

    if not candidates:
        return {"assigned": False, "reason": "no_quick_orders_found"}

    # Choose the quickest total trip and assign it
    best = min(candidates, key=lambda c: c["totalMinutes"])
    for o in data["orders"]:
        if o["id"] == best["order"]["id"]:
            o["status"] = "assigned"
            o["assignedTo"] = driver_id
            break
    _save_orders(data)

    return {"assigned": True, "driver_id": driver_id, **best}

def tool_reroute_driver(driver_id: str, driver_lat: float, driver_lon: float) -> Dict[str, Any]:
    """A wrapper tool that assigns a short order and formats the response for the agent."""
    res = tool_assign_short_nearby_order(driver_id, driver_lat, driver_lon)
    if not res.get("assigned"):
        return {"driver_id": driver_id, "rerouted": False, "reason": res.get("reason")}
    
    o = res["order"]
    new_task = (f"Pickup {o['id']} at {o['pickup']['address']} -> "
                f"drop at {o['dropoff']['address']} (≈{res['totalMinutes']} min)")
    
    return {"driver_id": driver_id, "rerouted": True, "newTask": new_task, "assignment": res}
    
# ------------------------- NOTIFICATIONS (FCM v1) ---------------------
def _is_placeholder_token(token: str) -> bool:
    """Checks if a token is empty or a placeholder string."""
    t = (token or "").strip().lower()
    return (not t) or (t in {"token", "customer_token", "driver_token", "passenger_token", "str"})

def _fcm_v1_send(token: str, title: str, body: str, data: Optional[dict] = None) -> Dict[str, Any]:
    """
    Sends a push notification using the FCM v1 API.
    Handles dry runs, placeholder tokens, and errors gracefully.
    """
    if FCM_DRY_RUN:
        log.info(f"[FCM_DRY_RUN] To: {token}, Title: '{title}', Body: '{body}'")
        return {"delivered": True, "dryRun": True}

    if _is_placeholder_token(token):
        return {"delivered": False, "reason": "missing_or_placeholder_device_token"}

    try:
        access_token = _fcm_access_token()
        url = f"https://fcm.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/messages:send"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # This message structure is more universal and works for both mobile & web
        message_payload = {
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body,
                },
                # FCM requires all data payload values to be strings
                "data": {k: str(v) for k, v in (data or {}).items()}
            }
        }
        
        log.info(f"[FCM] Sending notification to token ending in ...{token[-6:]}")
        response = http_post(url, message_payload, headers, timeout=10)
        
        if response.get("ok", False) or "name" in response:
            return {"delivered": True, "fcmResponse": response}
        else:
            log.error(f"[FCM] Send failed: {response}")
            return {"delivered": False, "error": response}
            
    except Exception as e:
        log.error(f"[FCM] An exception occurred during send: {e}")
        return {"delivered": False, "error": str(e)}

def tool_notify_customer(fcm_token: Optional[str], message: str, voucher: bool = False, title: str = "Order Update") -> Dict[str, Any]:
    """A specific tool to send a notification to a customer."""
    return _fcm_v1_send(fcm_token or "", title, message, {"voucher": voucher})

def tool_notify_passenger_and_driver(driver_token: Optional[str], passenger_token: Optional[str], message: str) -> Dict[str, Any]:
    """A specific tool to send a synchronized notification to a passenger and a driver."""
    d_res = _fcm_v1_send(driver_token or "", "Route Update", message)
    p_res = _fcm_v1_send(passenger_token or "", "Route Update", message)
    return {"driver_notified": d_res.get("delivered"), "passenger_notified": p_res.get("delivered")}

# ----------------------------- ASSERTIONS ------------------------------
def check_assertion(assertion: Optional[str], observation: Dict[str, Any]) -> bool:
    """
    Checks if an observation from a tool call satisfies a given assertion string.
    """
    # If no assertion is provided, pass unless the tool returned an explicit error.
    if not assertion:
        return not ("error" in observation or "trace" in observation)

    # --- Helper for parsing boolean-like values ---
    def _truthy(v: Any) -> bool:
        if isinstance(v, bool): return v
        s = str(v).strip().lower()
        return s in {"true", "1", "yes", "y", "ok"}

    # --- A dictionary to map assertion keywords to check functions (lambdas) ---
    checks = {
        "response!=none": lambda obs: isinstance(obs, dict) and len(obs) > 0,
        "routes>=1":      lambda obs: isinstance(obs.get("routes"), list) and len(obs["routes"]) >= 1,
        "delivered==true":lambda obs: _truthy(obs.get("delivered")) or _truthy(obs.get("driver_notified")) or _truthy(obs.get("passenger_notified")),
        "improvementmin>0": lambda obs: isinstance(obs.get("improvementMin"), (int, float)) and obs["improvementMin"] > 0,
        "count>0":        lambda obs: isinstance(obs.get("count"), (int, float)) and obs["count"] > 0,
        "delaymin>=0":    lambda obs: isinstance(obs.get("delayMin"), (int, float)) and obs["delayMin"] >= 0,
        "found==true":    lambda obs: _truthy(obs.get("found")),
        "photos>0":       lambda obs: isinstance(obs.get("photos_saved"), (int, float)) and obs["photos_saved"] > 0,
        "flow==started":  lambda obs: obs.get("flow") == "started",
        "refunded==true": lambda obs: _truthy(obs.get("refunded")),
        "cleared==true":  lambda obs: _truthy(obs.get("cleared")),
        "feedbacklogged==true": lambda obs: _truthy(obs.get("feedbackLogged")),
        "suggested==true": lambda obs: _truthy(obs.get("suggested")),
        "status!=none":   lambda obs: obs.get("status") is not None,
        "merchants>0":    lambda obs: isinstance(obs.get("merchants"), list) and len(obs["merchants"]) > 0,
        "lockers>0":      lambda obs: isinstance(obs.get("lockers"), list) and len(obs["lockers"]) > 0,
        "messagesent!=none": lambda obs: obs.get("messageSent") is not None,
    }

    # Sanitize the assertion string for matching
    key = str(assertion).strip().lower().replace(" ", "")
    
    # Execute the check if the key exists
    if key in checks:
        return checks[key](observation)

    # Fallback for simple "key==value" checks
    if "==" in key:
        k, v = key.split("==", 1)
        obs_val = observation.get(k)
        if v in {"true", "false"}:
            return _truthy(obs_val) == (v == "true")
        try:
            return float(obs_val) == float(v)
        except (ValueError, TypeError):
            return str(obs_val).lower() == v

    log.warning(f"Unknown assertion '{assertion}', defaulting to pass.")
    return True

# ----------------------------- PROMPTS --------------------------------
# This section is well-designed and requires no changes.
KIND_LABELS = [
    "merchant_capacity", "recipient_unavailable", "traffic", "damage_dispute",
    "payment_issue", "address_issue", "weather", "safety", "other", "unknown"
]

CLASSIFY_PROMPT = """
You are Synapse, an expert last-mile logistics coordinator.

Your task is to classify the given scenario into:
- kind → one of {labels}
- severity → one of ["low", "med", "high"]

Rules:
- Always choose the closest matching kind from the list.
- traffic → jams, accidents, closures, rerouting. Classify normal trip requests as 'traffic'.
- merchant_capacity → restaurant delays, long prep times.
- recipient_unavailable → not home, unreachable.
- damage_dispute → spills, broken seals, packaging fault.
- payment_issue → payment failed or requires re-authorization.
- address_issue → wrong address, pin mismatch.
- weather → rain, flooding, or other weather affecting the trip.
- safety → crash, unsafe area, emergency.
- other → none of the above.

Output STRICT JSON only (no prose), for example:
{{
  "kind": "traffic",
  "severity": "high"
}}

Scenario:
{scenario}
"""

# ----------------------------- POLICY RAILS (extended) -----------------
def _policy_next_extended(kind: str, steps_done: int, hints: Dict[str, Any]) -> Optional[tuple]:
    """
    Determines the agent's next step based on the scenario kind and progress.
    This function contains the core, rule-based logic for the Synapse agent.

    Returns:
      A tuple containing: (intent, tool, params, assertion, finish_reason, final_message, reason)
      or None if the flow is complete or unhandled.
    """
    # ------------------------- TRAFFIC POLICY --------------------------
    if kind == "traffic":
        scen = hints.get("scenario_text") or ""
        origin_any = hints.get("origin_place") or hints.get("origin")
        dest_any   = hints.get("dest_place")   or hints.get("dest")
        
        if not origin_any or not dest_any:
            return ("end flow", "none", {}, None, "final", "Cannot resolve traffic without a clear origin and destination.", "Missing origin/destination.")

        # Step 0: Check initial congestion and delay
        if steps_done == 0:
            return (
                "check congestion", "check_traffic",
                {"origin_any": origin_any, "dest_any": dest_any},
                "delayMin>=0", "continue", None, "Measure baseline ETA and traffic delay."
            )
        # Step 1: Calculate alternative routes
        if steps_done == 1:
            return (
                "calculate alternatives", "calculate_alternative_route",
                {"origin_any": origin_any, "dest_any": dest_any},
                "improvementMin>=0", "continue", None, "Compute alternatives to find a faster route."
            )
        # [cite_start]Step 2: Provide context by checking flight status if applicable [cite: 74]
        if steps_done == 2:
            flight_match = re.search(r"flight\s+([A-Z0-9]+)", scen, re.IGNORECASE)
            if flight_match:
                return (
                    "check flight status", "check_flight_status",
                    {"flight_no": flight_match.group(1)},
                    None, "continue", None, "Checking flight status to provide passenger context."
                )
            return ("skip flight check", "none", {}, None, "continue", None, "No flight number mentioned in scenario.")
        
        # Step 3: Notify both parties with the complete information
        if steps_done == 3:
            flight_status = hints.get("flight_status", {})
            msg = "We've detected heavy traffic and found a faster route. Your ETA has been updated."
            if flight_status.get("status") == "DELAYED":
                msg += f" FYI: We noticed your flight {flight_status.get('flight')} is also delayed by {flight_status.get('delayMin')} minutes."
            
            return (
                "inform both parties", "notify_passenger_and_driver",
                {"driver_token": hints.get("driver_token"), "passenger_token": hints.get("passenger_token"), "message": msg},
                "delivered==true", "final", "Reroute applied; driver and passenger notified with all context.", "Notify both parties with the updated route and flight status if available."
            )

    # --------------------- MERCHANT CAPACITY POLICY --------------------
    if kind == "merchant_capacity":
        customer_token = hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN
        driver_id = hints.get("driver_id", "driver_demo")
        lat, lon = (hints.get("origin") or [13.0827, 80.2707]) # Default to Chennai if no coords

        # Step 0: Proactively notify the customer of the delay and offer a voucher
        if steps_done == 0:
            return (
                "notify customer of delay", "notify_customer",
                {"fcm_token": customer_token, "message": "The restaurant is facing a long prep time. We are working to minimize your wait and have applied a voucher for the inconvenience.", "voucher": True, "title": "Order Delay"},
                "delivered==true", "continue", None, "Proactively inform customer and offer voucher."
            )
        # Step 1: Optimize driver's time by rerouting them to a short, nearby delivery
        if steps_done == 1:
            return (
                "reroute driver", "reroute_driver",
                {"driver_id": driver_id, "driver_lat": lat, "driver_lon": lon},
                None, "continue", None, "Reduce driver idle time by assigning a temporary nearby task."
            )
        # Step 2: Suggest alternative merchants to the customer
        if steps_done == 2:
            return (
                "suggest alternatives", "get_nearby_merchants",
                {"lat": lat, "lon": lon},
                "merchants>0", "final", "Customer has been notified and offered alternative merchants.", "Fetch and suggest faster nearby restaurants."
            )

    # ---------------------- DAMAGE DISPUTE POLICY ----------------------
# ---------------------- DAMAGE DISPUTE POLICY (Corrected) ----------------------
    if kind == "damage_dispute":
        order_id = hints.get("order_id", "order_demo")
        driver_id = hints.get("driver_id", "driver_demo")
        merchant_id = hints.get("merchant_id", "merchant_demo")
        customer_token = hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN
        driver_token = hints.get("driver_token") or DEFAULT_DRIVER_TOKEN

        # Step 0: Initiate the mediation flow
        if steps_done == 0:
            return ("start mediation", "initiate_mediation_flow", {"order_id": order_id}, "flow==started", "continue", None, "Start structured mediation.")
        
        # Step 1: Request evidence from the user
        elif steps_done == 1:
            return ("request evidence", "ask_user", {"question_id": "evidence_images", "question": "Please upload photos of the item, packaging, and any seals.", "expected": "image[]"}, None, "await_input", None, "Awaiting photos to proceed.")
        
        # Step 2: Collect and log the evidence uploaded by the user
        elif steps_done == 2:
            return ("collect evidence", "collect_evidence", {"order_id": order_id}, "photos>0", "continue", None, "Collect and persist provided evidence.")
        
        # Step 3: Analyze evidence with the vision model
        elif steps_done == 3:
            return ("analyze evidence", "analyze_evidence", {"order_id": order_id}, "status!=none", "continue", None, "Use AI to analyze evidence and determine cause.")
        
        # Step 4: Make a decision based on the analysis
        elif steps_done == 4:
            analysis = hints.get("analysis", {})
            if analysis.get("refund_reasonable"):
                return ("issue refund", "issue_instant_refund", {"order_id": order_id}, "refunded==true", "continue", None, "Analysis suggests a refund is reasonable.")
            else:
                msg = analysis.get("rationale", "After review, a refund could not be approved based on the provided evidence.")
                return ("decline refund", "notify_customer", {"fcm_token": customer_token, "message": msg, "title": "Damage Claim Update"}, None, "final", msg, "Inform customer of decline.")
        
        # Step 5: Exonerate the driver if the merchant was at fault
        elif steps_done == 5:
            analysis = hints.get("analysis", {})
            if analysis.get("fault") == "merchant":
                return ("exonerate driver", "exonerate_driver", {"driver_id": driver_id}, "cleared==true", "continue", None, "Merchant found at fault; clearing driver.")
            return ("skip exoneration", "none", {}, None, "continue", None, "Fault not assigned to the merchant.")
        
        # Step 6: Log packaging feedback for the merchant if they were at fault
        elif steps_done == 6:
            analysis = hints.get("analysis", {})
            feedback = analysis.get("packaging_feedback")
            if analysis.get("fault") == "merchant" and feedback:
                return ("log merchant feedback", "log_merchant_packaging_feedback", {"merchant_id": merchant_id, "feedback": feedback}, "feedbacklogged==true", "continue", None, "Logging evidence-backed feedback for the merchant.")
            return ("skip feedback", "none", {}, None, "continue", None, "No merchant feedback required.")
        
        # Step 7: Communicate final resolution to both parties
        elif steps_done == 7:
            return ("notify resolution", "tool_notify_resolution", {"driver_token": driver_token, "customer_token": customer_token, "message": "The damage dispute has been resolved. A refund has been issued."}, None, "final", "Resolution communicated to all parties.", "Finalizing the dispute.")
    # ------------------ RECIPIENT UNAVAILABLE POLICY -------------------
    if kind == "recipient_unavailable":
        answers = hints.get("answers", {})
        
        # Step 0: Attempt to contact the recipient
        if steps_done == 0:
            return ("contact recipient", "contact_recipient_via_chat", {"recipient_id": "recipient_demo", "message": "Your GrabExpress driver has arrived with your package."}, "messagesent!=none", "continue", None, "Attempting to contact the recipient via chat.")
        
        # Step 1: Ask for permission for a safe drop-off
        safe_drop_ok = _truthy_str(answers.get("safe_drop_ok"))
        if safe_drop_ok is None:
            return ("ask for safe drop permission", "ask_user", {"question_id": "safe_drop_ok", "question": "The recipient is unavailable. Is it okay to leave the package with a building concierge or neighbor?", "expected": "boolean"}, None, "await_input", None, "Awaiting user/sender permission for a safe drop.")
        
        # If safe drop is approved, execute and finish
        if safe_drop_ok:
            return ("perform safe drop", "suggest_safe_drop_off", {"address": "Concierge / Building Security"}, "suggested==true", "final", "Package left with concierge as per sender's instruction.", "Perform safe drop-off.")
        
        # Step 2: If safe drop is not approved, find a nearby locker
        return ("find nearby locker", "find_nearby_locker", {"place_name": hints.get("dest_place", "nearby")}, "lockers>0", "final", "We've located a nearby secure locker as an alternative delivery point.", "Suggest a secure locker as a fallback.")

    # --------------------- OTHER GENERIC POLICIES ----------------------
    if kind in ["weather", "safety"]:
        if steps_done == 0:
            if kind == "weather":
                lat, lon = (hints.get("origin") or hints.get("dest") or [13.0827, 80.2707])
                return ("assess weather", "check_weather", {"lat": lat, "lon": lon}, None, "continue", None, "Checking weather conditions at location.")
            else: # Safety
                return ("escalate safety issue", "none", {}, None, "final", "Safety concern acknowledged. This issue has been escalated to a human agent for immediate review.", "Escalating safety issue to human support.")
        if steps_done == 1 and kind == "weather":
            obs = hints.get("weather_obs", {})
            msg = f"Weather Alert: Conditions report '{obs.get('shortText')}'. Please expect potential delays and proceed with caution."
            return ("notify user of weather", "notify_customer", {"fcm_token": hints.get("customer_token"), "title": "Weather Alert", "message": msg}, None, "final", msg, "Informing user of adverse weather.")

    if kind in ["payment_issue", "address_issue"] and steps_done == 0:
        q_text = f"We've detected a potential {kind.replace('_', ' ')}. Please open the app to provide more details or correct the information."
        return ("request clarification", "notify_customer", {"fcm_token": hints.get("customer_token"), "title": "Action Required", "message": q_text}, None, "final", "Awaiting user action to resolve the issue.", "Requesting user input via notification.")

    # Fallback for unhandled kinds or completed flows
    return None

# ----------------------------- AGENT -----------------------------------
class SynapseAgent:
    """
    Full agent with deterministic policy rails and streaming.
    This class orchestrates the classification and step-by-step resolution of a scenario.
    """
    def __init__(self, llm):
        self.llm = llm

    def classify(self, scenario: str) -> Dict[str, Any]:
        """Classifies the scenario using the predefined prompt."""
        prompt = CLASSIFY_PROMPT.format(labels=json.dumps(KIND_LABELS), scenario=scenario)
        try:
            resp = self.llm.generate_content(prompt)
            # Use the robust safe_json helper for parsing
            return safe_json(getattr(resp, "text", ""), {"kind": "unknown", "severity": "med"})
        except Exception as e:
            log.error(f"[gemini_error:classify] {e}")
            return {"kind": "unknown", "severity": "med"}

    def resolve_stream(
        self,
        scenario: str,
        hints: Optional[Dict[str, Any]] = None,
        *,
        session_id: Optional[str] = None,
        start_at_step: int = 0
    ):
        """
        Streams the step-by-step resolution of a scenario.
        Yields events for session start, classification, each step, and a final summary.
        """
        t0 = time.time()
        hints = hints or {}
        sid = session_id or str(uuid.uuid4())

        yield {"type": "session", "at": now_iso(), "data": {"session_id": sid}}

        cls = self.classify(scenario)
        kind = cls.get("kind", "other")
        yield {"type": "classification", "at": now_iso(), "data": cls}
        
        time.sleep(STREAM_DELAY)

        steps = max(0, int(start_at_step))
        last_final_message = "Flow completed without a final resolution message."

        while steps < MAX_STEPS and (time.time() - t0) < MAX_SECONDS:
            step_data = _policy_next_extended(kind, steps, hints)
            if not step_data:
                break

            intent, tool, params, assertion, finish_reason, final_message, reason = step_data
            obs = {}

            if tool not in ("none", "ask_user"):
                try:
                    fn = TOOLS[tool]["fn"]
                    obs = fn(**(params or {}))
                    # Stash key observations in hints for use in later policy steps
                    if tool == "analyze_evidence": hints["analysis"] = obs
                    if tool == "check_flight_status": hints["flight_status"] = obs
                    if tool == "check_weather": hints["weather_obs"] = obs
                except Exception as e:
                    obs = {"error": str(e), "traceback": traceback.format_exc()}
            
            yield {
                "type": "step", "at": now_iso(), "data": {
                    "index": steps, "intent": intent, "tool": tool, "params": params,
                    "assertion": assertion, "observation": obs, "passed": check_assertion(assertion, obs),
                    "reason": reason,
                }
            }
            
            steps += 1
            if finish_reason:
                if final_message: last_final_message = final_message
                if finish_reason == "await_input":
                    _session_save(sid, {"scenario": scenario, "hints": hints, "steps_done": steps, "kind": kind})
                    yield {"type": "clarify", "at": now_iso(), "data": {"session_id": sid, **(params or {})}}
                break
        
        _session_delete(sid)
        yield {
            "type": "summary", "at": now_iso(), "data": {
                "outcome": "resolved", "message": last_final_message,
                "metrics": {"totalSeconds": int(time.time() - t0), "steps": steps}
            }
        }

    def resolve_sync(self, scenario: str, hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Synchronous version of resolve_stream for simple API calls."""
        trace = [evt for evt in self.resolve_stream(scenario, hints=hints or {})]
        return {"trace": trace}

# ----------------------------- TOOL REGISTRY ---------------------------
TOOLS: Dict[str, Dict[str, Any]] = {
    # --- Alphabetized for easy reference ---
    "air_quality": {
        "fn": tool_air_quality, "desc": "Gets current air quality.", "schema": {"lat": "float", "lon": "float"}
    },
    "analyze_evidence": {
        "fn": tool_analyze_evidence, "desc": "Analyzes evidence with Gemini Vision.", "schema": {"order_id":"str","notes":"str?"}
    },
    "ask_user": {
        "fn": lambda **kwargs: {"awaiting": True, **kwargs}, "desc": "Pauses and asks the user for input.",
        "schema": {"question_id": "str", "question": "str", "expected": "str?", "options": "list[str]?"}
    },
    "assign_short_nearby_order": {
        "fn": tool_assign_short_nearby_order, "desc": "Assigns a quick nearby order from a local file.",
        "schema": {"driver_id": "str", "driver_lat": "float", "driver_lon": "float"}
    },
    "calculate_alternative_route": {
        "fn": tool_calculate_alternative_route, "desc": "Finds alternative routes.", "schema": {"origin_any": "str", "dest_any": "str"}
    },
    "check_flight_status": {
        "fn": lambda flight_no: {"flight": flight_no, "status": "DELAYED", "delayMin": 45},
        "desc": "MOCK: Checks the status of a flight.", "schema": {"flight_no":"str"}
    },
    "check_traffic": {
        "fn": tool_check_traffic, "desc": "Checks traffic-aware ETA.", "schema": {"origin_any": "str", "dest_any": "str"}
    },
    "check_weather": {
        "fn": tool_check_weather, "desc": "Gets current weather conditions.", "schema": {"lat": "float", "lon": "float"}
    },
    "collect_evidence": {
        "fn": tool_collect_evidence, "desc": "Collects evidence photos & notes.", "schema": {"order_id":"str","images":"list[str]?","notes":"str?"}
    },
    "compute_route_matrix": {
        "fn": tool_compute_route_matrix, "desc": "Calculates a matrix of travel times.", "schema": {"origins": "[any,...]", "destinations": "[any,...]"}
    },
    "contact_recipient_via_chat": {
        "fn": lambda rid, msg: {"recipient_id": rid, "messageSent": True}, "desc": "Contacts a recipient via chat.", "schema": {"recipient_id":"str", "message":"str"}
    },
    "exonerate_driver": {
        "fn": lambda driver_id: {"driver_id": driver_id, "cleared": True}, "desc": "Clears a driver of fault in a dispute.", "schema": {"driver_id":"str"}
    },
    "find_nearby_locker": {
        "fn": tool_find_nearby_locker, "desc": "Finds a nearby parcel locker.", "schema": {"place_name": "str", "radius_m": "int"}
    },
    "geocode_place": {
        "fn": tool_geocode_place, "desc": "Geocodes a place/address string.", "schema": {"query": "str"}
    },
    "get_merchant_status": {
        "fn": lambda mid: {"merchant_id": mid, "prepTimeMin": 40}, "desc": "MOCK: Gets merchant prep time.", "schema": {"merchant_id":"str"}
    },
    "get_nearby_merchants": {
        "fn": tool_get_nearby_merchants, "desc": "Finds nearby alternative merchants.", "schema": {"lat": "float", "lon": "float"}
    },
    "initiate_mediation_flow": {
        "fn": tool_initiate_mediation_flow, "desc": "Starts a dispute mediation flow.", "schema": {"order_id":"str"}
    },
    "issue_instant_refund": {
        "fn": lambda order_id: {"order_id": order_id, "refunded": True}, "desc": "Issues an instant refund.", "schema": {"order_id":"str"}
    },
    "log_merchant_packaging_feedback": {
        "fn": lambda mid, f: {"merchant_id": mid, "feedbackLogged": True}, "desc": "Logs packaging feedback for a merchant.", "schema": {"merchant_id":"str", "feedback":"str"}
    },
    "notify_customer": {
        "fn": tool_notify_customer, "desc": "Sends a push notification to a customer.", "schema": {"fcm_token":"str", "message":"str", "title":"str", "voucher":"bool?"}
    },
    "notify_passenger_and_driver": {
        "fn": tool_notify_passenger_and_driver, "desc": "Notifies both passenger and driver.", "schema": {"driver_token":"str", "passenger_token":"str", "message":"str"}
    },
    "notify_resolution": {
        "fn": tool_notify_resolution, "desc": "Notifies parties of a dispute resolution.", "schema": {"driver_token":"str", "customer_token":"str", "message":"str"}
    },
    "place_details": {
        "fn": tool_place_details, "desc": "Gets details for a specific place.", "schema": {"place_id": "str"}
    },
    "places_search_nearby": {
        "fn": tool_places_search_nearby, "desc": "Performs a nearby search for places.", "schema": {"lat":"float", "lon":"float", "category":"str"}
    },
    "pollen_forecast": {
        "fn": tool_pollen_forecast, "desc": "Gets the pollen forecast.", "schema": {"lat": "float", "lon": "float"}
    },
    "reroute_driver": {
        "fn": tool_reroute_driver, "desc": "Reroutes a driver to a short nearby order.", "schema": {"driver_id": "str", "driver_lat": "float", "driver_lon": "float"}
    },
    "roads_snap": {
        "fn": tool_roads_snap, "desc": "Snaps GPS points to the nearest roads.", "schema": {"points": "[[lat,lon],...]"}
    },
    "suggest_safe_drop_off": {
        "fn": lambda address: {"address": address, "suggested": True}, "desc": "Suggests a safe drop-off location.", "schema": {"address":"str"}
    },
    "time_zone": {
        "fn": tool_time_zone, "desc": "Gets the time zone for a location.", "schema": {"lat": "float", "lon": "float"}
    },
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
    GET /api/agent/run  (SSE)
    First run:
      - scenario: the scenario text
      - (optional) origin, dest (numeric "lat,lon")
      - (optional) driver_token, passenger_token, merchant_id, order_id, driver_id, recipient_id
      - (optional) answers: JSON string to seed answers
    Resume:
      - session_id: id from a previous run where we emitted "clarify"
      - answers: JSON string with the user's responses (e.g., {"safe_drop_ok":"yes"})
    """
    scenario_q = (request.args.get("scenario") or "").strip()
    session_id_q = (request.args.get("session_id") or request.args.get("resume_session") or "").strip()
    answers_q = request.args.get("answers")
    answers_dict = safe_json(answers_q, {}) if answers_q else {}

    # ---------- Resume flow ----------
    if session_id_q:
        session = _session_load(session_id_q)
        if not session:
            return jsonify({"error": "invalid_session"}), 400
        scenario = session["scenario"]
        hints = session["hints"] or {}
        start_at = int(session.get("steps_done", 0))

        _merge_answers(hints, answers_dict)

        # Allow token overrides on resume
        driver_token_q    = (request.args.get("driver_token") or "").strip()
        passenger_token_q = (request.args.get("passenger_token") or "").strip()
        customer_token_q  = (request.args.get("customer_token") or "").strip()  # <-- add

        if driver_token_q:    hints["driver_token"] = driver_token_q
        if passenger_token_q: hints["passenger_token"] = passenger_token_q
        if customer_token_q:  hints["customer_token"] = customer_token_q        # <-- add


        def generate():
            try:
                for evt in agent.resolve_stream(
                    scenario,
                    hints=hints,
                    session_id=session_id_q,
                    start_at_step=start_at,
                    resume=True,
                ):
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

    # ---------- First run ----------
    scenario = scenario_q
    if not scenario:
        return jsonify({"error":"missing scenario"}), 400

    origin_q = request.args.get("origin")
    dest_q   = request.args.get("dest")

    driver_token_q    = (request.args.get("driver_token") or "").strip()
    passenger_token_q = (request.args.get("passenger_token") or "").strip()
    customer_token_q  = (request.args.get("customer_token") or "").strip()

    merchant_id_q  = (request.args.get("merchant_id") or "").strip()
    order_id_q     = (request.args.get("order_id") or "").strip()
    driver_id_q    = (request.args.get("driver_id") or "").strip()
    recipient_id_q = (request.args.get("recipient_id") or "").strip()

    # Append human-readable hints (avoid leaking raw tokens)
    if origin_q and dest_q:
        scenario += f"\n\n(Hint: origin={origin_q}, dest={dest_q})"
    if driver_token_q or passenger_token_q or customer_token_q:
        scenario += (
            "\n\n(Hint: driver_token="
            f"{'…' if driver_token_q else 'none'}, passenger_token="
            f"{'…' if passenger_token_q else 'none'}, customer_token="
            f"{'…' if customer_token_q else 'none'})"
        )
    if merchant_id_q or order_id_q or driver_id_q or recipient_id_q:
        scenario += f"\n\n(Hint: merchant_id={merchant_id_q or '—'}, order_id={order_id_q or '—'}, driver_id={driver_id_q or '—'}, recipient_id={recipient_id_q or '—'})"

    # Build base hints (Gemini will infer origin/dest places inside extract_hints)
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

    # Token hints
    if driver_token_q:
        hints["driver_token"] = driver_token_q
    if passenger_token_q:
        hints["passenger_token"] = passenger_token_q
    if customer_token_q:
        hints["customer_token"] = customer_token_q
    hints.setdefault("driver_token", DEFAULT_DRIVER_TOKEN or None)
    hints.setdefault("passenger_token", DEFAULT_PASSENGER_TOKEN or None)
    hints.setdefault("customer_token", DEFAULT_CUSTOMER_TOKEN or None)

    # Extended IDs
    if merchant_id_q:  hints["merchant_id"]  = merchant_id_q
    if order_id_q:     hints["order_id"]     = order_id_q
    if driver_id_q:    hints["driver_id"]    = driver_id_q
    if recipient_id_q: hints["recipient_id"] = recipient_id_q

    # If Gemini inferred origin/dest *place names*, geocode to coords when coords missing
    if not hints.get("origin") and hints.get("origin_place"):
        pt = _geocode(hints["origin_place"])
        if pt: hints["origin"] = [pt[0], pt[1]]
    if not hints.get("dest") and hints.get("dest_place"):
        pt = _geocode(hints["dest_place"])
        if pt: hints["dest"] = [pt[0], pt[1]]

    # Merge any provided answers on first run too
    _merge_answers(hints, answers_dict)

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
    Body: {
      scenario?, session_id?, answers?,
      origin:[lat,lon]?, dest:[lat,lon]?,
      driver_token?, passenger_token?,
      merchant_id?, order_id?, driver_id?, recipient_id?
    }
    Returns: { trace: [ classification, step..., summary ] }
    """
    data = request.get_json(force=True) or {}

    # Resume mode
    session_id = (data.get("session_id") or "").strip()
    answers    = data.get("answers") or {}
    if session_id:
        session = _session_load(session_id)
        if not session:
            return jsonify({"error":"invalid_session"}), 400
        scenario = session["scenario"]
        hints = session["hints"] or {}
        _merge_answers(hints, answers)
        result = agent.resolve_sync(scenario, hints=hints)
        return jsonify(result)

    # First-run mode
    scenario = (data.get("scenario") or "").strip()
    if not scenario:
        return jsonify({"error":"missing scenario"}), 400

    driver_token = (data.get("driver_token") or "").strip()
    passenger_token = (data.get("passenger_token") or "").strip()
    customer_token   = (data.get("customer_token") or "").strip()

    origin = data.get("origin")  # [lat,lon]
    dest   = data.get("dest")    # [lat,lon]

    merchant_id  = (data.get("merchant_id") or "").strip()
    order_id     = (data.get("order_id") or "").strip()
    driver_id    = (data.get("driver_id") or "").strip()
    recipient_id = (data.get("recipient_id") or "").strip()

    # Embed hints text for numeric coords only
    if origin and dest:
        scenario += f"\n\n(Hint: origin={origin[0]},{origin[1]}, dest={dest[0]},{dest[1]})"
    if merchant_id or order_id or driver_id or recipient_id:
         scenario += f"\n\n(Hint: merchant_id={merchant_id or '—'}, order_id={order_id or '—'}, driver_id={driver_id or '—'}, recipient_id={recipient_id or '—'})"
    if driver_token or passenger_token or customer_token:
        scenario += (
            "\n\n(Hint: driver_token="
            f"{'…' if driver_token else 'none'}, passenger_token="
            f"{'…' if passenger_token else 'none'}, customer_token="
            f"{'…' if customer_token else 'none'})"
        )
    # Base hints
    hints: Dict[str, Any] = {"origin": origin, "dest": dest}
    if driver_token:    hints["driver_token"]    = driver_token
    if passenger_token: hints["passenger_token"] = passenger_token
    if merchant_id:     hints["merchant_id"]     = merchant_id
    if order_id:        hints["order_id"]        = order_id
    if driver_id:       hints["driver_id"]       = driver_id
    if recipient_id:    hints["recipient_id"]    = recipient_id
    hints.setdefault("driver_token", DEFAULT_DRIVER_TOKEN or None)
    hints.setdefault("passenger_token", DEFAULT_PASSENGER_TOKEN or None)
    hints.setdefault("customer_token", DEFAULT_CUSTOMER_TOKEN or None)

    # Let Gemini infer origin/dest *place names*; then geocode if coords are missing
    h2 = extract_hints(scenario, hints.get("driver_token"), hints.get("passenger_token"))
    hints.update({k: v for k, v in h2.items() if v})

    if not hints.get("origin") and hints.get("origin_place"):
        pt = _geocode(hints["origin_place"])
        if pt: hints["origin"] = [pt[0], pt[1]]
    if not hints.get("dest") and hints.get("dest_place"):
        pt = _geocode(hints["dest_place"])
        if pt: hints["dest"] = [pt[0], pt[1]]

    _merge_answers(hints, answers)

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

# helpers near the top
def _parse_answer(raw, expected):
    if expected in {"image[]", "string[]"}:
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return [raw] if raw else []
    if expected == "boolean":
        s = str(raw).strip().lower()
        return s in {"1","true","yes","y"}
    return raw

def _sse_headers():
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

@app.route("/api/agent/clarify/continue", methods=["GET","POST","OPTIONS"])
@require_auth
def clarify_continue():
    # accept both GET (EventSource) and POST
    if request.method == "GET":
        sid      = (request.args.get("session_id")  or "").strip()
        qid      = (request.args.get("question_id") or "").strip()
        expected = (request.args.get("expected")    or "text").strip()
        raw      = request.args.get("answer") or ""
    else:
        data     = request.get_json(force=True) or {}
        sid      = (data.get("session_id")  or "").strip()
        qid      = (data.get("question_id") or "").strip()
        expected = (data.get("expected")    or "text").strip()
        raw      = data.get("answer", "")

    if not sid or not qid:
        return jsonify({"error": "missing session_id or question_id"}), 400

    sess = _session_load(sid)
    if not sess:
        return jsonify({"error": "invalid_or_expired_session"}), 404

    scenario = sess["scenario"]
    hints    = dict(sess.get("hints") or {})
    start_at = int(sess.get("steps_done", 0))

    answers = dict(hints.get("answers") or {})
    answers[qid] = _parse_answer(raw, expected)
    hints["answers"] = answers

    def generate():
        try:
            for evt in agent.resolve_stream(scenario, hints=hints,
                                            session_id=sid, start_at_step=start_at, resume=True):
                yield sse(evt)
            yield sse("[DONE]")
        except Exception as e:
            yield sse({"type":"error","at":now_iso(),
                      "data":{"message":str(e),"trace":traceback.format_exc()}})
            yield sse("[DONE]")

    return Response(generate(), headers=_sse_headers())

# app.py ─ replace evidence_upload() with:
@app.route("/api/evidence/upload", methods=["POST"])
def evidence_upload():
    order_id = request.form.get("order_id", "order_demo")
    session_id = request.form.get("session_id", "")      # <-- NEW
    question_id = request.form.get("question_id", "")    # <-- NEW
    files = request.files.getlist("images")
    saved = []
    os.makedirs("uploads", exist_ok=True)
    for f in files:
        fname = f"evidence_{order_id}_{int(time.time())}_{f.filename}"
        path = os.path.join("uploads", fname)
        f.save(path)
        saved.append(path)

    # If we know the session, drop file list into its answers so resume sees it
    if session_id:
        sess = _session_load(session_id)
        if sess:
            hints = dict(sess.get("hints") or {})
            ans = dict(hints.get("answers") or {})
            if question_id:
                ans[question_id] = saved[:]  # filenames (short!)
            hints["answers"] = ans
            _session_save(session_id, {**sess, "hints": hints})

    return jsonify({"ok": True, "files": saved})

if __name__ == "__main__":
    # Run: python app.py
    app.run(host="0.0.0.0", port=5000, debug=False)
