# app.py
import datetime
import os, re, json, time, math, traceback, logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, request, jsonify, Response, g, session
from flask_cors import CORS
import uuid

import urllib

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
    with open(ORDERS_FILE, "r") as f:
        return json.load(f)

def _save_orders(data: Dict[str, Any]) -> None:
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
from uuid import uuid4
from threading import Lock

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

# Interactive session storage (in-memory; stateless deployments should swap to Redis)
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
        existing = hints.get("answers") or {}
        existing.update(answers)
        hints["answers"] = existing
    return hints

def _truthy_str(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"y","yes","true","1"}:
        return True
    if s in {"n","no","false","0"}:
        return False
    return None

# --- Evidence helpers ---
UPLOADS_ROOT = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_ROOT, exist_ok=True)

EVIDENCE_ROOT = os.path.join(os.path.dirname(__file__), "evidence")
os.makedirs(EVIDENCE_ROOT, exist_ok=True)

def _save_evidence_images(order_id: str, images: list[str] | None) -> list[str]:
    saved = []
    if not images:
        return saved
    odir = os.path.join(EVIDENCE_ROOT, order_id)
    os.makedirs(odir, exist_ok=True)

    import base64, shutil, time, requests, mimetypes
    for i, src in enumerate(images):
        try:
            if isinstance(src, str) and src.startswith("data:image/"):
                header, b64 = src.split(",", 1)
                ext = ".jpg"
                if "png" in header:  ext = ".png"
                if "webp" in header: ext = ".webp"
                blob = base64.b64decode(b64)
                fp = os.path.join(odir, f"evidence_{int(time.time())}_{i}{ext}")
                with open(fp, "wb") as f: f.write(blob)
                saved.append(fp); continue

            if isinstance(src, str) and src.startswith(("http://","https://")):
                r = requests.get(src, timeout=15); r.raise_for_status()
                ct  = r.headers.get("Content-Type","image/jpeg")
                ext = mimetypes.guess_extension(ct) or ".jpg"
                fp = os.path.join(odir, f"evidence_{int(time.time())}_{i}{ext}")
                with open(fp, "wb") as f: f.write(r.content)
                saved.append(fp); continue

            if isinstance(src, str) and os.path.exists(src):
                ext = os.path.splitext(src)[1] or ".jpg"
                fp = os.path.join(odir, f"evidence_{int(time.time())}_{i}{ext}")
                shutil.copyfile(src, fp)
                saved.append(fp); continue
        except Exception as e:
            log.warning(f"[evidence] save fail {i}: {e}")
    return saved

def _load_evidence_files(order_id: str) -> list[str]:
    odir = os.path.join(EVIDENCE_ROOT, order_id)
    if not os.path.isdir(odir): return []
    files = [os.path.join(odir, f) for f in os.listdir(odir)
             if os.path.isfile(os.path.join(odir, f))]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


# -------------------------- HINT EXTRACTORS ---------------------------
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

# -------------------------- GOOGLE HELPERS ----------------------------
def _gm_headers(field_mask: Optional[str] = None) -> Dict[str, str]:
    h = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY}
    if field_mask:
        h["X-Goog-FieldMask"] = field_mask
    return h

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

# ----------------------------- REAL TOOLS ------------------------------
import base64, mimetypes, time
from uuid import uuid4

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")  

def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)

import base64, mimetypes

def tool_collect_evidence(order_id: str, images=None, notes=None):
    saved = _save_evidence_images(order_id, images or [])
    return {
        "order_id": order_id,
        "photos": len(saved),
        "files": saved[-5:],
        "notes": notes or "",
        "questionnaireCompleted": bool(notes),
    }

def tool_analyze_evidence(order_id: str, images=None, notes=None):
    import base64, mimetypes, os, json, re
    from google.genai import types

    parts = []

    # Collect images (base64 or file paths)
    for item in (images or []):
        if isinstance(item, str) and item.startswith("data:"):
            try:
                header, b64 = item.split(",", 1)
                mime = header.split(";")[0].replace("data:", "") or "image/jpeg"
                parts.append(types.Part.from_bytes(
                    data=base64.b64decode(b64),
                    mime_type=mime
                ))
            except Exception as e:
                log.warning(f"[analyze] bad base64: {e}")
        elif isinstance(item, str) and os.path.exists(item):
            mime = mimetypes.guess_type(item)[0] or "image/jpeg"
            with open(item, "rb") as f:
                parts.append(types.Part.from_bytes(
                    data=f.read(),
                    mime_type=mime
                ))

    if not parts:
        return {
            "order_id": order_id,
            "status": "NO_EVIDENCE",
            "fault": None,
            "confidence": 0.0,
            "rationale": "No images provided.",
            "refund_reasonable": False,
        }

    # Build the request: strings for text, Parts for images
    prompt = (
        "Analyze these spilled package photos and if the package looks spilled then suggest refund_reasonable as true, else false with rationale.\n"
        "Mostly favour a rfund if the package is open/spilled.\n"
        "Return ONLY valid JSON like:\n"
        "{\n"
        '  "fault": "merchant|driver|unclear",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "refund_reasonable": true|false,\n'
        '  "rationale": "short text",\n'
        '  "packaging_feedback": "short text"\n'
        "}"
    )

    try:
        resp = _llm.generate_content(
        contents=[prompt] + parts 
    )
        raw = getattr(resp, "text", "") or ""
    except Exception as e:
        return {
            "order_id": order_id,
            "status": "ERROR",
            "fault": None,
            "confidence": 0.0,
            "rationale": f"Model error: {e}",
            "refund_reasonable": False,
        }

    # Parse JSON (strip backticks if Gemini wraps it)
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        data = json.loads(m.group(0) if m else raw)
    except Exception:
        data = {}

    fault = (data.get("fault") or "unclear").lower()
    conf = float(data.get("confidence") or 0.0)
    return {
        "order_id": order_id,
        "status": "OK",
        "fault": fault if fault in ("merchant", "driver", "unclear") else "unclear",
        "confidence": max(0.0, min(1.0, conf)),
        "rationale": data.get("rationale") or raw,
        "refund_reasonable": bool(data.get("refund_reasonable")),
        "packaging_feedback": data.get("packaging_feedback") or "Improve packaging/seal.",
    }

def tool_geocode_place(query: str) -> Dict[str, Any]:
    pt = _geocode(query)
    if not pt:
        return {"found": False}
    lat, lon = pt
    return {"found": True, "lat": lat, "lon": lon, "query": query}

