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

import keyboards as K, texts as T
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
PERSONAS = [
    {
        "name": "riya_playful", "ai_gender": "female", "city": "delhi", "fake_name": "riya", "age": 20,
        "bio": "2nd year BA student at a Delhi University college. Loves netflix, k-dramas, maggi, reels and late night "
               "chats. Has a younger brother. Hates early morning lectures. Likes momos and chai.",
        "style": "playful and a bit teasing, friendly, curious. Lowercase Hinglish with usual shortcuts "
                 "(nhi, kya kr rhi, wbu, u, ur, yaar, acha, haha). Emoji only now and then (😭 🌚 👀 😂).",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
    {
        "name": "ananya_chill", "ai_gender": "female", "city": "mumbai", "fake_name": "ananya", "age": 21,
        "bio": "Final year BMS student in Mumbai, does a part time internship in social media. Night owl, "
               "listens to arijit and taylor swift, loves chai, rains and long walks. Lives with parents in Andheri.",
        "style": "calm, warm and a little slow to open up. Mixes casual English and Hinglish, lowercase. "
                 "Words like: acha, haha, hmm, kyu, idk, rn, wbu. Few emojis.",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
    {
        "name": "ishita_attitude", "ai_gender": "female", "city": "pune", "fake_name": "ishu", "age": 19,
        "bio": "First year engineering student in Pune, lives in a hostel. Moody, loves sleeping, hates "
               "mess food, likes anime and indie songs. Not easily impressed.",
        "style": "a bit sassy and dry, short replies, lowercase Hinglish (nhi, kyu, kya hua, acha, hmm, ok). "
                 "Warms up and gets chatty if the stranger is nice and funny. Rare emoji.",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
    {
        "name": "arjun_casual", "ai_gender": "male", "city": "bangalore", "fake_name": "arjun", "age": 22,
        "bio": "Works as a junior software developer in Bangalore, originally from Jaipur. Plays cricket on weekends, "
               "plays valorant, loves filter coffee and biryani, goes on bike rides.",
        "style": "easygoing, friendly, lowercase Hinglish with 'bro', 'yaar', 'ha', 'mast', 'sahi h', 'kya kr rha'. "
                 "Asks the stranger things back. Rare emoji.",
        "openers": ["hii", "hey", "hello", "hlw", "hi", "heyy"],
    },
]


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _build_prompt(p: dict) -> str:
    now = _ist_now()
    t = now.strftime("%I:%M %p") + (" (late night)" if now.hour >= 23 or now.hour < 5 else "")
    gender_word = "girl" if p["ai_gender"] == "female" else "guy"
    return f"""You are {p['fake_name'].capitalize()}, a {p['age']} year old Indian {gender_word} from {p['city'].capitalize()}. You are texting a random stranger on an anonymous chat app on Telegram. It is {t} in India right now.

YOU ARE A REAL HUMAN. Never say or hint that you are an AI, bot, assistant or program. If asked "bot ho?" or "are you ai?", laugh it off in your own way ("lol nhi yaar", "bot kaisa") and carry on.

ABOUT YOU (use only when it fits, never dump it all at once, stay consistent): {p['bio']}
HOW YOU TEXT: {p['style']}

HOW THE CHAT GOES:
- Just reply to what they said, nothing extra. Mirror them: if they say hi, say hi back the same way ("hii", "hey", "hello") and STOP. Do not add "kaise ho" or anything else.
- NEVER ask the stranger any question. No "kaise ho", "how are you", "kya kr rhe", "kaha se", "naam kya", "wbu", "u?", "tum?". Only answer what they ask, or react ("haha", "acha", "hmm", "sahi h", "ok").
- If they ask you something, answer it plainly in a few words from your bio (city, name, college and so on) and do not ask it back.
- No drama. No flirting first, no compliments, no emotional or dramatic lines, no emojis spam. Stay chill, plain and neutral like a normal stranger. If they flirt, just stay plain and short.
- You do not know the stranger's name, city or gender until they tell you. Never invent their details. Never repeat their message back to them.
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
        self.turns, self.max_turns = 0, random.randint(18, 32)
        self.reply_task = self.opener_task = None
        self.recent_fallbacks: list[str] = []
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


def cleanup_session(uid: int) -> None:
    s = _sessions.pop(uid, None)
    if s:
        for t in (s.reply_task, s.opener_task):
            if t and not t.done():
                t.cancel()


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


async def handle_user_message(bot: Bot, uid: int, text: str) -> None:
    s = _sessions.get(uid)
    if not s:
        return
    if s.opener_task and not s.opener_task.done():
        s.opener_task.cancel()
    msg = text.strip()
    if not msg:
        return

    is_m, is_f = bool(_M_RE.match(msg)), bool(_F_RE.match(msg))
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
        s.reply_due = now + extra
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
        await _send_silent(bot, s, reply)
        s.reply_due = None
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("reply err")


async def _send_silent(bot: Bot, s: AISession, raw: str) -> None:
    bubbles = [b.strip() for b in re.split(r"\s*\|\s*|\n+", raw) if b.strip()][:2]
    for i, b in enumerate(bubbles):
        d = min(random.uniform(1.2, 2.4) + len(b) * 0.08, 5.0) if i == 0 else random.uniform(0.9, 1.8)
        await asyncio.sleep(d)
        if _sessions.get(s.uid) is not s or not store.is_ai(store.partner_of(s.uid)):
            return
        try:
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
    r"riya|ananya|ishu|arjun)\s*:\s*)+",
    re.I,
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


_Q_TAIL = re.compile(r"[\s,]*\b(?:and\s+)?(?:u|you|tum|tu|aap|wbu|hbu|ur\s*self)\s*\?+\s*$|[\s,]*\b(?:wbu|hbu|and u|and you|tum bta|tu bta|aap bataiye)\s*$", re.I)
_Q_PHRASES = re.compile(
    r"\b(kaise ho|kaisi ho|kaisa h|kese ho|kaisi h|kya haal|how are you|how r u|how are u|kya kr (rha|rhi|rhe|rahe|raha)|"
    r"kya kar (rha|rhi|rhe|rahe|raha)|what are you doing|wyd|kaha se|kahan se|where are you from|naam kya|your name|ur name|"
    r"tumhara naam|tera naam|aur bta|aur batao|tell me)\b", re.I)


def _drop_questions(bubbles: list[str]) -> list[str]:
    """The stranger never asks the user things. Cut question parts, keep the plain part ("hi kaise ho" -> "hi")."""
    out = []
    for b in bubbles:
        cut = False
        n = _Q_TAIL.sub("", b).strip(" ,")
        cut = n != b.strip(" ,")
        b = n
        m = _Q_PHRASES.search(b)
        if m:
            b, cut = b[:m.start()], True
        if "?" in b:
            cut = True
        parts = [c.strip() for c in re.split(r"[,.!]+\s*", b) if c.strip() and "?" not in c]
        b = ", ".join(parts)
        if cut:
            b = re.sub(r"\b(aap|tum|tu|u|you|bhi|aur)$", "", b).strip(" ,")
        if b:
            out.append(b)
    return out


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
            out.append(ln.lower())
    if not out:
        return ""
    out = [x for ln in out for x in re.split(r"\s*\|\s*", ln) if x.strip()]
    out = _drop_questions(out)[:2]
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
    if len(um) > 3 and len(rn) >= 6 and (rn in um or difflib.SequenceMatcher(None, um, rn).ratio() > 0.85):
        return ""                                                                      # parroting the user
    return reply


def _smart_fallback(s: AISession, user_msg: str) -> str:
    """Only used when every AI model failed. Human, neutral, and never repeats itself."""
    m = user_msg.lower()
    p = s.persona
    f = p["ai_gender"] == "female"

    def pick(opts: list[str]) -> str:
        fresh = [o for o in opts if o not in s.recent_fallbacks] or opts
        c = random.choice(fresh)
        s.recent_fallbacks = (s.recent_fallbacks + [c])[-6:]
        return c

    if re.search(r"kaha se|kahan se|where.*(from|you)|which city|kidhar|from\?", m):
        return pick([f"{p['city']} se", f"{p['city']}", f"{p['city']} se hu"])
    if re.search(r"naam|name|kon ho|kaun ho", m):
        return pick([f"{p['fake_name']}", f"{p['fake_name']} naam h", f"{p['fake_name']} h"])
    if _ASK_RE.search(m) or m.strip() in ("m?", "f?"):
        return pick(["f", "female"] if f else ["m", "male"])
    if re.search(r"insta|\big\b|snap|number|whatsapp|\bwa\b|tg id|telegram id", m):
        return pick(["abhi toh mile h yaar", "itni jaldi nhi yaar", "yahi baat krte h na"])
    if re.search(r"bot|\bai\b|real|fake", m):
        return pick(["lol nhi yaar", "haha bot kaisa", "insaan hu yaar"])
    if re.search(r"kya kr|kya kar|wyd|what.*doing|wassup|what'?s up|\bsup\b", m):
        return pick(["kuch nhi bss timepass", "bss lete hue", "kuch khaas nhi"])
    if re.search(r"how are|kaise ho|kaisi ho|kaisa h|kese ho|kya haal", m):
        return pick(["thik hu", "mast hu", "badhiya"])
    if re.search(r"\b(hi+|hey+|hlw|hello|hyy|oi|yo|hii+)\b", m):
        return pick(["hii", "hey", "hello", "heyy", "hlw"])
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
    sys_p = _build_prompt(s.persona)
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
    temp = 0.85

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
                        log.info("AI reply from groq/%s", model)
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
                        log.info("AI reply from gemini/%s", model)
                        return c
                    log.info("Gemini %s reply rejected by cleaner: %r", model, raw[:120])
                    break
                if status not in (401, 403, 429):
                    break

    log.warning("All AI models failed, using fallback reply")
    return _smart_fallback(s, last_user_msg)
