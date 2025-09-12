"""
JSON utilities for parsing and handling LLM responses
"""
import json
import re
from typing import Any

def strip_json_block(text: str) -> str:
    """Strip markdown JSON code blocks from text"""
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
    """Safely parse JSON with fallback regex extraction"""
    try:
        return json.loads(text)
    except Exception:
        # Try to extract JSON object from text
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return default

def truthy_str(v: Any) -> bool:
    """Convert various values to boolean"""
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"y", "yes", "true", "1"}:
        return True
    if s in {"n", "no", "false", "0"}:
        return False
    return None