def _coerce_point(any_val: Any) -> Optional[List[float]]:
    """
    Accepts [lat, lon] or "place string"; returns [lat, lon] or None.
    """
    if isinstance(any_val, (list, tuple)) and len(any_val) == 2:
        try:
            return [float(any_val[0]), float(any_val[1])]
        except Exception:
            return None
    if isinstance(any_val, str) and any_val.strip():
        pt = _geocode(any_val.strip())
        if pt:
            return [pt[0], pt[1]]
    return None

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
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=[prompt])
        text = getattr(resp, "text", "") or "{}"
        data = safe_json(strip_json_block(text), {}) or {}
        op = (data.get("origin_place") or "").strip() or None
        dp = (data.get("dest_place") or "").strip() or None
        return {"origin_place": op, "dest_place": dp}
    except Exception:
        return {"origin_place": None, "dest_place": None}

def _gemini_place_from_text(scenario: str) -> Optional[str]:
    """
    Extract ONE concise center place from free text (used to anchor 'nearby' searches).
    """
    prompt = f"""
        Extract ONE concise place name from the scenario that best represents the search center.
        Return STRICT JSON only:
        {{
        "place_name": "<single place or empty>"
        }}

        Rules:
        - Prefer destination-like areas if present; else a prominent locality in the text.
        - Use human-readable names only (no coordinates/punctuation).

        Scenario:
        {scenario}
        """
    try:
        resp = _llm.generate_content(prompt)
        data = safe_json(strip_json_block(getattr(resp, "text", "") or "{}"), {}) or {}
        name = (data.get("place_name") or "").strip()
        return name or None
    except Exception:
        return None


def _gemini_category_from_text(scenario: str) -> Optional[str]:
    """
    Map text to a coarse category used for Places searches.
    Supported categories: mart, club, restaurant, pharmacy, hospital, atm, fuel, grocery
    """
    prompt = f"""
        From the scenario, pick ONE category keyword from this list:
        ["mart","club","restaurant","pharmacy","hospital","atm","fuel","grocery"]
        Return STRICT JSON only:
        {{"category":"<one of the list or empty>"}}

        Scenario:
        {scenario}
        """
    try:
        resp = _llm.generate_content(prompt)
        data = safe_json(strip_json_block(getattr(resp, "text", "") or "{}"), {}) or {}
        cat = (data.get("category") or "").strip().lower()
        return cat or None
    except Exception:
        return None


# Category→Places Primary Types and default keywords
CATEGORY_TO_TYPES = {
    "mart":       ["convenience_store", "supermarket"],
    "grocery":    ["supermarket", "grocery_store"],
    "club":       ["night_club"],
    "restaurant": ["restaurant"],
    "pharmacy":   ["pharmacy"],
    "hospital":   ["hospital"],
    "atm":        ["atm"],
    "fuel":       ["gas_station"],
    "locker":     ["point_of_interest", "post_office", "storage", "convenience_store"],
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

# --- place-only traffic tools ----------------------------------------------

def _extract_places_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    rd = _gemini_route_from_text(text or "")
    return (rd.get("origin_place"), rd.get("dest_place"))

# ---- add this near the other evidence helpers ----
def _purge_evidence(order_id: str) -> int:
    """Delete all saved evidence files for an order. Returns how many files were removed."""
    odir = os.path.join(EVIDENCE_ROOT, order_id)
    if not os.path.isdir(odir):
        return 0
    cnt = 0
    for f in os.listdir(odir):
        p = os.path.join(odir, f)
        try:
            if os.path.isfile(p):
                os.remove(p); cnt += 1
        except Exception as e:
            log.warning(f"[evidence] purge failed for {p}: {e}")
    return cnt

def tool_initiate_mediation_flow(order_id: str) -> Dict[str, Any]:
    removed = _purge_evidence(order_id)
    return {"order_id": order_id, "flow": "started", "purgedFiles": removed}

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
        # ---- 1) clean / fallback extraction ----------------------------------
        o_name = (_only_place_name(origin_any) or "").strip()
        d_name = (_only_place_name(dest_any) or "").strip()

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

        # ---- 2) mode map ------------------------------------------------------
        mode = {
            "DRIVE":"driving","DRIVING":"driving","CAR":"driving",
            "WALK":"walking","WALKING":"walking",
            "BIKE":"bicycling","BICYCLE":"bicycling","BICYCLING":"bicycling",
            "TRANSIT":"transit","TWO_WHEELER":"driving",
        }.get((travel_mode or "DRIVE").strip().upper(), "driving")

        # ---- 3) call Directions API ------------------------------------------
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": o_name, "destination": d_name,
            "mode": mode, "region": "in", "language": "en",
            "alternatives": "true", "key": GOOGLE_MAPS_API_KEY,
        }
        if mode == "driving":
            params.update(departure_time="now", traffic_model="best_guess")

        data = requests.get(url, params=params, timeout=15).json()
        if data.get("status") != "OK" or not data.get("routes"):
            return {"status": "error", "error": "directions_failed",
                    "origin_place": o_name, "dest_place": d_name, "raw": data}

        # ---- 4) parse first route + steps ------------------------------------
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

        # ---- 5) build Embed URL ----------------------------------------------
        embed_url = (
            "https://www.google.com/maps/embed/v1/directions"
            f"?key={GOOGLE_MAPS_API_KEY}"
            f"&origin={urllib.parse.quote_plus(o_name)}"
            f"&destination={urllib.parse.quote_plus(d_name)}"
            f"&mode={mode}"
        )

        # ---- 6) return --------------------------------------------------------
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
                "embedUrl": embed_url,            # ←-- new field
            },
        }

    except Exception as e:
        return {"status": "error", "error": f"traffic_check_failure:{e}",
                "origin_place": origin_any, "dest_place": dest_any}
  

ROUTES_KEY      = GOOGLE_MAPS_API_KEY         # server-restricted key
ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

