"""
Policy rails - deterministic step-by-step flows for different scenario types
"""
from typing import Optional, Tuple, Dict, Any
import re

from ..utils.geo import only_place_name
from ..utils.jsonx import truthy_str
from ..utils.sessions import session_load, session_save
from ..config import DEFAULT_CUSTOMER_TOKEN, DEFAULT_DRIVER_TOKEN, DEFAULT_PASSENGER_TOKEN, FCM_DRY_RUN

def _extract_places_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract origin and destination from text - imported from traffic tools"""
    from ..tools.traffic import _extract_places_from_text
    return _extract_places_from_text(text or "")

def policy_next_extended(kind: str, steps_done: int, hints: Dict[str, Any], sid: Optional[str] = None) -> Optional[Tuple]:
    """
    Returns the next action for the agent based on the scenario kind and current step.
    Returns: (intent, tool, params, assertion, finish_reason, final_message, reason)
    """
    
    if kind == "traffic":
        # Get scenario details
        scen = hints.get("scenario_text") or ""
        origin_any = hints.get("origin_place") or hints.get("origin")
        dest_any = hints.get("dest_place") or hints.get("dest")
        mode = (hints.get("mode") or "DRIVE").upper()

        origin_is_name = only_place_name(origin_any) is not None
        dest_is_name = only_place_name(dest_any) is not None

        # Step 0: Ask for route if we have neither name
        if (not origin_is_name and not dest_is_name) and steps_done == 0:
            q = {
                "question_id": "route_text",
                "question": (
                    "Please provide pickup and drop as place names only, "
                    "e.g. \"origin=SRMIST Chennai, dest=Chennai International Airport\"."
                ),
                "expected": "text",
            }
            return (
                "ask for route", "ask_user", q, None, "await_input", None,
                "Need origin/destination names to proceed (or I'll infer from scenario).",
            )

        # Step 1: Check congestion
        if steps_done == 0:
            return (
                "check congestion", "check_traffic",
                {
                    "origin_any": origin_any,
                    "dest_any": dest_any,
                    "travel_mode": mode,
                    "scenario_text": scen,
                },
                "delayMin>=0", "continue", None,
                "Measure baseline ETA and traffic delay."
            )

        # Step 2: Compute alternatives
        if steps_done == 1:
            return (
                "reroute", "calculate_alternative_route",
                {
                    "origin_any": origin_any,
                    "dest_any": dest_any,
                    "travel_mode": mode,
                    "scenario_text": scen,
                },
                "improvementMin>=0", "continue", None,
                "Compute alternatives and pick the fastest route."
            )

        # Step 3: Check flight status if applicable
        if steps_done == 2:
            flight_match = re.search(r"flight\s+([A-Z0-9]+)", scen, re.IGNORECASE)
            if flight_match:
                return (
                    "check flight status", "check_flight_status",
                    {"flight_no": flight_match.group(1)},
                    None, "continue", None, 
                    "Checking flight status to provide passenger context."
                )
            return ("skip flight check", "noop", {}, None, "continue", None, "No flight number in scenario.")

        # Step 4: Notify both parties
        if steps_done == 3:
            flight_status = hints.get("flight_status", {})
            msg = "We've detected heavy traffic and found a faster route. Your ETA has been updated."
            if flight_status.get("status") == "DELAYED":
                msg += f" FYI: We noticed your flight {flight_status.get('flight')} is also delayed by {flight_status.get('delayMin')} minutes."
            
            return (
                "inform both parties", "notify_passenger_and_driver",
                {
                    "driver_token": hints.get("driver_token") or DEFAULT_DRIVER_TOKEN, 
                    "passenger_token": hints.get("passenger_token") or DEFAULT_PASSENGER_TOKEN, 
                    "message": msg
                },
                "delivered==true", "final", 
                "Reroute applied; driver and passenger notified with all context.", 
                "Notify both parties with the updated route/ETA and flight status if available."
            )

    if kind == "merchant_capacity":
        answers = hints.get("answers") or {}
        merchants = hints.get("merchants") or []
        chosen = answers.get("alt_choice")
        token = hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN
        driver_id = hints.get("driver_id", "driver_demo")

        # Step 0: Proactively notify the customer about the delay
        if steps_done == 0:
            params = {
                "fcm_token": token,
                "message": ("The restaurant is experiencing a long prep time (~40 min). "
                            "We're minimizing delays and will keep you updated. "
                            "A small voucher has been applied for the inconvenience."),
                "voucher": True,
                "title": "Delay notice",
            }
            assertion = "delivered==true" if (token or FCM_DRY_RUN) else None
            return (
                "notify customer about delay", "notify_customer",
                params, assertion, "continue", None,
                "Proactively inform customer and offer voucher."
            )

        # Step 1: Optionally reroute driver to a quick nearby order
        if steps_done == 1:
            latlon = hints.get("origin") or hints.get("dest")
            if latlon and isinstance(latlon, (list, tuple)) and len(latlon) == 2:
                return (
                    "reroute driver to quick nearby order", "reroute_driver",
                    {"driver_id": driver_id, "driver_lat": float(latlon[0]), "driver_lon": float(latlon[1])},
                    None, "continue", None,
                    "Reduce driver idle time using orders.json."
                )
            return (
                "skip reroute (no coords)", "noop", {}, None, "continue", None,
                "No driver location; skipping reroute."
            )

        # Step 2: Fetch nearby alternative merchants
        if steps_done == 2:
            latlon = hints.get("origin") or hints.get("dest")
            if latlon and isinstance(latlon, (list, tuple)) and len(latlon) == 2:
                return (
                    "get nearby alternates", "get_nearby_merchants",
                    {"lat": float(latlon[0]), "lon": float(latlon[1]), "radius_m": 2000},
                    "merchants>0", "continue", None,
                    "Fetch up to 5 faster restaurants."
                )
            return (
                "skip fetching alternates", "noop", {}, None, "final",
                "Cannot fetch alternates without location.", "Cannot proceed with alternatives."
            )

        # Step 3: Ask the user to choose an alternative
        if steps_done == 3:
            def _is_unanswered(x):
                return x is None or (isinstance(x, str) and x.strip().lower() in ("", "null", "none"))

            if merchants and _is_unanswered(chosen):
                opts = [m["name"] for m in merchants] + ["NO • Continue with this restaurant"]
                hints.setdefault("meta", {})["alt_id_by_name"] = {m["name"]: m["id"] for m in merchants}
                _sess = session_load(sid) or {}
                _sess["hints"] = hints
                session_save(sid, _sess)

                return (
                    "clarify alternate", "ask_user",
                    {"question_id": "alt_choice",
                    "question": "Prep time is long. Pick an alternate or choose NO:",
                    "expected": "string",
                    "options": opts},
                    None, "await_input", "Awaiting customer choice.",
                    "Offer alternates."
                )
            return None 
            
        # Step 4: Process the user's choice
        if steps_done == 4:
            chosen_name = answers.get("alt_choice")
            if chosen_name and isinstance(chosen_name, str) and not chosen_name.upper().startswith("NO"):
                msg = f"We've switched your order to {chosen_name} to minimize delays."
            else:
                msg = "We'll keep your current restaurant and will let you know once the food is ready for pickup."
            
            return (
                "inform customer of choice", "notify_customer",
                {"fcm_token": token, "title": "Order Update", "message": msg},
                "delivered==true", "final",
                "Customer notified of their choice.", "Finalize transaction based on user input."
            )

    if kind == "damage_dispute":
        order_id = "123"
        driver_id = "123" 
        merchant_id = "123"
        answers = hints.get("answers") or {}
        imgs = hints.get("evidence_images") or answers.get("evidence_images")
        notes = hints.get("evidence_notes") or answers.get("evidence_notes")

        # Step 0: Start structured mediation flow
        if steps_done == 0:
            return ("start mediation", "initiate_mediation_flow",
                    {"order_id": order_id}, "flow==started",
                    "continue", None, "Start structured mediation.")

        # Step 1: Request images from the user
        if steps_done == 1:
            from ..repositories.evidence import load_evidence_files
            if not imgs and not load_evidence_files(order_id):
                return ("request images", "ask_user",
                        {"question_id": "evidence_images",
                         "question": "Please upload clear photos of the spilled package (seal, bag, spillage close-ups).",
                         "expected": "image[]"},
                        None, "await_input",
                        "Awaiting photos.", "Need photos to analyze.")
            return None

        # Step 2: Collect and process the evidence
        if steps_done == 2:
            return ("collect evidence", "collect_evidence",
                    {"order_id": order_id, "images": imgs, "notes": notes},
                    "photos>0", "continue", None, "Persist evidence.")

        # Step 3: Analyze the evidence with Gemini Vision
        if steps_done == 3:
            return ("analyze evidence", "analyze_evidence",
                    {"order_id": order_id, "images": imgs, "notes": notes},
                    "status!=none", "continue", None, "Decide likely fault.")

        # Step 4: Issue a refund if the analysis supports it
        if steps_done == 4:
            analysis = hints.get("analysis") or {}
            if bool(analysis.get("refund_reasonable")) and float(analysis.get("confidence", 0.0)) >= 0.55:
                return ("refund customer", "issue_instant_refund",
                        {"order_id": order_id},
                        "refunded==true", "continue", None, "Goodwill refund.")
            
            return ("skip refund", "noop", {}, None, "continue", None, "No refund required.")
        
        # Step 5: Exonerate the driver
        if steps_done == 5:
            analysis = hints.get("analysis", {})
            if analysis.get("fault") != "driver":
                return ("exonerate driver", "exonerate_driver",
                        {"driver_id": driver_id}, "cleared==true",
                        "continue", None, "Exonerating driver.")
            return ("skip driver exoneration", "noop", {}, None, "continue", None, "No driver exoneration required.")

        # Step 6: Log merchant packaging feedback
        if steps_done == 6:
            analysis = hints.get("analysis", {})
            if bool(analysis.get("refund_reasonable")):
                fb = analysis.get("packaging_feedback") or "Evidence-backed report: seal/leakage suggests packaging issue."
                return ("feedback to merchant", "log_merchant_packaging_feedback",
                        {"merchant_id": merchant_id, "feedback": fb},
                        "feedbackLogged==true", "continue", None, "Log packaging issue.")
            return ("skip merchant feedback", "noop", {}, None, "continue", None, "No merchant feedback required.")

        # Step 7: Final notification
        if steps_done == 7:
            refunded = hints.get("refunded", False)
            if refunded:
                msg = "A full refund has been issued for your order. We apologize for the damage."
            else:
                msg = "After reviewing the photos, we don't see sufficient evidence to issue a refund right now. If you have additional photos or context, please reply here."
            return (
                "notify resolution", "notify_customer",
                {
                    "fcm_token": hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN,
                    "title": "Dispute Resolution",
                    "message": msg,
                    "voucher": False,
                },
                "delivered==true", "final", "Resolution communicated to customer.", "Finalizing the dispute."
            )
        
    if kind == "recipient_unavailable":
        answers = hints.get("answers") or {}
        lockers = hints.get("lockers")
        chosen = answers.get("chosen_locker_id")

        # Step 0: Open chat once
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

        # Step 1: Safe-drop permission
        safe_ok = truthy_str(answers.get("safe_drop_ok"))
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

        # Step 2: Locker fallback gate
        locker_ok = truthy_str(answers.get("locker_ok"))
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

        # Step 3: We already have lockers → ask which one
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

        # Step 4: Locker chosen → send confirmation push
        if chosen:
            locker_id = hints["meta"]["locker_ids"].get(chosen, chosen)
            locker_name = ""
            for locker in (hints.get("lockers") or []):
                if locker.get("id") == locker_id:
                    locker_name = locker.get("name")
                    break
            return (
                "notify", "notify_customer",
                {
                    "fcm_token": hints.get("customer_token") or DEFAULT_CUSTOMER_TOKEN,
                    "title": "Package secured",
                    "message": (f"Your parcel has been placed in locker "
                                f"{locker_name}. Pick-up code sent via SMS/Email."),
                    "voucher": False,
                },
                "delivered==true",
                "final",
                "Locker selected and customer notified.",
                "Confirm locker drop-off.",
            )

        # Step 5: Lockers not fetched yet → fetch once
        if lockers is None:
            dest_place = hints.get("dest_place")
            if dest_place:
                return (
                    "find locker", "find_nearby_locker",
                    {"place_name": dest_place, "radius_m": 1500},
                    "lockers>0",
                    "continue",
                    "Found lockers, will prompt recipient.",
                    "Search lockers.",
                )

            latlon = hints.get("dest") or hints.get("origin")
            if latlon and isinstance(latlon, (list, tuple)) and len(latlon) == 2:
                return (
                    "find locker (coords)", "places_search_nearby",
                    {"lat": latlon[0], "lon": latlon[1],
                    "radius_m": 1500,
                    "keyword": "parcel locker OR package pickup OR amazon locker OR smart locker"},
                    "count>0",
                    "continue",
                    "Found lockers by coordinates; will prompt recipient.",
                    "Search lockers by coordinates.",
                )

        # Step 6: Still nothing → escalate to customer
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

    # Default: no more steps
    return None