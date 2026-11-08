import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional (Railway injects env vars)
    pass


def _ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x.strip().isdigit()}


BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_IDS = _ids(os.getenv("ADMIN_IDS", ""))
BOT_NAME = os.getenv("BOT_NAME", "Stranger Talk")

# Onboarding options (edit here, no code changes needed elsewhere)
AGE_BRACKETS = ["18-21", "22-25", "26+"]
REGIONS = [
    ("IN", "🇮🇳 India"),
    ("US", "🇺🇸 USA"),
    ("GB", "🇬🇧 UK"),
    ("PK", "🇵🇰 Pakistan"),
    ("BD", "🇧🇩 Bangladesh"),
    ("OTHER", "🌍 Other"),
]

# Intro animation: seconds between frames (keep >= 0.6 to respect Telegram edit limits)
INTRO_FRAME_DELAY = 0.8
