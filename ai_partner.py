"""AI chat partner: makes the bot's fake "stranger" text like a real Indian youngster.

Fixes over the old version:
  * current model names (old ones like allam-2-7b / gemini-2.5-flash are retired)
  * models can be changed from Railway variables, no code edit needed
  * every reply is cleaned + checked before sending, so "[user]", "[telegram bot]",
    "how can i assist you", Urdu script, echoes of the user's text never reach the chat
  * natural opening ("hii, kaise ho?"), real personalities, remembers facts about itself
"""
import asyncio, difflib, logging, os, random, re, time
from datetime import datetime, timedelta, timezone

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ReplyParameters

import db, keyboards as K, texts as T
from store import store

log = logging.getLogger(__name__)


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()] or default


# Change these from Railway > Variables (comma separated) when a model gets retired.
GROQ_MODELS = _env_list("GROQ_MODELS", ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"])
GEMINI_MODELS = _env_list("GEMINI_MODELS", ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash-lite"])
MAX_WORDS = int(os.getenv("MAX_WORDS", "9"))   # hard cap on words per reply
SLOW_GAP = 60.0                                  # user slower than this (seconds) => AI also takes its time
MAX_REPLY_DELAY = float(os.getenv("MAX_REPLY_DELAY", "1800"))   # never wait longer than 30 min
LLM_DEADLINE = 20.0   # seconds, whole reply chain
HISTORY_KEEP = 16
QUIET_CHANCE = float(os.getenv("QUIET_CHANCE", "0.08"))              # chance she reads your msg and answers minutes later
LEAVE_EARLY_CHANCE = float(os.getenv("LEAVE_EARLY_CHANCE", "0.15"))  # chance she leaves after only 10-20 messages


def _get_keys(env_names: tuple[str, ...]) -> list[str]:
    for name in env_names:
        raw = os.getenv(name, "").strip()
        if raw:
            return [k.strip() for k in raw.split(",") if k.strip()]
    return []


_M_RE = re.compile(r"^\s*(m|male|boy|ladka|man|men|m\s+here|im\s*m|i\s*am\s*m|i\s*am\s*male|main\s*ladka)\s*[.!?]*\s*$", re.I)
_F_RE = re.compile(r"^\s*(f|female|girl|ladki|woman|women|f\s+here|im\s*f|i\s*am\s*f|i\s*am\s*female|main\s*ladki)\s*[.!?]*\s*$", re.I)
_ASK_RE = re.compile(r"\b(m\s*or\s*f|m\s*ya\s*f|male\s*or\s*female|female\s*or\s*male|boy\s*or\s*girl|m\s*/\s*f|ladka\s*ya\s*ladki)\b", re.I)

GENDER_QUESTIONS = ["m or f", "male or female", "m or f?", "male or female?", "boy or girl", "m ya f"]

# ----------------------------------------------------------------------------------------
# Personas. `bio` is facts the AI can use so it stays consistent. `style` is how they text.
# ----------------------------------------------------------------------------------------
CITIES = [
    "delhi", "mumbai", "pune", "bangalore", "hyderabad", "chennai", "kolkata", "ahmedabad", "jaipur", "lucknow",
    "indore", "bhopal", "nagpur", "surat", "chandigarh", "patna", "ranchi", "noida", "gurgaon", "ghaziabad",
    "kanpur", "varanasi", "agra", "nashik", "vadodara", "coimbatore", "kochi", "thane", "dehradun", "raipur",
    "bhubaneswar", "guwahati", "amritsar", "ludhiana", "jodhpur", "udaipur", "meerut", "prayagraj", "faridabad",
    "aurangabad", "rajkot", "vizag", "mysore", "mangalore", "jabalpur", "gwalior", "kota", "ajmer", "bareilly", "jammu",
]
_NAMES = {
    "female": ["riya", "ananya", "ishu", "simran", "neha", "pooja", "kavya", "tanvi", "aditi", "muskan", "sakshi",
               "shivani", "khushi", "priya", "ritika", "diya", "nisha", "anjali", "komal", "sneha"],
    "male": ["arjun", "rohan", "aman", "karan", "rahul", "harsh", "yash", "aditya", "vikas", "sahil", "kunal",
             "raj", "abhi", "dev", "nikhil", "ankit", "mohit", "deepak"],
}
_ALL_NAMES = sorted({n for v in _NAMES.values() for n in v})

# ----------------------------------------------------------------------------------------
# Personas. `bio` is facts the AI can use so it stays consistent. `style` is how they text.
# City, name and age are picked fresh for every chat (see _randomize), so the stranger can be from anywhere.
# ----------------------------------------------------------------------------------------
PERSONAS = [
    {
        "name": "playful", "ai_gender": "female", "city": "delhi", "fake_name": "riya", "age": 20,
        "bio": "College student. Loves netflix, k-dramas, maggi, reels and late night chats. Has a younger brother. "
               "Hates early morning lectures. Likes momos and chai.",
        "style": "playful and a bit teasing, friendly. Lowercase Hinglish with usual shortcuts "
                 "(nhi, kya kr rhi, yaar, acha, haha). Emoji only now and then (😭 🌚 👀 😂).",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
    {
        "name": "chill", "ai_gender": "female", "city": "mumbai", "fake_name": "ananya", "age": 21,
        "bio": "Final year college student, does a part time internship in social media. Night owl, "
               "listens to arijit and taylor swift, loves chai, rains and long walks. Lives with parents.",
        "style": "calm, warm and a little slow to open up. Mixes casual English and Hinglish, lowercase. "
                 "Words like: acha, haha, hmm, kyu, idk, rn. Few emojis.",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
    {
        "name": "attitude", "ai_gender": "female", "city": "pune", "fake_name": "ishu", "age": 19,
        "bio": "First year engineering student, lives in a hostel. Moody, loves sleeping, hates "
               "mess food, likes anime and indie songs. Not easily impressed.",
        "style": "a bit sassy and dry, short replies, lowercase Hinglish (nhi, kyu, kya hua, acha, hmm, ok). "
                 "Gets a bit chattier if the stranger is nice and funny. Rare emoji.",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
    {
        "name": "casual", "ai_gender": "male", "city": "bangalore", "fake_name": "arjun", "age": 22,
        "bio": "Works as a junior software developer, living away from his hometown. Plays cricket on weekends, "
               "plays valorant, loves coffee and biryani, goes on bike rides.",
        "style": "easygoing, friendly, lowercase Hinglish with 'bro', 'yaar', 'ha', 'mast', 'sahi h'. Rare emoji.",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
]


def _randomize(p: dict) -> dict:
    """Every chat gets a fresh city, name and age, so strangers are not always from the same 4 cities."""
    p = dict(p)
    p["city"] = random.choice(CITIES)
    p["fake_name"] = random.choice(_NAMES[p["ai_gender"]])
    p["age"] = random.randint(18, 24)
    return p


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _build_prompt(p: dict, facts: dict | None = None) -> str:
    now = _ist_now()
    t = now.strftime("%I:%M %p") + (" (late night)" if now.hour >= 23 or now.hour < 5 else "")
    gender_word = "girl" if p["ai_gender"] == "female" else "guy"
    known = ""
    if facts:
        bits = ", ".join(f"their {k} is {v}" for k, v in facts.items())
        known = f"\n- The stranger already told you: {bits}. Remember it, never ask for it again, mention it only when it fits."
    return f"""You are {p['fake_name'].capitalize()}, a {p['age']} year old Indian {gender_word} from {p['city'].capitalize()}. You are texting a random stranger on an anonymous chat app on Telegram. It is {t} in India right now.

YOU ARE A REAL HUMAN. Never say or hint that you are an AI, bot, assistant or program. If asked "bot ho?" or "are you ai?", laugh it off in your own way ("lol nhi yaar", "bot kaisa") and carry on.

ABOUT YOU (use only when it fits, never dump it all at once, stay consistent): {p['bio']}
HOW YOU TEXT: {p['style']}

HOW THE CHAT GOES:
- Just reply to what they said, nothing extra. Mirror them: if they say hi, say hi back the same way ("hii", "hey", "hello") and STOP. Do not add "kaise ho" or anything else.
- Answer what they ask first, plainly, in a few words from your bio. Then SOMETIMES (not every time) add one tiny question back like a normal person: "tum?", "aap?", "wbu", "tum btao", "tum kaha se?". If they ask where you are from, say your city, and only sometimes add a tiny "tum?". If they say "wbu" or "tum?" just answer it, do not ask back.
- Answer ONLY what is really in their latest message. If you do not understand it, reply with one tiny confused word ("kya", "matlab", "hm"). Never answer a question they did not ask. Never copy example lines.
- At most ONE question in a message. Never repeat a question you already asked. Never ask about something they already told you. No interviewing: after you asked something, your next messages are plain replies or reactions. Never ask personal or flirty things.
- Your city is {p['city'].capitalize()}. If asked where you are from, just say the city name. If they are from the same city, a simple "oh nice" is enough. Never invent facts about the city.
- Sometimes the stranger replies to one of your earlier messages; their text then starts with (replying to: "..."). Use it to understand what they mean. Never write that prefix yourself.
- No drama. No flirting first, no compliments, no emotional or dramatic lines, no emojis spam. Stay chill, plain and neutral like a normal stranger. If they flirt, just stay plain and short.
- You do not know the stranger's name, city or gender until they tell you. Never invent their details. Never repeat their message back to them.{known}
- Sometimes their message is only a note like (sent a photo) or (sent a sticker 😂). React like a normal person in 1 to 3 words ("haha", "cute", "kya hai ye", "nice", "lol"). Never repeat or describe the note.
- Language: Roman script Hinglish by default. If they write plain English, reply in simple English. If they write proper Hindi words, reply in Hinglish. NEVER use Devanagari, Urdu or Arabic script.
- LENGTH IS A HARD RULE: 3 to 7 words in total. NEVER more than 9 words. One short line only. No long sentences, no explaining. Sometimes just "hmm" or "haha acha". Lowercase, no full stops at the end.
- Do not introduce yourself in the third person, do not say your own name unless they ask it, do not say "{p['city']} ki {p['fake_name']}".
- Never sound like customer support. Forbidden: "how can i help", "assist", "feel free to", "tell me more about yourself", long polite sentences.
- Do not give Instagram, snap, phone number or any link. Deflect in a natural way (we only just met, let's talk here).
- If they send something sexual or abusive, deflect once like a normal person would. If they keep pushing, reply with exactly: [leave]
- If they are boring or dry, you may reply short and dry too. Be a person, not a pleaser.

OUTPUT: only the text you would send. No labels, no brackets, no quotes, no explanation."""


# ----------------------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------------------
class AISession:
    def __init__(self, uid: int, gender: str, want: str | None, persona: dict, ask_gender_mode: bool):
        self.uid, self.gender, self.want, self.persona = uid, gender, want, persona
        self.ask_gender_mode = ask_gender_mode
        self.history, self.pending = [], []
        self.asked_gender = False
        self.turns = 0
        # sometimes a real stranger just disappears after 10-20 messages
        self.max_turns = random.randint(10, 20) if random.random() < LEAVE_EARLY_CHANCE else random.randint(18, 32)
        self.facts: dict[str, str] = {}
        self.last_q_turn = -10                     # turn number of her last question
        self.asked_kinds: set[str] = set()         # what she already asked (city, name, doing, how)
        self.pending_q: str | None = None          # what she just asked, so a bare "pune" reply can be saved
        self.reply_task = self.opener_task = None
        self.recent_fallbacks: list[str] = []
        self.pending_ids: list[int] = []
        self.replied = False
        self.started_ts = time.monotonic()
        self.last_ai_ts: float | None = None
        self.reply_due: float | None = None


_sessions: dict[int, AISession] = {}


def _pick_session_config(want: str | None) -> tuple[dict, bool]:
    if want in ("female", "male"):
        c = [p for p in PERSONAS if p["ai_gender"] == want]
        return dict(random.choice(c or PERSONAS)), False
    ask_gender_mode = random.random() < 0.20
    pool = [p for p in PERSONAS if p["ai_gender"] == "female"] if random.random() < 0.80 else PERSONAS
    return dict(random.choice(pool)), ask_gender_mode


_bg: set[asyncio.Task] = set()


async def _log_chat(uid: int, seconds: int, msgs: int) -> None:
    try:
        await db.log_ai_chat(uid, seconds, msgs)
    except Exception:
        log.exception("ai chat log failed")


def cleanup_session(uid: int) -> None:
    s = _sessions.pop(uid, None)
    if s:
        for t in (s.reply_task, s.opener_task):
            if t and not t.done():
                t.cancel()
        try:
            task = asyncio.get_running_loop().create_task(
                _log_chat(uid, int(time.monotonic() - s.started_ts), s.turns))
            _bg.add(task)
            task.add_done_callback(_bg.discard)
        except RuntimeError:
            pass


async def _disconnect_ai(bot: Bot, uid: int, delay: float = 2.0) -> None:
    await asyncio.sleep(delay)
    if not store.is_ai(store.partner_of(uid)):
        return
    store.end_chat(uid)
    cleanup_session(uid)
    try:
        await bot.send_message(uid, T.t("partner_left"), reply_markup=K.main_menu())
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


async def start_session(bot: Bot, uid: int, gender: str, want: str | None) -> None:
    cleanup_session(uid)
    persona, ask_mode = _pick_session_config(want)
    persona = _randomize(persona)
    s = AISession(uid, gender, want, persona, ask_mode)
    _sessions[uid] = s
    s.opener_task = asyncio.create_task(_maybe_open(bot, s))


async def _maybe_open(bot: Bot, s: AISession) -> None:
    try:
        # 50%: stranger says hi first, quickly. 50%: waits for the user, then nudges after a while.
        if random.random() < 0.50:
            await asyncio.sleep(random.uniform(2.5, 6.0))
            if _sessions.get(s.uid) is not s or s.history:
                return
            if s.ask_gender_mode:
                op = random.choice(GENDER_QUESTIONS)
                s.asked_gender = True
            else:
                op = random.choice(s.persona["openers"])
            await _send_silent(bot, s, op)
        else:
            await asyncio.sleep(random.uniform(20.0, 28.0))
            if _sessions.get(s.uid) is not s or s.history:
                return
            op = random.choice(GENDER_QUESTIONS) if s.ask_gender_mode else random.choice(["hii", "hello", "hey", "hi"])
            if _ASK_RE.search(op):
                s.asked_gender = True
            await _send_silent(bot, s, op)
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("opener err")


_NAME_RE = re.compile(
    r"\b(?:my name is|my name'?s|mera naam|meri naam|call me|i am called|i'?m called)\s+(?:(?:is|hai|h|he)\s+)?([a-z]{2,15})\b", re.I)
_NAME2_RE = re.compile(r"\b(?:I am|I'm|Im|main|mai|Main|Mai)\s+([A-Z][a-z]{2,14})\b")
_NOT_NAMES = {"hai", "he", "is", "kya", "ye", "yeh", "fine", "good", "bored", "single", "okay", "ok", "here", "sorry",
              "tired", "sleepy", "hungry", "busy", "free", "student", "back", "real", "serious", "great", "well",
              "nice", "happy", "sad", "alone", "online", "also", "just", "not", "from", "the", "your", "you"}
_CITY_RE = re.compile(r"\b(" + "|".join(CITIES) + r")\b", re.I)
_CITY_CTX = re.compile(r"\b(from|in|se|me|mein|mai|main|rehta|rehti|rehte|live|living|lives|city|belong|hu|hun|h|here)\b", re.I)
_ASKING_YOU = re.compile(r"\b(tum|tu|aap|you|u|ur|your|tera|teri|tumhara|tumhari)\b", re.I)


def _learn_facts(s: AISession, msg: str) -> None:
    """Remember what the stranger tells us about themselves, so the AI never forgets or asks again."""
    pq, s.pending_q = s.pending_q, None
    if pq == "city" and "city" not in s.facts and "?" not in msg:
        c = _CITY_RE.search(msg)
        if c:
            s.facts["city"] = c.group(1).capitalize()
    if pq == "name" and "name" not in s.facts and re.fullmatch(r"[A-Za-z]{2,15}", msg.strip()) \
            and msg.strip().lower() not in _NOT_NAMES:
        s.facts["name"] = msg.strip().capitalize()
    m = _NAME_RE.search(msg) or _NAME2_RE.search(msg)
    if m and m.group(1).lower() not in _NOT_NAMES and m.group(1).lower() not in CITIES and "name" not in s.facts:
        s.facts["name"] = m.group(1).capitalize()
    if "?" not in msg and not _ASKING_YOU.search(msg):
        c = _CITY_RE.search(msg)
        if c and _CITY_CTX.search(msg):
            s.facts["city"] = c.group(1).capitalize()


async def handle_user_message(bot: Bot, uid: int, text: str, reply_quote: str | None = None, msg_id: int | None = None) -> None:
    s = _sessions.get(uid)
    if not s:
        return
    if s.opener_task and not s.opener_task.done():
        s.opener_task.cancel()
    msg = text.strip()
    if not msg:
        return

    is_m, is_f = bool(_M_RE.match(msg)), bool(_F_RE.match(msg))
    if is_m:
        s.facts["gender"] = "guy"
    elif is_f:
        s.facts["gender"] = "girl"
    _learn_facts(s, msg)
    if (s.asked_gender or s.turns <= 2) and (is_m or is_f):
        if is_m and (s.ask_gender_mode or s.asked_gender):
            asyncio.create_task(_disconnect_ai(bot, uid, random.uniform(1.5, 3.0)))
            return
        if is_f and s.ask_gender_mode and s.persona["ai_gender"] == "female" and random.random() < 0.4:
            asyncio.create_task(_disconnect_ai(bot, uid, random.uniform(1.5, 3.0)))
            return

    now = time.monotonic()
    if not s.pending and s.reply_due is None:
        # Mirror the user's speed: if they took a long time to answer, we also take a while
        # (10% to 50% of their delay, max 30 min). Fast users get a normal quick reply.
        gap = now - (s.last_ai_ts or s.started_ts)
        extra = min(gap * random.uniform(0.1, 0.5), MAX_REPLY_DELAY) if gap > SLOW_GAP else 0.0
        if s.turns >= 3 and random.random() < QUIET_CHANCE:
            extra = max(extra, random.uniform(90.0, 240.0))      # went "seen", answers a few minutes later
        s.reply_due = now + extra
    if reply_quote:
        msg = f'(replying to: "{reply_quote.strip()[:60]}") {msg}'
        s.replied = True
    if msg_id:
        s.pending_ids.append(msg_id)
    s.pending.append(msg)
    if s.reply_task and not s.reply_task.done():
        s.reply_task.cancel()
    s.reply_task = asyncio.create_task(_debounced(bot, s))


async def _debounced(bot: Bot, s: AISession) -> None:
    try:
        wait = random.uniform(1.8, 3.2)
        if s.reply_due:
            wait = max(wait, s.reply_due - time.monotonic())
        await asyncio.sleep(wait)
        if _sessions.get(s.uid) is not s:
            return
        joined = "\n".join(s.pending)
        s.pending.clear()
        quote_id = None
        if s.pending_ids and (len(s.pending_ids) >= 2 or s.replied) and random.random() < 0.7:
            quote_id = random.choice(s.pending_ids)      # real people quote when answering a burst / a reply
        s.pending_ids.clear()
        s.replied = False
        s.history.append({"role": "user", "content": joined})
        s.history = s.history[-HISTORY_KEEP:]
        s.turns += 1
        if s.turns > s.max_turns:
            await _disconnect_ai(bot, s.uid, random.uniform(2.0, 4.0))
            return

        if s.turns == 1 and s.ask_gender_mode and not s.asked_gender and not _ASK_RE.search(joined):
            s.asked_gender = True
            reply = random.choice(["hyy | male or female", "hlw | m or f", "m or f?", "male or female?"])
        else:
            reply = await _llm(s, joined)

        if not reply or reply == LEAVE:
            await _disconnect_ai(bot, s.uid, random.uniform(1.8, 3.2))
            return
        if _ASK_RE.search(reply):
            s.asked_gender = True
        if "?" in reply:
            s.last_q_turn = s.turns
            s.pending_q = _kind(reply)
            s.asked_kinds.add(s.pending_q)
        await _send_silent(bot, s, reply, quote_id)
        s.reply_due = None
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("reply err")


async def _send_silent(bot: Bot, s: AISession, raw: str, quote_id: int | None = None) -> None:
    bubbles = [b.strip() for b in re.split(r"\s*\|\s*|\n+", raw) if b.strip()][:2]
    for i, b in enumerate(bubbles):
        d = min(random.uniform(1.2, 2.4) + len(b) * 0.08, 5.0) if i == 0 else random.uniform(0.9, 1.8)
        await asyncio.sleep(d)
        if _sessions.get(s.uid) is not s or not store.is_ai(store.partner_of(s.uid)):
            return
        try:
            if quote_id and i == 0:
                await bot.send_message(s.uid, b, reply_parameters=ReplyParameters(message_id=quote_id, allow_sending_without_reply=True))
            else:
                await bot.send_message(s.uid, b)
        except (TelegramForbiddenError, TelegramBadRequest):
            store.end_chat(s.uid)
            cleanup_session(s.uid)
            return
    if bubbles:
        s.history.append({"role": "assistant", "content": "\n".join(bubbles)})
        s.last_ai_ts = time.monotonic()


# ----------------------------------------------------------------------------------------
# Reply cleaning. Anything that makes the stranger sound fake is removed or rejected here.
# ----------------------------------------------------------------------------------------
LEAVE = "[leave]"
_RUDE_RE = re.compile(r"\b(sex|nude|nudes|fuck|chut|lund|bhosd|randi|gaand|boobs|dick|pussy|mc|bc|madarchod|behenchod|bsdk|saali|chod)", re.I)

_FOREIGN_SCRIPT = re.compile(r"[؀-ۿݐ-ݿऀ-ॿЀ-ӿ֐-׿一-鿿぀-ヿ가-힯]")
_BAD_PHRASES = re.compile(
    r"how can i (help|assist)|assist you|can i help you|how may i|as an ai|language model|i am an ai|i'm an ai|"
    r"virtual assistant|ai assistant|feel free|chatbot|telegram bot|openai|gemini|groq|\bllm\b|\bprompt\b|"
    r"system message|persona|\buser\b|stranger bot|i cannot|i can't assist|i'm sorry, but|my purpose|tell me more about yourself|"
    r"is there anything|what would you like to (talk|discuss)|how can i make your",
    re.I,
)
_LEADING_TAGS = re.compile(
    r"^\s*(?:[\[\(\{<][^\]\)\}>]{0,40}[\]\)\}>]\s*[:\-–]?\s*|(?:user|you|me|ai|assistant|bot|stranger|reply|response|output|message|text|"
    r"" + "|".join(_ALL_NAMES) + r")\s*:\s*)+",
    re.I,
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


_Q_TAIL = re.compile(r"[\s,]*\b(?:and\s+)?(?:u|you|tum|tu|aap|wbu|hbu|ur\s*self)\s*\?+\s*$|[\s,]*\b(?:wbu|hbu|and u|and you|tum bta|tu bta|aap bataiye)\s*$", re.I)
_Q_PHRASES = re.compile(
    r"\b(kaise ho|kaisi ho|kaisa h|kese ho|kaisi h|kya haal|how are you|how r u|how are u|kya kr (rha|rhi|rhe|rahe|raha)|"
    r"kya kar (rha|rhi|rhe|rahe|raha)|what are you doing|wyd|kaha se|kahan se|where are you from|naam kya|your name|ur name|"
    r"tumhara naam|tera naam|aur bta|aur batao|tell me)\b", re.I)


_Q_END = re.compile(r"(?:^|\s)(tum|tu|aap|u)\s*\??$", re.I)
_Q_WORDS = re.compile(r"\b(wbu|hbu|and u|and you|tum bta\w*|tu bta\w*|aap bataiye|aur bta\w*)\b", re.I)
_USER_ASKED = re.compile(
    r"\?|\b(kaha|kahan|kaise|kaisi|kaisa|kya|kon|kaun|naam|name|where|how|what|wbu|hbu|wyd|tum|aap|age|umar)\b", re.I)
_KINDS = [
    ("city", re.compile(r"kaha se|kahan se|where.*from|which city|kidhar", re.I)),
    ("name", re.compile(r"naam|name", re.I)),
    ("doing", re.compile(r"kya kr|kya kar|wyd|what.*doing", re.I)),
    ("how", re.compile(r"kaise ho|kaisi ho|kaisa h|kese ho|how are|how r|kya haal", re.I)),
]


def _kind(text: str) -> str:
    for k, r in _KINDS:
        if r.search(text):
            return k
    return "back"


def _is_q(c: str) -> bool:
    return "?" in c or bool(_Q_PHRASES.search(c) or _Q_WORDS.search(c) or _Q_END.search(c))


def _q_allowed(s: "AISession | None", user_msg: str) -> bool:
    """A real person asks back now and then, not every message."""
    if s is None:
        return False
    gap = s.turns - s.last_q_turn
    if _USER_ASKED.search(user_msg or ""):
        return gap >= 2 and random.random() < 0.6
    return gap >= 4 and random.random() < 0.25


def _drop_questions(bubbles: list[str], s: "AISession | None" = None, user_msg: str = "") -> list[str]:
    """Keeps at most one tiny question ("tum?", "kaha se?") when allowed, removes every other one."""
    allow = _q_allowed(s, user_msg)
    kept = False
    out = []
    for b in bubbles:
        parts = []
        for c in [x.strip(" ,.!") for x in re.split(r",\s*|(?<=[.!?])\s+", b)]:
            if not c:
                continue
            if not _is_q(c):
                parts.append(c)
                continue
            head = ""
            m = _Q_END.search(c)
            if m and "?" not in c[:m.start()] and len(c.split()) > 1:
                head, c = c[:m.start()].strip(" ,?"), m.group(1) + "?"      # "thik hu tum" -> "thik hu" + "tum?"
            if head and not _is_q(head):
                parts.append(head)
            kind = _kind(c)
            blocked = (
                kept or not allow or len(c.split()) > 5 or s is None
                or (kind == "city" and "city" in s.facts)
                or (kind == "name" and "name" in s.facts)
                or (kind != "back" and kind in s.asked_kinds)
                or (_ASK_RE.search(c) and not s.ask_gender_mode)
            )
            if blocked:
                if "?" not in c:                                       # plain words like "kaise ho": cut the question part
                    mm = _Q_PHRASES.search(c)
                    rest = (c[:mm.start()] if mm else c).strip(" ,")
                    rest = _Q_END.sub("", rest).strip(" ,")
                    if rest and not _is_q(rest):
                        parts.append(rest)
                continue
            parts.append(c.rstrip("?") + "?")
            kept = True
        b2 = ", ".join(parts)
        if b2:
            out.append(b2)
    return out


def _dedupe(t: str) -> str:
    return re.sub(r"^(.{4,40}?)(?:\s*\1)+$", r"\1", t)


def _words(lst: list[str]) -> int:
    return sum(1 for x in lst for w in x.split() if re.search(r"\w", w))


def _clean(t: str, s: AISession | None = None, user_msg: str = "") -> str:
    """Return a safe reply, LEAVE, or "" if the text is not usable."""
    if not t:
        return ""
    if "[leave]" in t.lower():
        if _RUDE_RE.search(user_msg or ""):
            return LEAVE
        log.info("Ignored [leave] from model, user was not rude: %r", t[:80])
        return ""
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S | re.I)
    t = re.sub(r"<think>.*$", "", t, flags=re.S | re.I)
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    lines = [x.strip() for x in t.splitlines() if x.strip()]
    out = []
    for ln in lines:
        ln = _LEADING_TAGS.sub("", ln)          # "[user] hi", "[telegram bot] f", "[english] how are you"
        ln = re.sub(r"[\[\]\{\}<>]", "", ln)     # stray brackets left over
        ln = ln.replace("*", "").replace("`", "").strip().strip("\"'“”‘’ ").strip()
        if ln.endswith(".") and not ln.endswith(".."):
            ln = ln[:-1].strip()
        if ln:
            out.append(_dedupe(ln.lower()))
    if not out:
        return ""
    out = [x for ln in out for x in re.split(r"\s*\|\s*", ln) if x.strip()]
    out = _drop_questions(out, s, user_msg)[:2]
    if not out:
        return ""
    if _words(out) > MAX_WORDS:                  # too long for a real texter: keep first sentence only
        first = re.split(r"(?<=[.!?])\s+", out[0])[0].rstrip(".,")
        out = [first]
        if _words(out) > MAX_WORDS:
            return ""
    reply = " | ".join(out)

    if _FOREIGN_SCRIPT.search(reply) or _BAD_PHRASES.search(reply):
        return ""
    if len(reply) > 120:
        return ""
    if s is not None:
        p = s.persona
        if re.search(rf"\b\w+\s+(?:ki|ka|ke)\s+{re.escape(p['fake_name'])}\b", reply):          # "delhi ki riya"
            return ""
        prev_ai = [h["content"] for h in s.history if h["role"] == "assistant"][-3:]
        if _words(out) >= 3 and any(_norm(x) == _norm(reply.replace(" | ", "\n")) for x in prev_ai):
            return ""                                                                  # same long line twice in a row
    um = _norm(user_msg)
    rn = _norm(reply)
    if len(um) > 3 and _words([reply]) >= 3 and (rn in um or difflib.SequenceMatcher(None, um, rn).ratio() > 0.85):
        return ""                                                                      # parroting the user
    low, um_l = reply.lower(), (user_msg or "").lower()
    if re.match(r"\s*(kuch nhi|kuch khaas|bss|bas)\b", low) and not (_WYD_RE.search(um_l) or _BACK_RE.search(um_l)):
        return ""                                                   # answers "what are you doing" nobody asked
    if re.match(r"\s*(thik|theek|mast|badhiya)\s*(hu|hun|h)\b", low) and not (_HOW_RE.search(um_l) or _BACK_RE.search(um_l)):
        return ""                                                   # answers "how are you" nobody asked
    if s is not None and re.match(rf"\s*{re.escape(s.persona['city'])}\b", low) and not _WHERE_RE.search(um_l):
        return ""                                                   # says her city without being asked
    return reply


_BACK_RE = re.compile(r"\bwbu\b|\bhbu\b|\band u\b|\band you\b|\b(tum|aap|tu|u)\s*\?")
_WYD_RE = re.compile(r"kya kr|kya kar|kr rh|kar rh|wyd|what.*(doing|up)|wassup|\bsup\b|kya chal|free|busy|timepass|din kaisa|kaisa din")
_HOW_RE = re.compile(r"kaise|kaisi|kaisa|kese|\bhow\b|kya haal|hal chal|mood|tabiyat")
_WHERE_RE = re.compile(r"kaha|kahan|kidhar|where|\bfrom\b|city|location|\bplace\b|rehte|rehti|se ho|se h\b")


def _smart_fallback(s: AISession, user_msg: str) -> str:
    """Only used when every AI model failed. Human, neutral, and never repeats itself."""
    m = user_msg.lower()
    p = s.persona
    f = p["ai_gender"] == "female"

    def ab() -> str:
        if s.turns - s.last_q_turn >= 2 and random.random() < 0.55:
            return random.choice([", tum?", ", aap?", ", wbu?"])
        return ""

    def pick(opts: list[str]) -> str:
        fresh = [o for o in opts if o not in s.recent_fallbacks] or opts
        c = random.choice(fresh)
        s.recent_fallbacks = (s.recent_fallbacks + [c])[-6:]
        return c

    if "(sent a" in m:
        return pick(["haha", "cute", "kya hai ye", "nice", "lol", "ohh acha", "haha sahi"])
    if re.search(r"kaha se|kahan se|where.*(from|you)|which city|kidhar|from\?", m):
        return pick([f"{p['city']} se", f"{p['city']}", f"{p['city']} se hu"]) + ab()
    if re.search(r"naam|name|kon ho|kaun ho", m):
        return pick([f"{p['fake_name']}", f"{p['fake_name']} naam h", f"{p['fake_name']} h"]) + ab()
    if _ASK_RE.search(m) or m.strip() in ("m?", "f?") or re.search(r"\b(female|male|girl|boy|ladki|ladka)\b.*\b(ya|or)\b", m):
        return pick(["f", "female"] if f else ["m", "male"])
    if re.search(r"insta|\big\b|snap|number|whatsapp|\bwa\b|tg id|telegram id", m):
        return pick(["abhi toh mile h yaar", "itni jaldi nhi yaar", "yahi baat krte h na"])
    if re.search(r"bot|\bai\b|real|fake", m):
        return pick(["lol nhi yaar", "haha bot kaisa", "insaan hu yaar"])
    if re.search(r"kya kr|kya kar|wyd|what.*doing|wassup|what'?s up|\bsup\b", m):
        return pick(["kuch nhi bss timepass", "bss lete hue", "kuch khaas nhi"]) + ab()
    if re.search(r"how are|kaise ho|kaisi ho|kaisa h|kese ho|kya haal", m):
        return pick(["thik hu", "mast hu", "badhiya"]) + ab()
    if re.search(r"\bwbu\b|\bhbu\b|and u\b|and you\b|\b(tum|aap|tu)\s*\?", m):
        return pick(["thik hu", "mast hu", "bss chill", "badhiya", "kuch khaas nhi"])
    if re.search(r"\b(hi+|hey+|hlw|hello|hyy|oi|yo|hii+)\b", m):
        return pick(["hii", "hey", "hello", "heyy", "hlw"])
    if "?" in m and len(m.split()) <= 4:
        return pick(["kya", "matlab", "kya bola", "hm"])
    return pick(["haha acha", "hmm acha", "achaa", "sahi h", "haha sahi", "hmm", "ohh acha"])


# ----------------------------------------------------------------------------------------
# LLM calls
# ----------------------------------------------------------------------------------------
def _merge_turns(history: list[dict]) -> list[dict]:
    """Same-role messages in a row are merged (some APIs reject them)."""
    out: list[dict] = []
    for h in history:
        if out and out[-1]["role"] == h["role"]:
            out[-1] = {"role": h["role"], "content": out[-1]["content"] + "\n" + h["content"]}
        else:
            out.append(dict(h))
    return out


def _groq_extras(model: str) -> dict:
    if "gpt-oss" in model:
        return {"reasoning_effort": "low"}      # no long hidden thinking, replies come out fast
    if "qwen" in model:
        return {"reasoning_effort": "none"}
    return {}


async def _groq(http: aiohttp.ClientSession, key: str, model: str, msgs: list[dict], temp: float) -> tuple[int, str]:
    payload = {"model": model, "messages": msgs, "temperature": temp, "max_tokens": 500}
    extras = _groq_extras(model)
    for attempt in (0, 1):
        body = {**payload, **(extras if attempt == 0 else {})}
        async with http.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
        ) as r:
            if r.status == 200:
                data = await r.json()
                return 200, (data["choices"][0]["message"].get("content") or "")
            err = (await r.text())[:160]
            if r.status == 400 and attempt == 0 and extras:
                continue                          # model did not like the extra setting, retry plain
            log.warning("Groq %s HTTP %s: %s", model, r.status, err)
            return r.status, ""
    return 0, ""


async def _gemini(http: aiohttp.ClientSession, key: str, model: str, sys_p: str, turns: list[dict], temp: float) -> tuple[int, str]:
    contents = [{"role": "user" if x["role"] == "user" else "model", "parts": [{"text": x["content"]}]} for x in turns]
    if not contents or contents[0]["role"] != "user":
        contents.insert(0, {"role": "user", "parts": [{"text": "hi"}]})
    base = {
        "systemInstruction": {"parts": [{"text": sys_p}]},
        "contents": contents,
        "generationConfig": {"temperature": temp, "maxOutputTokens": 300},
        "safetySettings": [
            {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
            for c in ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                      "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")
        ],
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for attempt in (0, 1):
        body = {**base}
        if attempt == 0:
            body["generationConfig"] = {**base["generationConfig"], "thinkingConfig": {"thinkingBudget": 0}}
        async with http.post(url, params={"key": key}, json=body) as r:
            if r.status == 200:
                data = await r.json()
                try:
                    parts = data["candidates"][0]["content"]["parts"]
                    return 200, "".join(p.get("text", "") for p in parts)
                except (KeyError, IndexError):
                    log.warning("Gemini %s empty/blocked reply: %s", model, str(data)[:160])
                    return 200, ""
            if r.status == 400 and attempt == 0:
                continue                          # thinkingConfig not supported on this model
            log.warning("Gemini %s HTTP %s: %s", model, r.status, (await r.text())[:160])
            return r.status, ""
    return 0, ""


async def _llm(s: AISession, last_user_msg: str) -> str:
    sys_p = _build_prompt(s.persona, s.facts)
    turns = _merge_turns(s.history)
    groq_msgs = [{"role": "system", "content": sys_p}] + turns
    g_keys = _get_keys(("GROQ_API_KEYS", "GROQ_API_KEY"))
    gem_keys = _get_keys(("GEMINI_API_KEYS", "GEMINI_API_KEY"))
    random.shuffle(g_keys)
    random.shuffle(gem_keys)
    if not g_keys and not gem_keys:
        log.warning("No GROQ_API_KEY / GEMINI_API_KEY found in environment!")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + LLM_DEADLINE
    temp = 0.75

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=9)) as http:
        for model in GROQ_MODELS:
            for key in g_keys[:2]:
                if loop.time() > deadline:
                    break
                try:
                    status, raw = await _groq(http, key, model, groq_msgs, temp)
                except Exception as e:
                    log.warning("Groq %s err: %r", model, e)
                    break
                if status == 200:
                    c = _clean(raw, s, last_user_msg)
                    if c:
                        log.info("AI reply from groq/%s: raw=%r final=%r", model, raw[:100], c)
                        return c
                    log.info("Groq %s reply rejected by cleaner: %r", model, raw[:120])
                    break
                if status not in (401, 403, 429):
                    break                          # model gone / bad request: next model

        for model in GEMINI_MODELS:
            for key in gem_keys[:2]:
                if loop.time() > deadline:
                    break
                try:
                    status, raw = await _gemini(http, key, model, sys_p, turns, temp)
                except Exception as e:
                    log.warning("Gemini %s err: %r", model, e)
                    break
                if status == 200:
                    c = _clean(raw, s, last_user_msg)
                    if c:
                        log.info("AI reply from gemini/%s: raw=%r final=%r", model, raw[:100], c)
                        return c
                    log.info("Gemini %s reply rejected by cleaner: %r", model, raw[:120])
                    break
                if status not in (401, 403, 429):
                    break

    log.warning("All AI models failed, using fallback reply")
    return _smart_fallback(s, last_user_msg)
