"""
Firebase Cloud Messaging (FCM) service
"""
import os
from typing import Dict, Any, Optional

from google.oauth2 import service_account
from google.auth.transport.requests import Request as GARequest

from ..config import SERVICE_ACCOUNT_FILE, FIREBASE_PROJECT_ID, FCM_DRY_RUN
from ..utils.http import http_post
from ..logger import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

def _fcm_access_token() -> str:
    """Generate OAuth2 access token using the service account JSON for FCM v1."""
    if not SERVICE_ACCOUNT_FILE or not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS file not found for FCM.")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    creds.refresh(GARequest())
    return creds.token

def _is_placeholder_token(token: str) -> bool:
    """Check if token is a placeholder/dummy value"""
    t = (token or "").strip().lower()
    return (not t) or (t in {"token","customer_token","driver_token","passenger_token","str"})

def send_notification(token: str, title: str, body: str, data: Optional[dict] = None) -> Dict[str, Any]:
    """Send FCM notification via v1 API"""
    # Dev mode: pretend delivered so UI flow can be tested
    if FCM_DRY_RUN:
        log.info("[fcm_send] DRY_RUN on → simulating delivered")
        return {"delivered": True, "dryRun": True}

    if _is_placeholder_token(token):
        return {"delivered": False, "reason": "missing_or_placeholder_device_token"}

    access_token = _fcm_access_token()
    base = f"https://fcm.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/messages:send"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # Use WebPush envelope for browsers
    msg = {
        "message": {
            "token": token,
            "webpush": {
                "headers": {"Urgency": "high"},
                "notification": {
                    "title": title,
                    "body": body,
                    "requireInteraction": True,
                },
                "fcmOptions": {"link": "https://your.app/alternates"},
                "data": data or {},
            },
        }
    }

    log.info(f"[fcm_send] sending WebPush title='{title}'")
    res = http_post(base, msg, headers, timeout=10)
    ok = bool(res) and (("name" in res) or res.get("ok") is True)
    if not ok:
        return {"delivered": False, "error": res}
    return {"delivered": True, "fcmResponse": res}