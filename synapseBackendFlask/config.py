"""
Configuration management for Synapse
"""
import os
import json
from typing import Dict, Any
from pathlib import Path

# Look for config.json in the same directory as this file
CONFIG_FILE = Path(__file__).with_name("config.json")

class Config:
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from config.json if it exists"""
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                self._config = json.load(f)
    
    def get(self, key: str, default: str = "") -> str:
        """Get configuration value from environment or config file"""
        return os.getenv(key, self._config.get(key, default))

# Global config instance
config = Config()

# Configuration constants
GOOGLE_MAPS_API_KEY  = config.get("GOOGLE_MAPS_API_KEY", "").strip()
ROUTES_KEY       = config.get("ROUTES_KEY", GOOGLE_MAPS_API_KEY).strip()
ROUTES_ENDPOINT  = config.get("ROUTES_ENDPOINT", "https://routes.googleapis.com/directions/v2:computeRoutes").strip()
GEMINI_API_KEY       = config.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL         = config.get("GEMINI_MODEL", "gemini-2.0-flash")

FIREBASE_PROJECT_ID  = config.get("FIREBASE_PROJECT_ID", "").strip()
SERVICE_ACCOUNT_FILE = config.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

REQUIRE_AUTH         = config.get("REQUIRE_AUTH", "false").lower() == "true"
CORS_ORIGINS         = [o.strip() for o in config.get("CORS_ORIGINS", "*").split(",")]

MAX_STEPS            = int(config.get("MAX_STEPS", "7"))
MAX_SECONDS          = int(config.get("MAX_SECONDS", "120"))
STREAM_DELAY         = float(config.get("STREAM_DELAY", "0.10"))
BASELINE_SPEED_KMPH  = float(config.get("BASELINE_SPEED_KMPH", "40.0"))

DEFAULT_CUSTOMER_TOKEN   = config.get("DEFAULT_CUSTOMER_TOKEN", "").strip()
DEFAULT_DRIVER_TOKEN     = config.get("DEFAULT_DRIVER_TOKEN", "").strip()
DEFAULT_PASSENGER_TOKEN  = config.get("DEFAULT_PASSENGER_TOKEN", "").strip()

FCM_DRY_RUN              = config.get("FCM_DRY_RUN", "false").lower() == "true"

# Validate critical config
if not GOOGLE_MAPS_API_KEY:
    raise RuntimeError(f"GOOGLE_MAPS_API_KEY missing. Looked in env and {CONFIG_FILE}")
if not GEMINI_API_KEY:
    raise RuntimeError(f"GEMINI_API_KEY missing. Looked in env and {CONFIG_FILE}")
