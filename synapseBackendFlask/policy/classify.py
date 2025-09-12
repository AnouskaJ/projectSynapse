"""
Scenario classification logic
"""
import json
from typing import Dict, Any

from ..services.llm import llm
from ..utils.jsonx import safe_json, strip_json_block
from ..logger import get_logger

log = get_logger(__name__)

KIND_LABELS = [
    "merchant_capacity", "recipient_unavailable", "traffic", "damage_dispute",
    "payment_issue", "address_issue", "weather", "safety", "other", "unknown"
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
- damage_dispute → spills, broken seals, packaging fault, who's at fault
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

def classify_scenario(scenario: str) -> Dict[str, Any]:
    """Classify a scenario using the LLM"""
    prompt = CLASSIFY_PROMPT.format(labels=json.dumps(KIND_LABELS), scenario=scenario)
    
    try:
        resp = llm.generate_content(prompt)
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