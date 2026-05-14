"""Configuration loading from config.json."""
import json
from . import CONFIG_FILE


def load_config() -> dict | None:
    """Read pricing config. Returns None on missing, invalid, or non-dict file."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return cfg if isinstance(cfg, dict) else None
