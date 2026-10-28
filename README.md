Plantify AI

Upload a plant photo, get a likely identification with honest uncertainty, a
beginner-friendly care guide, and a local history of everything you identified.

Portfolio project: Python | Streamlit | Google Gemini API (Interactions API, vision +
structured JSON output) | SQLite | pytest.

Status: written and unit-tested without network access. The Streamlit UI and the
live Gemini call have "not" been run by the author of this code yet, follow the
manual checklist below and record your own results.

Architecture

```
Browser (Streamlit UI)  ->  app.py
                              |-- utils.py        validate/shrink image, fingerprint, cooldown
                              |-- ai_service.py   Gemini call, JSON schema, validation, error mapping
                              |-- database.py     SQLite: save / list / get / delete
                              '-- config.py       settings, .env loading, limits
```

| File | Purpose |
|---|---|
| `app.py` | The web interface (Identify / History / About pages) |
| `ai_service.py` | Talks to Gemini; validates every AI answer before it is shown or saved |
| `database.py` | SQLite storage; table is created automatically at start-up |
| `utils.py` | Image checks (real format, size, rotation, metadata stripping) and throttling helpers |
| `config.py` | Model names, limits, paths; reads `.env` |
| `tests/` | Automated tests that use a fake AI client (no API calls, no cost) |

Key design choices
1. Structured output: the AI must fill in a JSON schema; the reply is then parsed and
  cleaned (`parse_and_validate`). Malformed replies produce a friendly error, never a crash.
2. Honesty: the prompt and validation push low-confidence cases towards "please send a
  clearer photo" and alternatives instead of a confident guess. Unknown care facts show
  "No reliable information available." instead of invented details.
3. Privacy: photos are shrunk and re-saved (this removes GPS/EXIF data), sent with
  `store=False`, and never written to disk by this app.
4. Quota protection (soft): same-photo cache, 10-second cooldown, 25 requests per browser
  session. These reduce accidents but "cannot guarantee" you stay under Google's quota.
5. Backup model: if the main model returns 404/429/503, one retry on a backup model.

AI provider and free tier (checked 27 Oct 2026)
SDK: official `google-genai` (Python 2.3.0+ is required for the Interactions API).
Default model: `gemini-3.8-flash`; backup: `gemini-3.5-flash-lite`. Google's pricing page
  lists both with a free tier. Free-tier rate limits, model availability and policies can
  change and may depend on your account and region, check
  https://ai.google.dev/gemini-api/docs/pricing and
  https://ai.google.dev/gemini-api/docs/rate-limits.
On the free tier Google's terms say submitted content may be used to improve its products.

Setup on Windows (PowerShell)
See the step-by-step guide given with this project. Short version:
```powershell
py --version
cd C:\path\to\plantcare-ai
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
notepad .env          
streamlit run app.py
python -m pytest      # run the tests
```
If PowerShell refuses to activate the environment, use "Command Prompt" instead and run
`.venv\Scripts\activate.bat`.

Usage
1. Open https://plantify-ai-akskbgsj9jlpmlcsjmv2b9.streamlit.app/
2. Upload a JPG/PNG/WEBP (max 5 MB) and press "Identify Plant".
3. Read the Identification and Care guide tabs. Results are saved automatically.
4. "History" lets you reopen or delete saved results. "Clear / start over" resets the page.

Manual checklist
[ ] App starts and shows the welcome message with no errors in the terminal.
[ ] Without an API key, a clear message appears and the button is disabled.
[ ] A `.txt` file renamed to `.jpg` is rejected with a friendly message.
[ ] A clear photo of one plant returns a name, confidence, care guide.
[ ] Pressing Identify twice on the same photo makes no second API request.
[ ] A blurry photo / photo of a mug gives uncertainty or "no plant" not a confident guess.
[ ] The result appears in History; deleting it removes it.
[ ] `data/plantify.db` and `.env` are NOT tracked by git (`git status`).

Manual evaluation plan
Use 8-10 photos you are allowed to use (your own plants, or public-domain photos).
Include: 3 clear single plants, 2 close-ups of leaves, 1 flowering plant, 1 blurry photo,
1 photo with several plants, 1 non-plant (e.g. a mug). Verify the true species yourself
from a reliable source, then fill in:

| # | Photo description | True species (verified how?) | App's top answer | Confidence shown | Correct? | Notes (care advice sensible? uncertainty honest?) |
|---|---|---|---|---|---|---|

Report your own numbers honestly. Do not quote accuracy figures you did not measure.

Limitations
1. Identification is a best guess from one photo; look-alike species are common.
2. Care advice and pet-toxicity notes are AI-generated and general, verify with trusted sources.
3. Rate limits are per Google project and can change; the in-app limits are only a courtesy.
4. HEIC/GIF images are not supported. No user accounts: the history is shared by anyone using this computer's copy.

Troubleshooting
| Message / symptom | Fix |
|---|---|
| "No API key found" | Edit `.env`, set `GEMINI_API_KEY=...`, "restart" Streamlit (it reads `.env` at start) |
| "Google did not accept the API key" | Re-copy the key from https://aistudio.google.com/apikey; no spaces or quotes |
| "free usage limit was reached" | Wait a minute; if persistent, the daily free quota is used - try later |
| "model name is not available" | Set `GEMINI_MODEL` in `.env` to a model listed at https://ai.google.dev/gemini-api/docs/models |
| `AttributeError: ... has no attribute 'interactions'` | Old SDK: `pip install --upgrade google-genai` |
| `'streamlit' is not recognized` | Virtual environment not active, or run `python -m streamlit run app.py` |

Ideas for production
Authentication and per-user history; PostgreSQL; server-side rate limiting; storing a
thumbnail with consent; retrieval from a vetted plant database (e.g. toxicity) instead of
model memory; image-quality pre-checks; structured logging/monitoring; CI with tests;
Docker deployment; an evaluation harness with a labelled photo set; prompt/model versioning.
