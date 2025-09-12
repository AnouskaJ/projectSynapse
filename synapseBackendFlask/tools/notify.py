"""
Notification tools using FCM
"""
import json
from typing import Dict, Any, Optional

from ..services.fcm import send_notification
from ..config import DEFAULT_CUSTOMER_TOKEN, DEFAULT_DRIVER_TOKEN, DEFAULT_PASSENGER_TOKEN

def tool_notify_resolution(driver_token: Optional[str], customer_token: Optional[str], message: str) -> Dict[str, Any]:
    """Sends a final resolution notification to both the driver and the customer."""
    d_res = send_notification(driver_token or "", "Dispute Resolution", message)
    c_res = send_notification(customer_token or "", "Dispute Resolution", message)
    return {"driver_notified": d_res.get("delivered"), "customer_notified": c_res.get("delivered")}

def tool_notify_customer(fcm_token: Optional[str], message: str, voucher: bool = False, title: str = "Order Update") -> Dict[str, Any]:
    """Send notification to customer"""
    return send_notification(
        fcm_token or DEFAULT_CUSTOMER_TOKEN or "", 
        title, 
        message, 
        {"voucher": json.dumps(bool(voucher))}
    )

def tool_notify_passenger_and_driver(driver_token: Optional[str], passenger_token: Optional[str], message: str) -> Dict[str, Any]:
    """Push notify both driver and passenger"""
    d = send_notification(driver_token or DEFAULT_DRIVER_TOKEN or "", "Route Update", message) if driver_token else {"delivered": False}
    p = send_notification(passenger_token or DEFAULT_PASSENGER_TOKEN or "", "Route Update", message) if passenger_token else {"delivered": False}
    return {"driverDelivered": d.get("delivered"), "passengerDelivered": p.get("delivered")}