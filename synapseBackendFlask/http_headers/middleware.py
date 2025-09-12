"""
HTTP middleware and utilities
"""
import json
from typing import Any

def parse_answer(raw, expected):
    """Parse user answers based on expected type"""
    if expected in {"image[]", "string[]"}:
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return [raw] if raw else []
    
    if expected == "boolean":
        s = str(raw).strip().lower()
        return s in {"1", "true", "yes", "y"}
    
    return raw

def normalize_answer_value(val):
    """Normalize answer values from UI libraries"""
    # Accept {label,value} or {name} from UI libs
    if isinstance(val, dict):
        val = val.get("value") or val.get("label") or val.get("name") or ""

    # Allow numeric indexes too
    if isinstance(val, (int, float)):
        try:
            val = str(int(val))
        except Exception:
            val = str(val)

    if isinstance(val, str) and val.strip().lower() in ("", "null", "none"):
        val = None

    return val