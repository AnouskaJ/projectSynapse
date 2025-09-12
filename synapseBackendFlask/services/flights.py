"""
Flight status service (mock implementation)
"""
from typing import Dict, Any

def get_flight_status(flight_no: str) -> Dict[str, Any]:
    """Mock flight status check - in production this would connect to a real flight API"""
    return {
        "flight": flight_no, 
        "status": "DELAYED", 
        "delayMin": 45
    }