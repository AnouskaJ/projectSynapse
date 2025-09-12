"""
Firebase authentication utilities
"""
import os
from typing import Optional, Dict, Any
from functools import wraps

from flask import request, jsonify, g

from ..config import SERVICE_ACCOUNT_FILE, FIREBASE_PROJECT_ID, REQUIRE_AUTH
from ..logger import get_logger

log = get_logger(__name__)

# Initialize Firebase Admin
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
    """Extract bearer token from Authorization header"""
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
    """Decorator to require authentication for protected endpoints"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        decoded = verify_firebase_token_optional()
        if REQUIRE_AUTH and (decoded is None):
            return jsonify({"error": "unauthorized"}), 401
        g.user = decoded  # may be None if not provided/required
        return fn(*args, **kwargs)
    return wrapper