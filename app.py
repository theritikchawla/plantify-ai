"""
app.py - the Streamlit user interface for Plantify AI.

Run it with:   streamlit run app.py

Streamlit re-runs this whole file from top to bottom every time you click a
button or upload a file. Values that must survive between runs (like the
current result) are kept in st.session_state.
"""

import logging
import sqlite3
import time
from datetime import datetime

import streamlit as st

import ai_service
import config
import database
import utils
from ai_service import PlantAIError

config.setup_logging()
logger = logging.getLogger("plantify.app")

st.set_page_config(page_title="Plantify AI", page_icon="🌿", layout="wide")

# Light CSS: a softer look. Everything else uses Streamlit's built-in styling.
st.markdown(
    """
    <style>
        .block-container { padding-top: 2rem; max-width: 1200px; }
        .tagline { color: #4b6a4f; font-size: 1.05rem; margin-top: -0.5rem; }
        .sci-name { font-style: italic; color: #4b6a4f; font-size: 1.15rem; margin-top: -0.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Titles and icons for the care guide cards (order = display order).
CARE_SECTIONS = [
    ("sunlight", "☀️", "Sunlight"),
    ("watering", "💧", "Watering"),
    ("soil", "🪴", "Soil"),
    ("humidity_and_temperature", "🌡️", "Humidity & temperature"),
    ("fertiliser", "🌱", "Fertiliser"),
    ("repotting", "🔄", "Repotting"),
    ("common_problems", "🍂", "Common problems"),
    ("pests_and_prevention", "🐛", "Pests & prevention"),
]

GENERAL_DISCLAIMER = (
    "AI identification can be wrong, and plant care varies with your climate, the season, "
    "pot size and growing conditions. Treat this as a starting point, and double-check "
    "anything important (especially pet safety) with a trusted source or a professional."
)


# ---------------------------------------------------------------------------
# Start-up
# ---------------------------------------------------------------------------
def init_state() -> None:
    """Create the session values we need (only the first time)."""
    defaults = {
        "result": None,  # the result currently shown
        "saved_id": None,  # database id of the current result, if saved
        "last_request_time": None,
        "request_count": 0,
        "results_cache": {},  # image fingerprint -> {"result": ..., "saved_id": ...}
        "uploader_version": 0,  # changing this resets the file uploader
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def start_database() -> bool:
    """Create the database if needed. Returns False if that failed."""
    try:
        database.init_db()
        return True
    except (sqlite3.Error, OSError):
        logger.error("Could not initialise the database")
        return False


# ---------------------------------------------------------------------------
# Small display helpers
# ---------------------------------------------------------------------------
def format_time(iso_text: str) -> str:
    """Show the stored UTC time in the computer's local time zone."""
    try:
        return datetime.fromisoformat(iso_text).astimezone().strftime("%d %b %Y, %H:%M")
    except ValueError:
        return iso_text


def show_confidence(result: dict) -> None:
    level = result["confidence"]
    explanation = result["confidence_explanation"]
    message = f"**Confidence: {level}.** {explanation}".strip()
    if level == "high":
        st.success(message)
    elif level == "medium":
        st.info(message)
    else:
        st.warning(message)


def show_result_details(result: dict) -> None:
    """Show the identification and the care guide (used for new AND saved results)."""
    st.header(result["common_name"])
    if result["scientific_name"]:
        st.markdown(f'<div class="sci-name">{result["scientific_name"]}</div>', unsafe_allow_html=True)
    show_confidence(result)

    if result["needs_better_photo"]:
        st.warning(f"📷 A clearer photo would help. {result['better_photo_advice']}")

    identification_tab, care_tab = st.tabs(["🔍 Identification", "🪴 Care guide"])

    with identification_tab:
        if result["description"]:
            st.write(result["description"])
        if result["visible_characteristics"]:
            st.subheader("What I could see")
            for characteristic in result["visible_characteristics"]:
                st.markdown(f"- {characteristic}")
        if result["alternatives"]:
            with st.expander("Other possibilities"):
                for alternative in result["alternatives"]:
                    title = alternative["common_name"] or alternative["scientific_name"]
                    scientific = (
                        f" ({alternative['scientific_name']})"
                        if alternative["common_name"] and alternative["scientific_name"]
                        else ""
                    )
                    st.markdown(f"**{title}**{scientific}")
                    if alternative["reason"]:
                        st.caption(alternative["reason"])

    with care_tab:
        st.info(f"🐾 **Pet safety:** {result['care']['pet_toxicity']}")
        columns = st.columns(2)
        for position, (field, icon, title) in enumerate(CARE_SECTIONS):
            with columns[position % 2]:
                with st.container(border=True):
                    st.markdown(f"**{icon} {title}**")
                    st.write(result["care"][field])
        st.caption(GENERAL_DISCLAIMER)


def show_save_controls() -> None:
    """Tell the user whether the current result is saved (or let them save it)."""
    result = st.session_state.result
    if st.session_state.saved_id:
        st.caption("✅ Saved to your History (stored only on this computer).")
    elif ai_service.is_saveable(result):
        if st.button("💾 Save to history"):
            save_current_result()
            st.rerun()


def save_current_result() -> None:
    try:
        st.session_state.saved_id = database.save_identification(st.session_state.result)
        # Remember the id for the cache too, so re-identifying the same photo shows "saved".
        for entry in st.session_state.results_cache.values():
            if entry["result"] is st.session_state.result:
                entry["saved_id"] = st.session_state.saved_id
    except (sqlite3.Error, OSError):
        logger.error("Could not save to the database")
        st.warning("I could not save this result to your history, but you can still read it here.")


# ---------------------------------------------------------------------------
# Page: Identify
# ---------------------------------------------------------------------------
def run_identification(prepared_bytes: bytes, mime_type: str) -> None:
    """Handle a click on 'Identify Plant', including the safety checks."""
    image_id = utils.fingerprint(prepared_bytes)

    # 1. Same photo as before? Reuse the answer - no new API call.
    cached = st.session_state.results_cache.get(image_id)
    if cached:
        saved_id = cached["saved_id"]
        if saved_id and database.get_identification(saved_id) is None:
            saved_id = None  # the user deleted it from History meanwhile
        st.session_state.result = cached["result"]
        st.session_state.saved_id = saved_id
        st.info("You already identified this photo, so I reused that answer (no new AI request).")
        return

    # 2. Protect against accidental repeated requests.
    if st.session_state.request_count >= config.MAX_REQUESTS_PER_SESSION:
        st.warning(
            "You have reached the request limit for this session. "
            "Refresh the page to start a new session."
        )
        return
    wait_seconds = utils.seconds_until_next_request(
        st.session_state.last_request_time, time.time(), config.MIN_SECONDS_BETWEEN_REQUESTS
    )
    if wait_seconds > 0:
        st.warning(f"Please wait {wait_seconds} more second(s) before the next request.")
        return

    # Count the attempt BEFORE calling, so failed attempts also slow you down.
    st.session_state.last_request_time = time.time()
    st.session_state.request_count += 1

    # 3. Ask the AI.
    try:
        with st.spinner("Looking closely at your plant..."):
            result = ai_service.identify_plant(prepared_bytes, mime_type)
    except PlantAIError as error:
        st.error(error.user_message)
        return
    except Exception as error:  # noqa: BLE001 - never show raw errors to the user
        logger.error("Unexpected error during identification: %s", type(error).__name__)
        st.error("Something unexpected went wrong. Please try again.")
        return

    st.session_state.result = result
    st.session_state.saved_id = None
    st.session_state.results_cache[image_id] = {"result": result, "saved_id": None}

    if ai_service.is_saveable(result):
        save_current_result()


def reset_current_result() -> None:
    """Clear the result and empty the file uploader."""
    st.session_state.result = None
    st.session_state.saved_id = None
    st.session_state.uploader_version += 1


def page_identify() -> None:
    st.title("🌿 Plantify AI")
    st.markdown(
        '<p class="tagline">Upload a photo of a plant to find out what it might be '
        "and how to look after it.</p>",
        unsafe_allow_html=True,
    )

    with st.expander("🔒 Privacy: what happens to my photo?"):
        st.write(
            "When you click **Identify Plant**, your photo is sent to Google's Gemini API for "
            "analysis. On Google's free tier, Google's terms say submitted content may be used to "
            "improve its products, so please upload plant photos only (no people, documents or "
            "private places). Before sending, Plantify shrinks the photo and removes hidden "
            "metadata such as GPS location. Plantify does not save your photo - only the text "
            "result, in a database on this computer."
        )

    if not config.api_key_is_configured():
        st.error(
            "No API key found yet. Open the `.env` file in the project folder, set "
            "`GEMINI_API_KEY`, and restart the app. The README explains how."
        )

    left, right = st.columns([1, 1.5], gap="large")

    with left:
        uploaded_file = st.file_uploader(
            "Upload a plant photo",
            type=config.ALLOWED_EXTENSIONS,
            help=f"JPG, PNG or WEBP, up to {config.MAX_UPLOAD_MB} MB.",
            key=f"uploader_{st.session_state.uploader_version}",
        )

        prepared_bytes, mime_type = None, None
        if uploaded_file is not None:
            try:
                prepared_bytes, mime_type = utils.prepare_image(uploaded_file.getvalue())
            except utils.ImageValidationError as error:
                st.error(str(error))
            else:
                st.image(prepared_bytes, caption="Your photo")

        identify_clicked = st.button(
            "🔍 Identify Plant",
            type="primary",
            disabled=prepared_bytes is None or not config.api_key_is_configured(),
        )
        if st.button("↩️ Clear / start over"):
            reset_current_result()
            st.rerun()

        if identify_clicked and prepared_bytes is not None:
            run_identification(prepared_bytes, mime_type)

    with right:
        result = st.session_state.result
        if result is None:
            st.markdown("### 👋 Welcome!")
            st.info(
                "Upload a clear, well-lit photo of one plant, then press **Identify Plant**. "
                "Close-ups of the leaves (and flowers, if any) work best."
            )
        elif not result["is_plant"]:
            st.warning(
                "I could not see a plant in this photo. "
                + (result["better_photo_advice"] or "Please try another photo.")
            )
        else:
            show_result_details(result)
            show_save_controls()


# ---------------------------------------------------------------------------
# Page: History
# ---------------------------------------------------------------------------
def page_history() -> None:
    st.title("📚 History")
    st.caption("Plants you have identified. Stored only in a database on this computer.")

    try:
        items = database.list_identifications()
    except (sqlite3.Error, ValueError):
        logger.error("Could not read the history")
        st.error("I could not read your history right now.")
        return

    if not items:
        st.info("Nothing here yet. Identify a plant and it will appear in this list.")
        return

    for item in items:
        title = f"{item['common_name']} - {item['scientific_name'] or 'scientific name unknown'}"
        with st.expander(f"{title}  ·  {format_time(item['created_at'])}"):
            show_result_details(item["details"])
            if st.button("🗑️ Delete this record", key=f"delete_{item['id']}"):
                database.delete_identification(item["id"])
                st.rerun()


# ---------------------------------------------------------------------------
# Page: About
# ---------------------------------------------------------------------------
def page_about() -> None:
    st.title("ℹ️ About Plantify AI")
    st.write(
        "Plantify AI is a portfolio project that combines a vision-capable AI model, "
        "structured JSON output, input validation and a small SQLite database behind a "
        "simple Streamlit interface."
    )
    st.subheader("Good to know")
    st.markdown(
        "- The AI gives a **best guess**, not a certain answer. Blurry photos or several plants "
        "in one picture make mistakes more likely.\n"
        "- Care advice is general. Watering, light and feeding depend on your home and the season.\n"
        "- Pet-toxicity notes are only a hint. Always confirm with a veterinarian.\n"
        "- Free-tier limits and model availability can change, and may depend on your account and region."
    )
    st.caption(f"Model in use: {', '.join(config.get_model_names())}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    init_state()

    if not start_database():
        st.error("I could not create the local database. Check that the project folder is writable.")
        st.stop()

    st.sidebar.title("🌿 Plantify AI")
    page = st.sidebar.radio("Menu", ["Identify", "History", "About"], label_visibility="collapsed")
    st.sidebar.divider()
    # We only show WHETHER a key exists - never the key itself.
    st.sidebar.caption("API key: " + ("found ✅" if config.api_key_is_configured() else "missing ❌"))
    st.sidebar.caption(
        f"AI requests this session: {st.session_state.request_count}/{config.MAX_REQUESTS_PER_SESSION}"
    )

    if page == "Identify":
        page_identify()
    elif page == "History":
        page_history()
    else:
        page_about()


main()
