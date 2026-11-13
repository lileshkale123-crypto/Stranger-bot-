import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x.strip().isdigit()}

def _keys(raw: str) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()]

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_IDS = _ids(os.getenv("ADMIN_IDS", ""))
BOT_NAME = os.getenv("BOT_NAME", "Stranger Talk")

GROQ_API_KEYS = _keys(os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY", ""))
GEMINI_API_KEYS = _keys(os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY", ""))

AI_MATCH_DELAY_MIN = float(os.getenv("AI_MATCH_DELAY_MIN", "6.0"))
AI_MATCH_DELAY_MAX = float(os.getenv("AI_MATCH_DELAY_MAX", "12.0"))

AGE_BRACKETS = ["18-21", "22-25", "26+"]
REGIONS = [
    ("IN", "🇮🇳 India"),
    ("US", "🇺🇸 USA"),
    ("GB", "🇬🇧 UK"),
    ("PK", "🇵🇰 Pakistan"),
    ("BD", "🇧🇩 Bangladesh"),
    ("OTHER", "🌍 Other"),
]

INTRO_FRAME_DELAY = 0.8

PLANS = [
    {"id": "d7", "days": 7, "stars": 50, "title": "7 Days"},
    {"id": "d30", "days": 30, "stars": 150, "title": "30 Days"},
    {"id": "d90", "days": 90, "stars": 350, "title": "90 Days"},
]
PLAN_BY_ID = {p["id"]: p for p in PLANS}

FILTER_FALLBACK_SECONDS = 30
RATE_LIMIT_MSGS = 6
RATE_LIMIT_WINDOW = 4.0

REFERRAL_TARGET = int(os.getenv("REFERRAL_TARGET", "25"))
REFERRAL_REWARD_DAYS = int(os.getenv("REFERRAL_REWARD_DAYS", "7"))
REFERRAL_REPEAT = os.getenv("REFERRAL_REPEAT", "1") == "1"
