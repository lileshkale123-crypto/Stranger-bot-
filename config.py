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

# Premium plans paid with Telegram Stars. Add a plan by adding a line here.
PLANS = [
    {"id": "d7", "days": 7, "stars": 50, "title": "7 Days"},
    {"id": "d30", "days": 30, "stars": 150, "title": "30 Days"},
    {"id": "d90", "days": 90, "stars": 350, "title": "90 Days"},
]
PLAN_BY_ID = {p["id"]: p for p in PLANS}

# Matching
FILTER_FALLBACK_SECONDS = 30  # offer "match with anyone" if a premium filter finds nobody

# Anti-spam: max messages per window (seconds) while chatting
RATE_LIMIT_MSGS = 6
RATE_LIMIT_WINDOW = 4.0

# Referral rewards: every REFERRAL_TARGET friends who finish setup via your link = REFERRAL_REWARD_DAYS of VIP.
REFERRAL_TARGET = int(os.getenv("REFERRAL_TARGET", "25"))
REFERRAL_REWARD_DAYS = int(os.getenv("REFERRAL_REWARD_DAYS", "7"))
REFERRAL_REPEAT = os.getenv("REFERRAL_REPEAT", "1") == "1"  # False = reward only once per person
