"""
Time utilities
"""
import time

def now_iso() -> str:
    """Get current time in ISO format"""
    return time.strftime("%Y-%m-%dT%H:%M:%S")