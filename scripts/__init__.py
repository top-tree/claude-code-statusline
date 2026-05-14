"""Path constants for the custom statusline package."""
import os

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS    = os.path.join(BASE_DIR, "sessions")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
