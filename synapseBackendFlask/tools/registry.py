"""
Tool registry - centralized registry of all available tools
"""
from .traffic import tool_check_traffic, tool_calculate_alternative_route
from .nearby import tool_places_search_nearby, tool_find_nearby_locker, tool_get_nearby_merchants, tool_mark_as_placed
from .mediation import (tool_collect_evidence, tool_analyze_evidence, tool_initiate_mediation_flow,
                       tool_issue_instant_refund, tool_exonerate_driver, tool_log_merchant_packaging_feedback,
                       tool_contact_recipient_via_chat, tool_suggest_safe_drop_off)
from .notify import tool_notify_resolution, tool_notify_customer, tool_notify_passenger_and_driver
from .assign import tool_assign_short_nearby_order, tool_reroute_driver, tool_get_merchant_status
from .environment import tool_check_weather, tool_air_quality, tool_pollen_forecast, tool_time_zone, tool_geocode_place
from .roads import tool_roads_snap, tool_compute_route_matrix
from .merchants import tool_place_details, tool_noop
from ..services.flights import get_flight_status

# Centralized tool registry
TOOLS = {
    # Traffic and routing
    "check_traffic": {
        "fn": tool_check_traffic,
        "desc": "ETA/naive delay via Routes API (place-name based).",
        "schema": {"origin_any": "str?", "dest_any": "str?", "travel_mode": "DRIVE|TWO_WHEELER|WALK|BICYCLE|TRANSIT", "scenario_text": "str?"},
    },
    "calculate_alternative_route": {
        "fn": tool_calculate_alternative_route,
        "desc": "Alternative routes & improvement (place-name based).",
        "schema": {"origin_any": "str?", "dest_any": "str?", "travel_mode": "str", "scenario_text": "str?"},
    },
    "compute_route_matrix": {
        "fn": tool_compute_route_matrix,
        "desc": "Route matrix (Routes API).",
        "schema": {"origins": "[any,...]", "destinations": "[any,...]"},
    },
    
    # Environment monitoring
    "check_weather": {
        "fn": tool_check_weather,
        "desc": "Current weather (Google Weather API).",
        "schema": {"lat": "float", "lon": "float"},
    },
    "air_quality": {
        "fn": tool_air_quality,
        "desc": "Current air quality (Air Quality API).",
        "schema": {"lat": "float", "lon": "float"},
    },
    "pollen_forecast": {
        "fn": tool_pollen_forecast,
        "desc": "Pollen forecast (Pollen API).",
        "schema": {"lat": "float", "lon": "float"},
    },
    "time_zone": {
        "fn": tool_time_zone,
        "desc": "Time zone for location (Time Zone API).",
        "schema": {"lat": "float", "lon": "float", "timestamp": "int?"},
    },
    "geocode_place": {
        "fn": tool_geocode_place,
        "desc": "Geocode a place/address.",
        "schema": {"query": "str"},
    },
    
    # Places and nearby search
    "places_search_nearby": {
        "fn": tool_places_search_nearby,
        "desc": "Nearby places (category-aware, Places API).",
        "schema": {
            "lat": "float|str?",
            "lon": "float|str?",
            "radius_m": "int",
            "keyword": "str?",
            "included_types": "list[str]?",
            "place_name": "str?",
            "scenario_text": "str?",
            "category": "str?"
        },
    },
    "place_details": {
        "fn": tool_place_details,
        "desc": "Place details (Places API).",
        "schema": {"place_id": "str"},
    },
    "find_nearby_locker": {
        "fn": tool_find_nearby_locker,
        "desc": "Find nearby parcel lockers.",
        "schema": {"place_name": "str", "radius_m": "int?"},
    },
    "mark_as_placed": {
        "fn": tool_mark_as_placed,
        "desc": "Mark order as placed in locker.",
        "schema": {"locker_id": "str", "order_id": "str"},
    },
    "get_nearby_merchants": {
        "fn": tool_get_nearby_merchants,
        "desc": "Nearby alternate restaurants via Google Places.",
        "schema": {"lat": "float", "lon": "float", "radius_m": "int"},
    },
    
    # Roads
    "roads_snap": {
        "fn": tool_roads_snap,
        "desc": "Snap GPS points to roads.",
        "schema": {"points": "[[lat,lon],...]", "interpolate": "bool?"},
    },
    
    # Notifications
    "notify_customer": {
        "fn": tool_notify_customer,
        "desc": "Push notify customer (FCM v1).",
        "schema": {"fcm_token": "str", "message": "str", "voucher": "bool", "title": "str"},
    },
    "notify_passenger_and_driver": {
        "fn": tool_notify_passenger_and_driver,
        "desc": "Push notify both (FCM v1).",
        "schema": {"driver_token": "str", "passenger_token": "str", "message": "str"},
    },
    "notify_resolution": {
        "fn": tool_notify_resolution,
        "desc": "Sends a final resolution notification to both driver and customer.",
        "schema": {"driver_token": "str", "customer_token": "str", "message": "str"}
    },
    
    # Assignment and routing
    "assign_short_nearby_order": {
        "fn": tool_assign_short_nearby_order,
        "desc": "Assign a quick nearby order from orders.json",
        "schema": {"driver_id": "str", "driver_lat": "float", "driver_lon": "float", "radius_km": "float?", "max_total_minutes": "float?"},
    },
    "reroute_driver": {
        "fn": tool_reroute_driver,
        "desc": "Reroute driver to a selected short nearby order",
        "schema": {"driver_id": "str", "driver_lat": "float", "driver_lon": "float"},
    },
    
    # Mediation and evidence
    "initiate_mediation_flow": {
        "fn": tool_initiate_mediation_flow,
        "desc": "Start mediation flow (purges old evidence for a fresh review).",
        "schema": {"order_id": "str"},
    },
    "collect_evidence": {
        "fn": tool_collect_evidence,
        "desc": "Collect evidence photos & notes.",
        "schema": {"order_id": "str", "images": "list[str]?", "notes": "str?"}
    },
    "analyze_evidence": {
        "fn": tool_analyze_evidence,
        "desc": "Analyze evidence with Gemini Vision.",
        "schema": {"order_id": "str", "notes": "str?"}
    },
    "issue_instant_refund": {
        "fn": tool_issue_instant_refund,
        "desc": "Refund instantly.",
        "schema": {"order_id": "str"}
    },
    "exonerate_driver": {
        "fn": tool_exonerate_driver,
        "desc": "Clear driver fault.",
        "schema": {"driver_id": "str"}
    },
    "log_merchant_packaging_feedback": {
        "fn": tool_log_merchant_packaging_feedback,
        "desc": "Feedback to merchant packaging.",
        "schema": {"merchant_id": "str", "feedback": "str"}
    },
    "contact_recipient_via_chat": {
        "fn": tool_contact_recipient_via_chat,
        "desc": "Chat recipient.",
        "schema": {"recipient_id": "str", "message": "str"}
    },
    "suggest_safe_drop_off": {
        "fn": tool_suggest_safe_drop_off,
        "desc": "Suggest safe place.",
        "schema": {"address": "str"}
    },
    
    # Mock/utility tools
    "get_merchant_status": {
        "fn": tool_get_merchant_status,
        "desc": "Merchant backlog/prep time.",
        "schema": {"merchant_id": "str"}
    },
    "check_flight_status": {
        "fn": get_flight_status,
        "desc": "Flight status check.",
        "schema": {"flight_no": "str"}
    },
    "noop": {
        "fn": tool_noop,
        "desc": "No operation",
        "schema": {}
    },
    "ask_user": {
        "fn": lambda **kwargs: {"awaiting": True, **kwargs},
        "desc": "Pause chain and ask user a question; resume when answered.",
        "schema": {"question_id": "str", "question": "str", "expected": "str?", "options": "list[str]?"},
    },
}