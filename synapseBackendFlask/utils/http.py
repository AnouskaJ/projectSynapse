"""
HTTP utilities for API calls
"""
import requests
from typing import Dict, Any, Optional

def http_get(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: float = 20.0):
    """Make HTTP GET request"""
    r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def http_post(url: str, json_body: Dict[str, Any], headers: Dict[str, str], timeout: float = 25.0):
    """Make HTTP POST request"""
    r = requests.post(url, json=json_body, headers=headers, timeout=timeout)
    try:
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"ok": True, "text": r.text}
    except requests.HTTPError:
        return {"ok": False, "status": r.status_code, "error_text": r.text}