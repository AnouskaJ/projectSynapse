"""
Mediation and evidence analysis tools
"""
import base64
import mimetypes
import os
import json
import re
from typing import Dict, Any, List, Optional

from google.genai import types

from ..services.llm import llm
from ..repositories.evidence import save_evidence_images, load_evidence_files, purge_evidence
from ..logger import get_logger

log = get_logger(__name__)

def tool_collect_evidence(order_id: str, images=None, notes=None):
    """Collect evidence photos and notes for an order"""
    saved = save_evidence_images(order_id, images or [])
    return {
        "order_id": order_id,
        "photos": len(saved),
        "files": saved[-5:],
        "notes": notes or "",
        "questionnaireCompleted": bool(notes),
    }

def tool_analyze_evidence(order_id: str, images=None, notes=None):
    """Analyze evidence using Gemini Vision"""
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
        resp = llm.generate_content(
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

def tool_initiate_mediation_flow(order_id: str) -> Dict[str, Any]:
    """Start structured mediation flow (purges old evidence for a fresh review)"""
    removed = purge_evidence(order_id)
    return {"order_id": order_id, "flow": "started", "purgedFiles": removed}

# Mock tools for the mediation flow
def tool_issue_instant_refund(order_id: str) -> Dict[str, Any]:
    """Mock: Issue instant refund for an order"""
    return {"order_id": order_id, "refunded": True}

def tool_exonerate_driver(driver_id: str) -> Dict[str, Any]:
    """Mock: Clear driver fault"""
    return {"driver_id": driver_id, "cleared": True}

def tool_log_merchant_packaging_feedback(merchant_id: str, feedback: str) -> Dict[str, Any]:
    """Mock: Log packaging feedback to merchant"""
    return {"merchant_id": merchant_id, "feedbackLogged": True}

def tool_contact_recipient_via_chat(recipient_id: str, message: str) -> Dict[str, Any]:
    """Mock: Contact recipient via chat"""
    return {"recipient_id": recipient_id, "messageSent": message}

def tool_suggest_safe_drop_off(address: str) -> Dict[str, Any]:
    """Mock: Suggest safe drop-off location"""
    return {"address": address, "suggested": True}