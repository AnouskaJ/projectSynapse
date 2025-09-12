"""
Session management utilities
"""
from typing import Dict, Any, Optional
from threading import Lock

# In-memory session storage (for stateless deployments, consider Redis)
SESSIONS: Dict[str, Any] = {}
SESSIONS_LOCK = Lock()

def session_save(session_id: str, payload: Dict[str, Any]) -> None:
    """Save session data"""
    with SESSIONS_LOCK:
        SESSIONS[session_id] = payload

def session_load(session_id: str) -> Optional[Dict[str, Any]]:
    """Load session data"""
    with SESSIONS_LOCK:
        return SESSIONS.get(session_id)

def session_delete(session_id: str) -> None:
    """Delete session data"""
    with SESSIONS_LOCK:
        SESSIONS.pop(session_id, None)

def merge_answers(hints: Dict[str, Any], answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge user answers into hints"""
    if answers and isinstance(answers, dict):
        existing = hints.get("answers") or {}
        existing.update(answers)
        hints["answers"] = existing
    return hints