def tool_calculate_alternative_route(
    origin_any: Optional[str] = None,
    dest_any: Optional[str] = None,
    travel_mode: str = "DRIVE",
    scenario_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Get main + alternate routes via Routes API (computeAlternativeRoutes=True)."""

    # 1. resolve free-form names --------------------------------
    o_name = (_only_place_name(origin_any) or "").strip()
    d_name = (_only_place_name(dest_any) or "").strip()
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

    # 2. minimal POST body with computeAlternativeRoutes --------
    body = {
        "origin": {"address": o_name},
        "destination": {"address": d_name},
        "travelMode": travel_mode.upper(),
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
    }
    
    # Use the correct field mask as per the documentation
    field_mask = "routes.duration,routes.distanceMeters,routes.routeLabels,routes.polyline.encodedPolyline"

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
        resp.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        data = resp.json()

    except requests.exceptions.RequestException as e:
        return {"status": "error", "error": f"routes_api_failed: {e}",
                "raw": str(e), "origin_place": o_name, "dest_place": d_name}

    # 3. parse every returned route -----------------------------
    routes_out: List[Dict[str, Any]] = []
    best_time = None
    
    if not data.get("routes"):
        return {"status": "error", "error": "no_routes_found",
                "origin_place": o_name, "dest_place": d_name}

    for r in data["routes"]:
        duration_min = round(int(r["duration"][:-1]) / 60)
        poly = r["polyline"]["encodedPolyline"]
        label = r.get("routeLabels", ["DEFAULT_ROUTE"])[0]

        if best_time is None or duration_min < best_time:
            best_time = duration_min

        routes_out.append({
            "summary": label,
            "durationMin": duration_min,
            "trafficMin": duration_min, # Routes API v2 doesn't separate these
            "distance_km": round(r["distanceMeters"] / 1000, 1),
            "polyline": poly,
        })

    default = next((x for x in routes_out if x["summary"] == "DEFAULT_ROUTE"), routes_out[0])
    improvement = max(0, default["durationMin"] - best_time)

    return {
        "status": "ok",
        "origin_place": o_name,
        "dest_place": d_name,
        "mode": travel_mode.lower(),
        "improvementMin": improvement,
        "map": {
            "kind": "directions",
            "routes": routes_out,
            "bounds": None, # Routes API v2 doesn’t provide bounds
        },
    }

def tool_compute_route_matrix(origins: List[Any], destinations: List[Any]) -> Dict[str, Any]:
    if not origins or not destinations:
        return {"error": "missing_origins_or_destinations"}

    def wp_from_any(val):
        pt = _coerce_point(val)  # strictly lat/lon list/tuple or geocoded string
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
    except Exception:
        return {"error": "bad_points"}
    ...

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

def tool_find_nearby_locker(lat: float, lon: float, radius_m: int = 2000) -> Dict[str, Any]:
    """
    Use Google Places Nearby Search to get up to 5 parcel lockers near given coords.
    """
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
        lockers = []
        for p in results[:5]:  # Get the top 5 results
            lockers.append({
                "id": p.get("place_id"),
                "name": p.get("name"),
                "address": p.get("vicinity"),
                "rating": p.get("rating"),
                "user_ratings_total": p.get("user_ratings_total"),
            })

        return {
            "status": "ok",
            "count": len(lockers),
            "lockers": lockers,
            "center": {"lat": lat, "lon": lon},
            "query_place": place_name,
            "used_radius_m": radius_m,
        }

    except Exception as e:
        log.error(f"[find_nearby_locker] An error occurred: {e}")
        return {"count": 0, "lockers": [], "error": str(e)}
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
    """
    Find up to 5 nearby places relevant to a field/vertical.

    Center priority:
      1) place_name (geocoded)
      2) scenario_text -> Gemini extract -> geocode
      3) explicit lat/lon (or strings coercible via _coerce_point)

    Category priority:
      1) explicit category
      2) scenario_text -> Gemini category guess
      3) fallback: use provided keyword only
    """
    # --- Center selection ---
    center = None

    if place_name and str(place_name).strip():
        pt = _geocode(place_name.strip())
        if pt:
            center = [pt[0], pt[1]]

    if center is None and scenario_text and str(scenario_text).strip():
        maybe_center_name = _gemini_place_from_text(scenario_text.strip())
        if maybe_center_name:
            pt = _geocode(maybe_center_name)
            if pt:
                center = [pt[0], pt[1]]

    if center is None:
        if isinstance(lat_any, (int, float)) and isinstance(lon_any, (int, float)):
            center = [float(lat_any), float(lon_any)]
        else:
            center = _coerce_point([lat_any, lon_any]) if (lat_any is not None or lon_any is not None) else None

    if not center:
        return {"error": "invalid_center"}

    # --- Category selection ---
    cat = (category or "").strip().lower() if category else None
    if not cat and scenario_text:
        cat = _gemini_category_from_text(scenario_text)

    types = included_types or (CATEGORY_TO_TYPES.get(cat) if cat else None)
    kw = keyword or (CATEGORY_KEYWORDS.get(cat) if cat else None)

    # - If we still have neither types nor keyword, default to a broad keyword
    if not types and not kw:
        kw = "point of interest"

    lat, lon = center
    body = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius_m),
            }
        }
    }
    if kw:
        body["keyword"] = kw
    if types:
        body["includedPrimaryTypes"] = types

    field_mask = ",".join([
        "places.id","places.displayName","places.formattedAddress",
        "places.nationalPhoneNumber","places.websiteUri","places.rating",
        "places.userRatingCount","places.currentOpeningHours.openNow",
    ])

    try:
        data = _places_post("places:searchNearby", body, field_mask)
        raw = (data.get("places") or [])

        # Keep top 5; prefer places with rating & more reviews
        def _score(p):
            rating = p.get("rating") or 0
            cnt = p.get("userRatingCount") or 0
            # simple rank: rating then log(review_count)
            return (rating, math.log(cnt + 1))

        # Sort descending by score
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
    # Dev mode: pretend delivered so UI flow can be tested
    if FCM_DRY_RUN:
        log.info("[tool_fcm_send] DRY_RUN on → simulating delivered")
        return {"delivered": True, "dryRun": True}

    if _is_placeholder_token(token):
        return {"delivered": False, "reason": "missing_or_placeholder_device_token"}

    access_token = _fcm_access_token()
    base = f"https://fcm.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/messages:send"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # Use WebPush envelope for browsers
    msg = {
        "message": {
            "token": token,
            "webpush": {
                "headers": {"Urgency": "high"},
                "notification": {
                    "title": title,
                    "body": body,
                    # icon & badge are optional but recommended
                    # "icon": "https://your.cdn/icon-192.png",
                    # "badge": "https://your.cdn/badge-72.png",
                    "requireInteraction": True,
                },
                # Make the notification clickable (opens your app)
                "fcmOptions": {"link": "https://your.app/alternates"},
                "data": data or {},
            },
        }
    }

    log.info(f"[tool_fcm_send] sending WebPush title='{title}'")
    res = http_post(base, msg, headers, timeout=10)
    ok = bool(res) and (("name" in res) or res.get("ok") is True)
    if not ok:
        return {"delivered": False, "error": res}
    return {"delivered": True, "fcmResponse": res}

def tool_notify_resolution(driver_token: Optional[str], customer_token: Optional[str], message: str) -> Dict[str, Any]:
    """Sends a final resolution notification to both the driver and the customer."""
    d_res = _fcm_v1_send(driver_token or "", "Dispute Resolution", message)
    c_res = _fcm_v1_send(customer_token or "", "Dispute Resolution", message)
    return {"driver_notified": d_res.get("delivered"), "customer_notified": c_res.get("delivered")}

def tool_notify_customer(fcm_token: Optional[str], message: str, voucher: bool=False, title: str="Order Update") -> Dict[str, Any]:
    return _fcm_v1_send(fcm_token or "", title, message, {"voucher": json.dumps(bool(voucher))})

def tool_notify_passenger_and_driver(driver_token: Optional[str], passenger_token: Optional[str], message: str) -> Dict[str, Any]:
    d = _fcm_v1_send(driver_token or "", "Route Update", message) if driver_token else {"delivered": False}
    p = _fcm_v1_send(passenger_token or "", "Route Update", message) if passenger_token else {"delivered": False}
    return {"driverDelivered": d.get("delivered"), "passengerDelivered": p.get("delivered")}

def tool_get_nearby_merchants(lat: float, lon: float, radius_m: int = 2000) -> Dict[str, Any]:
    """
    Use Google Places Nearby Search to get up to 5 restaurants near given coords.
    """
    try:
        places_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat},{lon}",
            "radius": radius_m,
            "type": "restaurant",   # restrict to restaurants
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
    
def _estimate_trip_minutes(pick_lat, pick_lon, drop_lat, drop_lon) -> float:
    # simple baseline estimate using haversine + BASELINE_SPEED_KMPH
    dist_km = haversine_km(pick_lat, pick_lon, drop_lat, drop_lon)
    return round((dist_km / BASELINE_SPEED_KMPH) * 60.0, 1)

def tool_assign_short_nearby_order(driver_id: str, driver_lat: float, driver_lon: float,
                                   radius_km: float = 6.0, max_total_minutes: float = 25.0) -> Dict[str, Any]:
    """
    Pick the best 'quick' order near the driver:
    - pickup within `radius_km`
    - pickup->drop ETA <= `max_total_minutes`
    Marks the order as 'assigned' to driver_id in orders.json.
    """
    data = _load_orders()
    candidates = []
    for o in data.get("orders", []):
        if o.get("status") != "pending":
            continue
        p = o["pickup"]; d = o["dropoff"]
        dist_to_pick = haversine_km(driver_lat, driver_lon, p["lat"], p["lon"])
        if dist_to_pick > radius_km:
            continue
        job_minutes = _estimate_trip_minutes(p["lat"], p["lon"], d["lat"], d["lon"])
        total_minutes = round(job_minutes + (dist_to_pick / BASELINE_SPEED_KMPH) * 60.0, 1)
        if total_minutes <= max_total_minutes:
            candidates.append({
                "order": o, "distToPickupKm": round(dist_to_pick, 2),
                "jobMinutes": job_minutes, "totalMinutes": total_minutes
            })

    if not candidates:
        return {"assigned": False, "reason": "no_quick_orders_found"}

    # choose the quickest total
    best = min(candidates, key=lambda c: c["totalMinutes"])
    # mark as assigned
    for o in data["orders"]:
        if o["id"] == best["order"]["id"]:
            o["status"] = "assigned"
            o["assignedTo"] = driver_id
            break
    _save_orders(data)

    return {
        "assigned": True,
        "driver_id": driver_id,
        "order": best["order"],
        "distToPickupKm": best["distToPickupKm"],
        "jobMinutes": best["jobMinutes"],
        "totalMinutes": best["totalMinutes"]
    }

def tool_reroute_driver(driver_id: str, driver_lat: float, driver_lon: float) -> Dict[str, Any]:
    """
    Wrapper that calls assign_short_nearby_order and returns a friendly payload
    used by the policy.
    """
    res = tool_assign_short_nearby_order(driver_id, driver_lat, driver_lon)
    if not res.get("assigned"):
        return {"driver_id": driver_id, "rerouted": False, "reason": res.get("reason")}
    o = res["order"]
    newtask = f"Pickup {o['id']} at {o['pickup']['address']} → drop at {o['dropoff']['address']} (≈{res['totalMinutes']} min)"
    return {
        "driver_id": driver_id,
        "rerouted": True,
        "newTask": newtask,
        "assignment": res
    }


# ----------------------------- ASSERTIONS ------------------------------
def check_assertion(assertion: Optional[str], observation: Dict[str, Any]) -> bool:
    """
    Return True when:
      - assertion is None/empty, and observation has no obvious error, OR
      - the named predicate matches the observation.
    Handles common boolean/string/number cases robustly.
    """
    # No explicit assertion → pass unless an error key exists
    if not assertion or not str(assertion).strip():
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

    if "response!=none" in a:
        return isinstance(observation, dict) and len(observation) > 0

    if "len(routes)>=1" in a or "routes>=1" in a:
        routes = observation.get("routes")
        return isinstance(routes, list) and len(routes) >= 1

    if "customerack==true" in a:
        return _truthy(observation.get("customerAck"))

    if "delivered==true" in a:
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

    if "==" in a and all(op not in a for op in (">", "<", "!=")):
        k, val = a.split("==", 1)
        ov = observation.get(k)
        sval = val.strip().lower()
        if sval in {"true","false"}:
            return _truthy(ov) == (sval == "true")
        try:
            return float(str(ov)) == float(sval)
        except Exception:
            return str(ov).strip().lower() == sval

    return True

# ----------------------------- PROMPTS --------------------------------
KIND_LABELS = [
    "merchant_capacity","recipient_unavailable","traffic","damage_dispute",
    "payment_issue","address_issue","weather","safety","other","unknown"
]

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
        # we ignore coordinates; keep only human place strings
        scen = hints.get("scenario_text") or ""
        origin_any = hints.get("origin_place") or hints.get("origin")
        dest_any   = hints.get("dest_place")   or hints.get("dest")
        mode       = (hints.get("mode") or "DRIVE").upper()

        origin_is_name = _only_place_name(origin_any) is not None
        dest_is_name   = _only_place_name(dest_any)   is not None

        # 0) ask once if we have neither name; tools can still infer from scenario_text later
        if (not origin_is_name and not dest_is_name) and steps_done == 0:
            q = {
                "question_id": "route_text",
                "question": (
                    "Please provide pickup and drop as place names only, "
                    "e.g. \"origin=SRMIST, dest=Chennai International Airport\"."
                ),
                "expected": "text",
            }
            return (
                "ask for route",
                "ask_user",
                q,
                None,
                "await_input",
                None,
                "Need origin/destination names to proceed (or I'll infer from scenario).",
            )

        # 1) check congestion (place-name tools; will infer names from scenario_text if missing)
        if steps_done == 0:
            return (
                "check congestion",
                "check_traffic",
                {
                    "origin_any": origin_any,
                    "dest_any": dest_any,
                    "travel_mode": mode,
                    "scenario_text": scen,
                },
                "delayMin>=0",
                "continue",
                None,
                "Measure baseline ETA and traffic delay."
            )

        # 2) compute alternatives (place-name tools)
        if steps_done == 1:
            return (
                "reroute",
                "calculate_alternative_route",
                {
                    "origin_any": origin_any,
                    "dest_any": dest_any,
                    "travel_mode": mode,
                    "scenario_text": scen,
                },
                "improvementMin>=0",
                "continue",
                None,
                "Compute alternatives and pick the fastest route."
            )

        # Step 2: Provide context by checking flight status if applicable
        if steps_done == 2:
            flight_match = re.search(r"flight\s+([A-Z0-9]+)", scen, re.IGNORECASE)
            if flight_match:
                return (
                    "check flight status", "check_flight_status",
                    {"flight_no": flight_match.group(1)},
                    None, "continue", None, "Checking flight status to provide passenger context."
                )
            # If no flight number is mentioned, just skip to the next step
            return ("skip flight check", "none", {}, None, "continue", None, "No flight number in scenario.")

        # Step 3: Notify both parties with the complete information
        if steps_done == 3:
            # Check if the previous step found flight info and add it to the message
            flight_status = hints.get("flight_status", {})
            msg = "We've detected heavy traffic and found a faster route. Your ETA has been updated."
            if flight_status.get("status") == "DELAYED":
                msg += f" FYI: We noticed your flight {flight_status.get('flight')} is also delayed by {flight_status.get('delayMin')} minutes."
            
            return (
                "inform both parties", "notify_passenger_and_driver",
                {"driver_token": hints.get("driver_token"), "passenger_token": hints.get("passenger_token"), "message": msg},
                "delivered==true", "final", "Reroute applied; driver and passenger notified with all context.", "Notify both parties with the updated route/ETA and flight status if available."
            )
        
    # Merchant capacity — notify → real reroute → suggest alternates → push
    if kind == "merchant_capacity":
        token = hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN
        driver_id = hints.get("driver_id", "driver_demo")

        # Step 0: Proactively notify customer (real FCM)
        if steps_done == 0:
            params = {
                "fcm_token": token,
                "message": "The restaurant is experiencing a long prep time (~40 min). We’re minimizing delays and will keep you updated. A small voucher has been applied for the inconvenience.",
                "voucher": True,
                "title": "Delay notice"
            }
            assertion = "delivered==true" if (token or FCM_DRY_RUN) else None
            return (
                "notify customer about delay",
                "notify_customer",
                params,
                assertion,
                "continue",
                None,
                "Proactively inform customer and offer voucher."
            )

        # Step 1: Actually reroute the driver to a quick nearby order
        if steps_done == 1:
            # Try to infer current driver location: prefer origin (restaurant) then dest
            latlon = None
            if isinstance(hints.get("origin"), (list, tuple)) and len(hints["origin"]) == 2:
                latlon = hints["origin"]
            elif isinstance(hints.get("dest"), (list, tuple)) and len(hints["dest"]) == 2:
                latlon = hints["dest"]

            if latlon:
                return (
                    "reroute driver to quick nearby order",
                    "reroute_driver",
                    {"driver_id": driver_id, "driver_lat": float(latlon[0]), "driver_lon": float(latlon[1])},
                    None,
                    "continue",
                    None,
                    "Reduce driver idle time using orders.json."
                )
            # If we lack a reasonable location, skip reroute
            return (
                "skip reroute (no coords)",
                "none",
                {},
                None,
                "continue",
                None,
                "No driver location available; skipping reroute."
            )

        # ──────────────────────────────
        # Step 2 : fetch nearby alternates
        # ──────────────────────────────
        if steps_done == 2:
            latlon = hints.get("origin") or hints.get("dest")
            if latlon and isinstance(latlon, (list, tuple)) and len(latlon) == 2:
                return (
                    "get nearby alternates",
                    "get_nearby_merchants",
                    {"lat": float(latlon[0]), "lon": float(latlon[1]), "radius_m": 2000},
                    "merchants>0",
                    "continue",                     # <-- not final any more
                    None,
                    "Fetch up to 5 faster restaurants.",
                )
            # fall back to notify if no coords
            steps_done = 3                         # force skip to notify

        # ──────────────────────────────
        # Step 3 : ask which restaurant
        # ──────────────────────────────
        if steps_done == 3:
            merchants = hints.get("merchants")     # cached by executor
            choice    = answers.get("alt_choice")
            # ❶ ask once
            if merchants and choice is None:
                opts = [m["name"] for m in merchants] + ["NO • Continue with this restaurant"]
                hints.setdefault("meta", {})["alt_id_by_name"] = {
                    m["name"]: m["id"] for m in merchants
                }
                q = {
                    "question_id": "alt_choice",
                    "question": "Prep time is long. Pick an alternate or choose NO:",
                    "expected": "string",
                    "options": opts,
                }
                return (
                    "clarify", "none", q, None,
                    "await_input",
                    "Awaiting customer choice.",
                    "Offer alternates.",
                )
            # ❷ handle answer
            if choice:
                selected_id = hints["meta"]["alt_id_by_name"].get(choice)
                hints["selected_alt_id"] = selected_id   # could be None if NO
                steps_done = 4                           # fall through to notify

        # ──────────────────────────────
        # Step 4 : notify with result
        # ──────────────────────────────
        if steps_done == 4:
            chosen = hints.get("selected_alt_id")
            msg = (
                f"We’ll switch to **{answers['alt_choice']}** (faster)." if chosen
                else "We’ll keep your current restaurant."
            )
            params = {
                "fcm_token": token,
                "title": "Update on your order",
                "message": msg,
                "voucher": True,
            }
            assertion = "delivered==true" if (token or FCM_DRY_RUN) else None
            return (
                "notify customer with alternates",
                "notify_customer",
                params,
                assertion,
                "final",
                "Customer informed of choice.",
                "Close loop with customer.",
            )

        return None
    
    # Damage dispute
    if kind == "damage_dispute":
        order_id    = hints.get("order_id", "order_demo")
        driver_id   = hints.get("driver_id", "driver_demo")
        merchant_id = hints.get("merchant_id", "merchant_demo")

        answers = hints.get("answers") or {}
        imgs  = hints.get("evidence_images") or answers.get("evidence_images")
        notes = hints.get("evidence_notes")  or answers.get("evidence_notes")

        if steps_done == 0:
            return ("start mediation", "initiate_mediation_flow",
                    {"order_id": order_id}, "flow==started",
                    "continue", None, "Start structured mediation.")

        if steps_done == 1:
            if not imgs and not _load_evidence_files(order_id):
                return ("request images", "ask_user",
                        {"question_id":"evidence_images",
                        "question":"Please upload clear photos of the spilled package (seal, bag, spillage close-ups).",
                        "expected":"image[]"},
                        None, "await_input",
                        "Awaiting photos.", "Need photos to analyze.")
            return ("collect evidence", "collect_evidence",
                    {"order_id": order_id, "images": imgs, "notes": notes},
                    "photos>0", "continue", None, "Persist evidence.")

        if steps_done == 2:
            return ("analyze evidence", "analyze_evidence",
                    {"order_id": order_id, "images": imgs, "notes": notes},
                    "status!=none", "continue", None, "Decide likely fault.")

        if steps_done == 3:
            analysis   = hints.get("analysis") or {}
            reasonable = bool(analysis.get("refund_reasonable"))
            fault      = (analysis.get("fault") or "").lower()
            conf       = float(analysis.get("confidence") or 0.0)
            if reasonable and conf >= 0.55:
                return ("refund customer", "issue_instant_refund",
                        {"order_id": order_id},
                        "refunded==true", "continue", None, "Goodwill refund.")
            msg = ("After reviewing the photos, we don’t see sufficient evidence to issue a refund right now. "
                "If you have additional photos or context, please reply here.")
            return ("notify no refund", "notify_customer",
                    {"fcm_token": hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN,
                    "message": msg, "voucher": False, "title": "Damage Assessment"},
                    "delivered==true", "final", "Customer informed.", "No refund.")

        # Step 5: Exonerate the driver if the merchant was at fault
        if steps_done == 4: 
            analysis = hints.get("analysis", {})
            # Only exonerate if the fault is clearly on the merchant
            if analysis.get("fault") == "merchant":
                return ("exonerate driver", "exonerate_driver", 
                        {"driver_id": driver_id}, "cleared==true",
                        "continue", None, "Merchant found at fault; clearing driver.")
            # IMPORTANT: For all other cases, continue to the next step instead of stopping.
            return ("skip exoneration", "none", {}, None, "continue", None, "Fault not assigned to the merchant.")

        if steps_done == 5:
            analysis = hints.get("analysis") or {}
            if (analysis.get("fault") or "").lower() == "merchant":
                fb = analysis.get("packaging_feedback") or \
                    "Evidence-backed report: seal/leakage suggests packaging issue."
                return ("feedback to merchant", "log_merchant_packaging_feedback",
                        {"merchant_id": merchant_id, "feedback": fb},
                        "feedbacklogged==true", "continue", None, "Log packaging issue.")
            return ("done", "none", {}, None, "final", "Resolution sent.", "No merchant feedback required.")

        # Step 7 (or the final step in your sequence): Communicate final resolution to both parties
        if steps_done == 6: # Adjust step number if needed
            return (
                "notify resolution", "tool_notify_resolution", 
                {
                    "driver_token": hints.get("driver_token"), 
                    "customer_token": hints.get("customer_token"), 
                    "message": "The damage dispute has been resolved. A refund has been issued."
                }, 
                None, "final", "Resolution communicated to all parties.", "Finalizing the dispute."
            )
        return None
    # ---------------------------------------------------------------------
    #  recipient_unavailable  → safe-drop? → choose locker → notify
    # ---------------------------------------------------------------------
    if kind == "recipient_unavailable":
        answers = hints.get("answers") or {}
        lockers = hints.get("lockers")                 # filled after tool runs
        chosen  = answers.get("chosen_locker_id")      # filled via clarify

        # 0 ▸ open chat once
        if steps_done == 0:
            rid = hints.get("recipient_id", "recipient_demo")
            return (
                "reach out via chat", "contact_recipient_via_chat",
                {"recipient_id": rid,
                "message": "Driver has arrived. How should we proceed?"},
                "messagesent!=none",
                "continue", None,
                "Start chat to coordinate.",
            )

        # 1 ▸ safe-drop permission
        safe_ok = _truthy_str(answers.get("safe_drop_ok"))
        if safe_ok is None:
            return (
                "clarify", "none",
                {
                    "question_id": "safe_drop_ok",
                    "question": ("Recipient unavailable. Is it OK to leave the "
                                "package with the building concierge or a neighbour?"),
                    "expected": "boolean",
                    "options": ["yes", "no"],
                },
                None, "await_input",
                "Awaiting safe-drop permission.",
                "Ask for safe-drop permission.",
            )

        if safe_ok is True:
            addr = hints.get("dest_place") or "Building concierge"
            return (
                "suggest safe drop", "suggest_safe_drop_off",
                {"address": addr},
                "suggested==true",
                "final",
                "Safe-drop approved; driver will leave package with concierge.",
                "Proceed with safe drop.",
            )

        # 2 ▸ locker fallback gate
        locker_ok = _truthy_str(answers.get("locker_ok"))
        if locker_ok is None:
            return (
                "clarify", "none",
                {
                    "question_id": "locker_ok",
                    "question": ("Safe-drop not allowed. Should I route to the "
                                "nearest parcel/post-office locker instead?"),
                    "expected": "boolean",
                    "options": ["yes", "no"],
                },
                None, "await_input",
                "Awaiting locker permission.",
                "Offer locker fallback.",
            )

        # 3 ▸ we already have lockers → ask which one
        if lockers and chosen is None:
            opts = [l["name"] for l in lockers]
            hints.setdefault("meta", {})["locker_ids"] = {
                l["name"]: l["id"] for l in lockers
            }
            return (
                "clarify", "none",
                {
                    "question_id": "chosen_locker_id",
                    "question": "Select a locker for the driver:",
                    "expected": "string",
                    "options": opts,
                },
                None, "await_input",
                "Awaiting locker choice.",
                "Ask which locker.",
            )

        # 4 ▸ locker chosen → send confirmation push
        if chosen:
            locker_id = hints["meta"]["locker_ids"].get(chosen, chosen)
            return (
                "notify", "notify_customer",
                {
                    "fcm_token": hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN,
                    "title": "Package secured",
                    "message": (f"Your parcel has been placed in locker "
                                f"{locker_id}. Pick-up code sent via SMS/Email."),
                    "voucher": False,
                },
                "delivered==true",
                "final",
                "Locker selected and customer notified.",
                "Confirm locker drop-off.",
            )

        # 5 ▸ lockers not fetched yet → fetch once
        if lockers is None:
            dest_place = hints.get("dest_place")
            if dest_place:
                return (
                    "find locker", "find_nearby_locker",
                    {"place_name": dest_place, "radius_m": 15000},
                    "lockers>0",
                    "continue",          # <-- NOT final
                    "Found lockers, will prompt recipient.",
                    "Search lockers.",
                )

            latlon = hints.get("dest") or hints.get("origin")
            if latlon and isinstance(latlon, (list, tuple)) and len(latlon) == 2:
                return (
                    "find locker (coords)", "places_search_nearby",
                    {"lat": latlon[0], "lon": latlon[1],
                    "radius_m": 15000,
                    "keyword": "parcel locker OR package pickup OR amazon locker OR smart locker"},
                    "count>0",
                    "continue",          # <-- NOT final
                    "Found lockers by coordinates; will prompt recipient.",
                    "Search lockers by coordinates.",
                )

        # 6 ▸ still nothing → escalate to customer
        return (
            "notify", "notify_customer",
            {
                "fcm_token": hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN,
                "title": "Delivery attempt",
                "message": ("Delivery attempted; no safe-drop and no lockers "
                            "could be suggested. Please advise next steps."),
                "voucher": False,
            },
            "delivered==true",
            "final",
            "Awaiting recipient guidance (no location for lockers).",
            "Notify customer due to insufficient data.",
        )

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

    def resolve_stream(
        self,
        scenario: str,
        hints: Optional[Dict[str, Any]] = None,
        *,
        session_id: Optional[str] = None,
        start_at_step: int = 0,
        resume: bool = False
    ):
        """
        Streams events. If 'resume' is True, we continue from a saved session_id.
        """
        t0 = time.time()
        hints = hints or {}
        sid = session_id or str(uuid4())

        # 0) announce session id
        yield {"type": "session", "at": now_iso(), "data": {"session_id": sid}}

        # 1) classification
        cls = self.classify(scenario)
        kind = cls.get("kind", "other")
        yield {"type": "classification", "at": now_iso(), "data": cls, "kind": kind}
        time.sleep(STREAM_DELAY)

        # 2) steps
        steps = max(0, int(start_at_step))
        last_final_message = None
        awaiting_q: Optional[Dict[str, Any]] = None

        # Fold free-typed route text back into hints for traffic flows
        answers = hints.get("answers") or {}
        route_text = (answers.get("route_text") or "").strip() if isinstance(answers.get("route_text"), str) else ""
        if route_text and ("origin" not in hints and "origin_place" not in hints):
            rhints = extract_hints(route_text, hints.get("driver_token"), hints.get("passenger_token"))
            hints.update({k: v for k, v in rhints.items() if k in ("origin","dest","origin_place","dest_place")})

        while steps < MAX_STEPS and (time.time() - t0) < MAX_SECONDS:
            step = _policy_next_extended(kind, steps, hints)
            if not step:
                break

            intent, tool, params, assertion, finish_reason, final_message, reason = step

            # Execute tool (including pseudo tools)
            if tool in ("none", "ask_user"):
                # ask_user → just echo back what to ask; resolve will pause below
                obs = {"awaiting": True, **(params or {})} if tool == "ask_user" else {"note": "clarification_requested"}
            else:
                try:
                    fn = TOOLS.get(tool, {}).get("fn")
                    if callable(fn):
                        obs = fn(**(params or {}))
                        if tool in ("find_nearby_locker", "places_search_nearby") and isinstance(obs, dict):
                            if obs.get("lockers"):
                                hints["lockers"] = obs["lockers"]
                        if tool == "get_nearby_merchants" and obs.get("merchants"):
                            hints["merchants"] = obs["merchants"]
                        session["hints"]  = hints  
                        if tool not in ("none", "ask_user") and isinstance(obs, dict):
                            # stash key outputs for later policy checks
                            if tool == "analyze_evidence":
                                # persist for the rest of the run (and resume)
                                hints["analysis"] = obs
                        # ---- side effects we need for later policy steps ----
                        if tool == "collect_evidence" and isinstance(obs, dict):
                            files = obs.get("files")
                            if files:
                                a = hints.get("answers") or {}
                                a["evidence_images"] = files
                                hints["answers"] = a
                        if tool == "analyze_evidence" and isinstance(obs, dict):
                            # keep last analysis for refund/decline branches
                            hints["analysis"] = obs
                    else:
                        obs = {"error": f"tool_not_found_or_not_callable:{tool}"}
                except Exception as e:
                    obs = {"error": str(e), "trace": traceback.format_exc()}
            try:
                if tool == "collect_evidence":
                    # remember saved files (if tool returned them)
                    if isinstance(obs, dict) and obs.get("files"):
                        hints["evidence_images"] = obs.get("files")
                elif tool == "analyze_evidence":
                    # keep full analysis for the decision step
                    if isinstance(obs, dict) and obs.get("status"):
                        hints["analysis"] = obs
                elif tool == "issue_instant_refund":
                    if isinstance(obs, dict) and "refunded" in obs:
                        hints["refunded"] = bool(obs.get("refunded"))
            except Exception:
                pass

            passed = check_assertion(assertion, obs)
            if not passed and isinstance(obs, dict) and "error" not in obs:
                # be permissive unless the tool explicitly failed
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
                last_final_message = final_message
                break

            if finish_reason == "await_input":
                # save the current run under the SAME sid for resume
                _session_save(sid, {
                    "scenario": scenario,
                    "hints": hints,
                    "kind": kind,
                    "steps_done": steps,
                    "savedAt": now_iso(),
                })
                awaiting_q = {
                    "session_id": sid,
                    "question_id": (params or {}).get("question_id"),
                    "question": (params or {}).get("question"),
                    "expected": (params or {}).get("expected"),
                    "options": (params or {}).get("options"),
                }
                yield {"type": "clarify", "at": now_iso(), "data": awaiting_q, "kind": kind}
                break

        # 3) summary
        if awaiting_q:
            # keep session for resume; route wrapper will still send [DONE]
            return

        duration = int(time.time() - t0)
        outcome = "resolved" if (last_final_message is not None) else ("classified_only" if steps == 0 else "incomplete")
        summary_message = last_final_message or "No further steps were taken."

        # we're done; clear session
        _session_delete(sid)

        yield {
            "type": "summary",
            "at": now_iso(),
            "kind": kind,
            "data": {
                "scenario": scenario,
                "classification": cls,
                "metrics": {"totalSeconds": duration, "steps": steps},
                "outcome": outcome,
                "message": summary_message,
            },
        }

    def resolve_sync(self, scenario: str, hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        trace = []
        for evt in self.resolve_stream(scenario, hints=hints or {}):
            trace.append(evt)
        return {"trace": trace}

# ----------------------------- TOOL REGISTRY ---------------------------
TOOLS: Dict[str, Dict[str, Any]] = {
    "check_flight_status": {
        "fn": lambda flight_no: {"flight": flight_no, "status": "DELAYED", "delayMin": 45},
        "desc": "MOCK: Checks the status of a flight.", "schema": {"flight_no":"str"}
    },
    "tool_notify_resolution": {
        "fn": tool_notify_resolution,
        "desc": "Sends a final resolution notification to both driver and customer.",
        "schema": {"driver_token":"str", "customer_token":"str", "message":"str"}
    },
    "check_traffic": {
        "fn": tool_check_traffic,
        "desc": "ETA/naive delay via Routes API (place-name based).",
        "schema": {"origin_any": "str?", "dest_any": "str?", "travel_mode": "DRIVE|TWO_WHEELER|WALK|BICYCLE|TRANSIT", "scenario_text": "str?"},
    },
    "calculate_alternative_route": {
        "fn": tool_calculate_alternative_route,
        "desc": "Alternative routes & improvement (place-name based).",
        "schema": {"origin_any": "str?", "dest_any": "str?", "travel_mode": "str", "scenario_text": "str?"},
    },
    "compute_route_matrix": {
        "fn": tool_compute_route_matrix,
        "desc": "Route matrix (Routes API).",
        "schema": {"origins": "[any,...]", "destinations": "[any,...]"},
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
    "desc": "Nearby places (category-aware, Places API).",
    "schema": {
        "lat": "float|str?",
        "lon": "float|str?",
        "radius_m": "int",
        "keyword": "str?",
        "included_types": "list[str]?",
        "place_name": "str?",
        "scenario_text": "str?",
        "category": "str?"
    },
    },
    "place_details": {
        "fn": tool_place_details,
        "desc": "Place details (Places API).",
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

    # --- Custom tools / mocks ---
    "get_merchant_status": {"fn": lambda merchant_id: {"merchant_id": merchant_id, "prepTimeMin": 40, "backlogOrders": 12, "response": True},
                            "desc": "Merchant backlog/prep time.", "schema": {"merchant_id":"str"}},
    "assign_short_nearby_order": {
        "fn": tool_assign_short_nearby_order,
        "desc": "Assign a quick nearby order from orders.json",
        "schema": {"driver_id": "str", "driver_lat": "float", "driver_lon": "float", "radius_km": "float?", "max_total_minutes": "float?"},
    },
    "reroute_driver": {
        "fn": tool_reroute_driver,
        "desc": "Reroute driver to a selected short nearby order",
        "schema": {"driver_id": "str", "driver_lat": "float", "driver_lon": "float"},
    },

    "get_nearby_merchants": {
        "fn": tool_get_nearby_merchants,
        "desc": "Nearby alternate restaurants via Google Places.",
        "schema": {"lat": "float", "lon": "float", "radius_m": "int"},
    },
    "initiate_mediation_flow": {
        "fn": tool_initiate_mediation_flow,
        "desc": "Start mediation flow (purges old evidence for a fresh review).",
        "schema": {"order_id":"str"},
    },
    "collect_evidence": {"fn": tool_collect_evidence,
        "desc": "Collect evidence photos & notes.",
        "schema": {"order_id":"str","images":"list[str]?","notes":"str?"}},
    "analyze_evidence": {"fn": tool_analyze_evidence,
        "desc": "Analyze evidence with Gemini Vision.",
        "schema": {"order_id":"str","notes":"str?"}},
    "issue_instant_refund": {"fn": lambda order_id: {"order_id": order_id, "refunded": True},
                         "desc": "Refund instantly.", "schema": {"order_id":"str"}},
    "exonerate_driver": {"fn": lambda driver_id: {"driver_id": driver_id, "cleared": True},
                         "desc": "Clear driver fault.", "schema": {"driver_id":"str"}},
    "log_merchant_packaging_feedback": {"fn": lambda merchant_id, feedback: {"merchant_id": merchant_id, "feedbackLogged": True},
                                        "desc": "Feedback to merchant packaging.", "schema": {"merchant_id":"str","feedback":"str"}},
    "contact_recipient_via_chat": {"fn": lambda recipient_id, message: {"recipient_id": recipient_id, "messageSent": message},
                                   "desc": "Chat recipient.", "schema": {"recipient_id":"str","message":"str"}},
    "suggest_safe_drop_off": {"fn": lambda address: {"address": address, "suggested": True},
                              "desc": "Suggest safe place.", "schema": {"address":"str"}},
    "find_nearby_locker": {
    "fn": lambda place_name, radius_m=15000: tool_find_nearby_locker(place_name, radius_m)},
    "check_flight_status": {"fn": lambda flight_no: {"flight": flight_no, "status": "DELAYED", "delayMin": 45},
                            "desc": "Flight status check.", "schema": {"flight_no":"str"}},

    # Pseudo tool to pause & request user input
    "ask_user": {
        "fn": lambda **kwargs: {"awaiting": True, **kwargs},
        "desc": "Pause chain and ask user a question; resume when answered.",
        "schema": {"question_id": "str", "question": "str", "expected": "str?", "options": "list[str]?"},
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
        return jsonify({"error":"missing scenario"
                        }), 400

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
