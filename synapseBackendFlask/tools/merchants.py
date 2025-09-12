"""
Merchant-related tools
"""
from typing import Dict, Any

from ..services.places import get_place_details

def tool_place_details(place_id: str) -> Dict[str, Any]:
    """Get detailed information about a place"""
    return get_place_details(place_id)

# Mock tools that would integrate with real systems
def tool_noop(**kwargs) -> Dict[str, Any]:
    """No operation tool"""
    return {"noop": True, **kwargs}