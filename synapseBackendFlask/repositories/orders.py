"""
Orders repository for managing order data
"""
import json
import os
from typing import Dict, Any

ORDERS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "orders.json")

def load_orders() -> Dict[str, Any]:
    """Load orders from JSON file"""
    if not os.path.exists(ORDERS_FILE):
        return {"orders": []}
    
    with open(ORDERS_FILE, "r") as f:
        return json.load(f)

def save_orders(data: Dict[str, Any]) -> None:
    """Save orders to JSON file"""
    with open(ORDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_pending_orders():
    """Get all pending orders"""
    data = load_orders()
    return [o for o in data.get("orders", []) if o.get("status") == "pending"]

def assign_order(order_id: str, driver_id: str) -> bool:
    """Assign an order to a driver"""
    data = load_orders()
    for order in data.get("orders", []):
        if order.get("id") == order_id:
            order["status"] = "assigned"
            order["assignedTo"] = driver_id
            save_orders(data)
            return True
    return False

def get_order(order_id: str) -> Dict[str, Any]:
    """Get a specific order by ID"""
    data = load_orders()
    for order in data.get("orders", []):
        if order.get("id") == order_id:
            return order
    return {}