"""
Logging configuration for Synapse
"""
import logging

def setup_logging():
    """Configure logging for the application"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def get_logger(name: str = "synapse") -> logging.Logger:
    """Get a logger instance with the given name"""
    # This will now safely get a logger after basicConfig has been called.
    return logging.getLogger(name)

# A global logger instance for the module.
# Note: The logger is defined here, but setup_logging() is called in app.py.
log = get_logger("synapse")