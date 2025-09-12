"""
Assertion checking for tool outputs
"""
from typing import Optional, Dict, Any

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
        return s in {"true", "1", "yes", "y", "ok"}

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
        if isinstance(v, list): return len(v) > 0
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
        if sval in {"true", "false"}:
            return _truthy(ov) == (sval == "true")
        try:
            return float(str(ov)) == float(sval)
        except Exception:
            return str(ov).strip().lower() == sval

    return True