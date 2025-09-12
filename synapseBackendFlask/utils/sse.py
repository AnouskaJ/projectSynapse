"""
Server-Sent Events utilities
"""
import json
from typing import Any

def sse(data: Any) -> str:
    """Format data for Server-Sent Events"""
    payload = json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
    return f"data: {payload}\n\n"

def sse_headers():
    """Standard headers for SSE responses"""
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }