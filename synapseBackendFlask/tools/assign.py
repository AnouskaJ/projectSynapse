"""
Driver assignment and rerouting tools
"""
from typing import Dict, Any

from ..repositories.orders import load_orders, save_orders
from ..utils.geo import haversine_km, estimate_trip_minutes
from ..config import BASELINE_SPEED_KMPH
from ..logger import get_logger

log = get_logger(__name__)

def tool_assign_short_nearby_order(driver_id: str, driver_lat: float, driver_lon: float,
                                   radius_km: float = 6.0, max_total_minutes: float = 25.0) -> Dict[str, Any]:
    """
    Pick the best 'quick' order near the driver:
    - pickup within `radius_km`
    - pickup->drop ETA <= `max_total_minutes`
    Marks the order as 'assigned' to driver_id in orders.json.
    """
    data = load_orders()
    candidates = []
    
    for order in data.get("orders", []):
        if order.get("status") != "pending":
            continue
        
        pickup = order["pickup"]
        dropoff = order["dropoff"]
        
        dist_to_pick = haversine_km(driver_lat, driver_lon, pickup["lat"], pickup["lon"])
        if dist_to_pick > radius_km:
            continue
            
        job_minutes = estimate_trip_minutes(pickup["lat"], pickup["lon"], dropoff["lat"], dropoff["lon"], BASELINE_SPEED_KMPH)
        total_minutes = round(job_minutes + (dist_to_pick / BASELINE_SPEED_KMPH) * 60.0, 1)
        
        if total_minutes <= max_total_minutes:
            candidates.append({
                "order": order, 
                "distToPickupKm": round(dist_to_pick, 2),
                "jobMinutes": job_minutes, 
                "totalMinutes": total_minutes
            })

    if not candidates:
        return {"assigned": False, "reason": "no_quick_orders_found"}

    # Choose the quickest total
    best = min(candidates, key=lambda c: c["totalMinutes"])
    
    # Mark as assigned
    for order in data["orders"]:
        if order["id"] == best["order"]["id"]:
            order["status"] = "assigned"
            order["assignedTo"] = driver_id
            break
    
    save_orders(data)

    return {
        "assigned": True,
        "driver_id": driver_id,
        "order": best["order"],
        "distToPickupKm": best["distToPickupKm"],
        "jobMinutes": best["jobMinutes"],
        "totalMinutes": best["totalMinutes"]
    }

def tool_reroute_driver(driver_id: str, driver_lat: float, driver_lon: float) -> Dict[str, Any]:
    """
    Wrapper that calls assign_short_nearby_order and returns a friendly payload
    used by the policy.
    """
    res = tool_assign_short_nearby_order(driver_id, driver_lat, driver_lon)
    if not res.get("assigned"):
        return {"driver_id": driver_id, "rerouted": False, "reason": res.get("reason")}
    
    order = res["order"]
    newtask = f"Pickup {order['id']} at {order['pickup']['address']} → drop at {order['dropoff']['address']} (≈{res['totalMinutes']} min)"
    
    return {
        "driver_id": driver_id,
        "rerouted": True,
        "newTask": newtask,
        "assignment": res
    }

# Mock merchant status tool
def tool_get_merchant_status(merchant_id: str) -> Dict[str, Any]:
    """Mock: Get merchant backlog/prep time"""
    return {
        "merchant_id": merchant_id, 
        "prepTimeMin": 40, 
        "backlogOrders": 12, 
        "response": True
    }