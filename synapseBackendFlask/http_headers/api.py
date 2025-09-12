"""
HTTP API routes for Synapse
"""
import json
import os
import time
import traceback
from typing import Dict, Any

from flask import Flask, request, jsonify, Response

from ..auth.firebase import require_auth
from ..config import *
from ..services.fcm import send_notification
from ..utils.sse import sse, sse_headers
from ..utils.jsonx import safe_json
from ..utils.sessions import session_load, session_save, merge_answers
from ..utils.time import now_iso
from ..agent import SynapseAgent
from .middleware import parse_answer, normalize_answer_value
from ..logger import get_logger

log = get_logger(__name__)

def create_api_routes(app: Flask, agent: SynapseAgent):
    """Create all API routes for the Flask app"""
    
    @app.route("/api/health")
    def health():
        return jsonify({
            "ok": True,
            "model": GEMINI_MODEL,
            "project": FIREBASE_PROJECT_ID,
            "googleKeySet": bool(GOOGLE_MAPS_API_KEY),
            "requireAuth": REQUIRE_AUTH,
            "fcmDryRun": FCM_DRY_RUN,
            "fcmScopes": ["https://www.googleapis.com/auth/firebase.messaging"],
        })

    @app.route("/api/tools")
    def tools():
        from ..tools.registry import TOOLS
        return jsonify({
            "tools": [
                {"name": k, "desc": v.get("desc"), "schema": v.get("schema")}
                for k, v in TOOLS.items()
            ]
        })

    @app.route("/api/agent/run")
    @require_auth
    def run_stream():
        """GET /api/agent/run (SSE) - Stream agent responses"""
        scenario_q = (request.args.get("scenario") or "").strip()
        session_id_q = (request.args.get("session_id") or request.args.get("resume_session") or "").strip()
        answers_q = request.args.get("answers")
        answers_dict = safe_json(answers_q, {}) if answers_q else {}

        # Resume flow
        if session_id_q:
            session = session_load(session_id_q)
            if not session:
                return jsonify({"error": "invalid_session"}), 400
            
            scenario = session["scenario"]
            hints = session["hints"] or {}
            start_at = int(session.get("steps_done", 0))

            merge_answers(hints, answers_dict)

            # Allow token overrides on resume
            driver_token_q = (request.args.get("driver_token") or "").strip()
            passenger_token_q = (request.args.get("passenger_token") or "").strip()
            customer_token_q = (request.args.get("customer_token") or "").strip()

            if driver_token_q: hints["driver_token"] = driver_token_q
            if passenger_token_q: hints["passenger_token"] = passenger_token_q
            if customer_token_q: hints["customer_token"] = customer_token_q

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
                    yield sse({"type": "error", "at": now_iso(), "data": {"message": str(e), "trace": traceback.format_exc()}})
                    yield sse("[DONE]")

            return Response(generate(), headers=sse_headers())

        # First run
        scenario = scenario_q
        if not scenario:
            return jsonify({"error": "missing scenario"}), 400

        origin_q = request.args.get("origin")
        dest_q = request.args.get("dest")

        driver_token_q = (request.args.get("driver_token") or "").strip()
        passenger_token_q = (request.args.get("passenger_token") or "").strip()
        customer_token_q = (request.args.get("customer_token") or "").strip()

        merchant_id_q = (request.args.get("merchant_id") or "").strip()
        order_id_q = (request.args.get("order_id") or "").strip()
        driver_id_q = (request.args.get("driver_id") or "").strip()
        recipient_id_q = (request.args.get("recipient_id") or "").strip()

        # Append human-readable hints
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

        # Build base hints
        from ..tools.traffic import extract_hints
        hints = extract_hints(scenario, driver_token_q, passenger_token_q)

        # Override from query params if provided
        if origin_q and dest_q:
            try:
                lat1, lon1 = map(float, origin_q.split(","))
                lat2, lon2 = map(float, dest_q.split(","))
                hints["origin"] = [lat1, lon1]
                hints["dest"] = [lat2, lon2]
            except Exception:
                pass

        # Token hints
        if driver_token_q: hints["driver_token"] = driver_token_q
        if passenger_token_q: hints["passenger_token"] = passenger_token_q
        if customer_token_q: hints["customer_token"] = customer_token_q
        hints.setdefault("driver_token", DEFAULT_DRIVER_TOKEN or None)
        hints.setdefault("passenger_token", DEFAULT_PASSENGER_TOKEN or None)
        hints.setdefault("customer_token", DEFAULT_CUSTOMER_TOKEN or None)

        # Extended IDs
        if merchant_id_q: hints["merchant_id"] = merchant_id_q
        if order_id_q: hints["order_id"] = order_id_q
        if driver_id_q: hints["driver_id"] = driver_id_q
        if recipient_id_q: hints["recipient_id"] = recipient_id_q

        # Geocode place names to coords when coords missing
        from ..services.google_maps import geocode
        if not hints.get("origin") and hints.get("origin_place"):
            pt = geocode(hints["origin_place"])
            if pt: hints["origin"] = [pt[0], pt[1]]
        if not hints.get("dest") and hints.get("dest_place"):
            pt = geocode(hints["dest_place"])
            if pt: hints["dest"] = [pt[0], pt[1]]

        # Merge any provided answers on first run too
        merge_answers(hints, answers_dict)

        def generate():
            try:
                for evt in agent.resolve_stream(scenario, hints=hints):
                    yield sse(evt)
                yield sse("[DONE]")
            except Exception as e:
                yield sse({"type": "error", "at": now_iso(), "data": {"message": str(e), "trace": traceback.format_exc()}})
                yield sse("[DONE]")

        return Response(generate(), headers=sse_headers())

    @app.route("/api/agent/resolve", methods=["POST"])
    @require_auth
    def resolve_sync_endpoint():
        """POST /api/agent/resolve - Synchronous agent resolution"""
        data = request.get_json(force=True) or {}

        # Resume mode
        session_id = (data.get("session_id") or "").strip()
        answers = data.get("answers") or {}
        if session_id:
            session = session_load(session_id)
            if not session:
                return jsonify({"error": "invalid_session"}), 400
            scenario = session["scenario"]
            hints = session["hints"] or {}
            merge_answers(hints, answers)
            result = agent.resolve_sync(scenario, hints=hints)
            return jsonify(result)

        # First-run mode
        scenario = (data.get("scenario") or "").strip()
        if not scenario:
            return jsonify({"error": "missing scenario"}), 400

        driver_token = (data.get("driver_token") or "").strip()
        passenger_token = (data.get("passenger_token") or "").strip()
        customer_token = (data.get("customer_token") or "").strip()

        origin = data.get("origin")  # [lat,lon]
        dest = data.get("dest")    # [lat,lon]

        merchant_id = (data.get("merchant_id") or "").strip()
        order_id = (data.get("order_id") or "").strip()
        driver_id = (data.get("driver_id") or "").strip()
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
        if driver_token: hints["driver_token"] = driver_token
        if passenger_token: hints["passenger_token"] = passenger_token
        if customer_token: hints["customer_token"] = customer_token
        if merchant_id: hints["merchant_id"] = merchant_id
        if order_id: hints["order_id"] = order_id
        if driver_id: hints["driver_id"] = driver_id
        if recipient_id: hints["recipient_id"] = recipient_id
        hints.setdefault("driver_token", DEFAULT_DRIVER_TOKEN or None)
        hints.setdefault("passenger_token", DEFAULT_PASSENGER_TOKEN or None)
        hints.setdefault("customer_token", DEFAULT_CUSTOMER_TOKEN or None)

        # Let Gemini infer origin/dest *place names*; then geocode if coords are missing
        from ..tools.traffic import extract_hints
        h2 = extract_hints(scenario, hints.get("driver_token"), hints.get("passenger_token"))
        hints.update({k: v for k, v in h2.items() if v})

        from ..services.google_maps import geocode
        if not hints.get("origin") and hints.get("origin_place"):
            pt = geocode(hints["origin_place"])
            if pt: hints["origin"] = [pt[0], pt[1]]
        if not hints.get("dest") and hints.get("dest_place"):
            pt = geocode(hints["dest_place"])
            if pt: hints["dest"] = [pt[0], pt[1]]

        merge_answers(hints, answers)

        result = agent.resolve_sync(scenario, hints=hints)
        return jsonify(result)

    @app.route("/api/agent/clarify/continue", methods=["GET", "POST", "OPTIONS"])
    @require_auth
    def clarify_continue():
        """Continue after clarification question"""
        if request.method == "GET":
            sid = (request.args.get("session_id") or "").strip()
            qid = (request.args.get("question_id") or "").strip()
            expected = (request.args.get("expected") or "string").strip()
            raw = request.args.get("answer") or ""
        else:
            data = request.get_json(force=True) or {}
            sid = (data.get("session_id") or "").strip()
            qid = (data.get("question_id") or "").strip()
            expected = (data.get("expected") or "string").strip()
            raw = data.get("answer", "")

        if not sid or not qid:
            return jsonify({"error": "missing session_id or question_id"}), 400

        sess = session_load(sid)
        if not sess:
            return jsonify({"error": "invalid_or_expired_session"}), 404

        scenario = sess["scenario"]
        hints = dict(sess.get("hints") or {})
        start_at = int(sess.get("steps_done", 0))

        # Normalize and store the answer
        answers = dict(hints.get("answers") or {})
        val = parse_answer(raw, expected)
        val = normalize_answer_value(val)

        answers[qid] = val
        hints["answers"] = answers

        # Persist the updated session
        sess["hints"] = hints
        session_save(sid, sess)

        def generate():
            try:
                for evt in agent.resolve_stream(
                    scenario,
                    hints=hints,
                    session_id=sid,
                    start_at_step=start_at,
                    resume=True,
                ):
                    yield sse(evt)
                yield sse("[DONE]")
            except Exception as e:
                yield sse({
                    "type": "error",
                    "at": now_iso(),
                    "data": {"message": str(e), "trace": traceback.format_exc()}
                })
                yield sse("[DONE]")

        return Response(generate(), headers=sse_headers())

    @app.route("/api/evidence/upload", methods=["POST"])
    def evidence_upload():
        """Upload evidence files"""
        order_id = request.form.get("order_id", "order_demo")
        session_id = request.form.get("session_id", "")
        question_id = request.form.get("question_id", "")
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
            sess = session_load(session_id)
            if sess:
                hints = dict(sess.get("hints") or {})
                ans = dict(hints.get("answers") or {})
                if question_id:
                    ans[question_id] = saved[:]  # filenames
                hints["answers"] = ans
                session_save(session_id, {**sess, "hints": hints})

        return jsonify({"ok": True, "files": saved})

    @app.route("/api/fcm/send_test", methods=["POST"])
    @require_auth
    def fcm_send_test():
        """Test FCM notification sending"""
        data = request.get_json(force=True) or {}
        token = data.get("token")
        title = data.get("title", "Test")
        body = data.get("body", "Hello from Synapse")
        
        if not token:
            return jsonify({"error": "missing token"}), 400
        
        res = send_notification(token, title, body)
        return jsonify(res)

    @app.route("/api/fcm/send", methods=["POST"])
    @require_auth
    def fcm_send():
        """Send FCM notification with data payload"""
        data = request.get_json(force=True) or {}
        token = data.get("token") or ""
        title = data.get("title") or "Notification"
        body = data.get("body") or ""
        extra = data.get("data") or None
        
        if not token:
            return jsonify({"error": "missing token"}), 400
        
        res = send_notification(token, title, body, extra)
        return jsonify(res)