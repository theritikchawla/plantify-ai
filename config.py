"""
config.py - all the settings for Plantify AI live here.

Why a separate file? If you ever want to change a limit (for example the
maximum upload size), you change it in ONE place instead of hunting through
the whole project.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# The folder that contains this file (the project folder).
BASE_DIR = Path(__file__).resolve().parent

# Read the hidden ".env" file (if it exists) and load its values as
# environment variables. This is how your API key gets into the program
# without ever being written in the source code.
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# AI settings
# ---------------------------------------------------------------------------
# Model names change over time. Keep them in .env so you can change them
# without touching the code. The defaults below were checked against Google's
# pricing and model documentation on 27 October 2026.
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_FALLBACK_MODEL = "gemini-3.5-flash-lite"


def get_model_names() -> list[str]:
    """Return the main model followed by the backup model (no duplicates)."""
    main_model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    backup_model = (
        os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL).strip()
        or DEFAULT_FALLBACK_MODEL
    )
    return [main_model] if backup_model == main_model else [main_model, backup_model]


# Values people commonly forget to replace in .env.
_PLACEHOLDER_KEYS = {"", "your_api_key_here", "paste_your_key_here"}


def get_api_key() -> str:
    """Return the API key from the environment (never print or log this!)."""
    return os.getenv("GEMINI_API_KEY", "").strip()


def api_key_is_configured() -> bool:
    """True if a real-looking key has been set in .env."""
    return get_api_key().lower() not in _PLACEHOLDER_KEYS


# How long we wait for Google before giving up.
REQUEST_TIMEOUT_SECONDS = 60

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
MAX_UPLOAD_MB = 5
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}  # checked on the real file content
MAX_IMAGE_PIXELS = 40_000_000  # refuse absurdly large images
MAX_IMAGE_SIDE = 1600  # photos are shrunk to this before being sent (saves quota)

# ---------------------------------------------------------------------------
# Protection against accidental repeated requests
# ---------------------------------------------------------------------------
# NOTE: these limits live in the browser session. They reduce accidents (double
# clicks, re-uploading the same photo) but they do NOT guarantee you stay under
# Google's quota - only Google's own limits do that.
MIN_SECONDS_BETWEEN_REQUESTS = 10
MAX_REQUESTS_PER_SESSION = 25

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_PATH = Path(os.getenv("PLANTIFY_DB_PATH", BASE_DIR / "data" / "plantify.db"))


def setup_logging() -> None:
    """Print simple log lines to the terminal. We never log keys or images."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
