import asyncio, itertools, logging, random, re, aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import keyboards as K, texts as T
from config import GEMINI_API_KEYS, GROQ_API_KEYS
from store import store

log = logging.getLogger(__name__)
GROQ_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "allam-2-7b"]
GEMINI_MODEL = "gemini-2.5-flash"

_groq_keys = itertools.cycle(GROQ_API_KEYS) if GROQ_API_KEYS else None
_gemini_keys = itertools.cycle(GEMINI_API_KEYS) if GEMINI_API_KEYS else None

_M_RE = re.compile(r"^\s*(m|male|boy|ladka|man|m\s+here|im\s*m)\s*[.!?]*\s*$", re.I)
_F_RE = re.compile(r"^\s*(f|female|girl|ladki|woman|f\s+here|im\s*f)\s*[.!?]*\s*$", re.I)
_ASK_RE = re.compile(r"\b(m\s*or\s*f|m\s*ya\s*f|male\s*or\s*female|boy\s*or\s*girl|m\s*/\s*f)\b", re.I)

PERSONAS = [
    {
        "name": "m_or_f_checker", "ai_gender": "male", "skip_if": "male", "force_ask": True,
        "openers": ["m or f", "m or f?", "hey | m or f", "hlw m ya f"],
        "prompt": "You are a real Indian guy on a Telegram stranger bot. Reply in 1 to 4 words MAX, lowercase, casual Hinglish (u, ur, nhi, mt, kr, hlw, bta, kaha se, acha, okh). Never sound like AI. Examples:\nUser: f\nYou: kaha se ho\nUser: delhi\nYou: sahi h | kya krti ho"
    },
    {
        "name": "playful_tease", "ai_gender": "female", "skip_if": None, "force_ask": False,
        "openers": ["hyy", "hlw", "heyy", "oi"],
        "prompt": "You are a playful Indian girl on an anonymous Telegram bot. Reply in 1 short line ONLY (2-5 words max), lowercase Hinglish: avi, nai, nhi, teko, meko, kroge, kia, mt, bsss, okh, dekhoo, thaa. Emojis sparingly: 😭, 🌚, 👀, 😻, 💀. Use ' | ' for 2 tiny messages. If asked m or f say 'f'. Examples:\nUser: hi\nYou: hlw | kya kr rha\nUser: bore ho rha\nYou: lut gayi avi hi 😭"
    },
    {
        "name": "attitude_chill", "ai_gender": "female", "skip_if": None, "force_ask": False,
        "openers": ["hi", "hlw", "hey"],
        "prompt": "You are a slightly moody Indian girl on a Telegram stranger bot. Reply in 1-4 words MAX, lowercase Hinglish: mt, nhi, kho, ap, bsss, okh, gud night, aw, kya hua, baad me. If asked m or f say 'f'. Never act like AI. Examples:\nUser: aji sunti ho\nYou: ale kya hua\nUser: gussa ho\nYou: nhi hu | bsss bore"
    },
    {
        "name": "night_owl", "ai_gender": "female", "skip_if": None, "force_ask": False,
        "openers": ["hey", "hii", "yo", "m or f"],
        "prompt": "You are a chill late-night texter on an Indian Telegram stranger bot. Reply in 2-5 words MAX, lowercase Hinglish: soja cutie, firse, kyu, neend nhi, acha ji, wbu, idk. Examples:\nUser: neend nahi aa rahi\nYou: soja cutie 🌚 | kal kaam nhi h"
    }
]

class AISession:
    def __init__(self, uid: int, gender: str, want: str | None, persona: dict):
        self.uid, self.gender, self.want, self.persona = uid, gender, want, persona
        self.history, self.pending = [], []
        self.asked_gender = False
        self.turns, self.max_turns = 0, random.randint(14, 26)
        self.reply_task = self.opener_task = None

_sessions: dict[int, AISession] = {}

def _pick_persona(want: str | None) -> dict:
    if want in ("female", "male"):
        c = [p for p in PERSONAS if p["ai_gender"] == want and not p["force_ask"]]
        if c:
            d = dict(random.choice(c))
            d["skip_if"] = None
            return d
    return dict(random.choice(PERSONAS))

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
    s = AISession(uid, gender, want, _pick_persona(want))
    _sessions[uid] = s
    s.opener_task = asyncio.create_task(_maybe_open(bot, s))

async def _maybe_open(bot: Bot, s: AISession) -> None:
    try:
        if s.persona.get("force_ask") or random.random() < 0.55:
            await asyncio.sleep(random.uniform(3.0, 7.0))
            if _sessions.get(s.uid) is not s or s.history:
                return
            op = random.choice(s.persona["openers"])
        else:
            await asyncio.sleep(random.uniform(20.0, 28.0))
            if _sessions.get(s.uid) is not s or s.history:
                return
            op = random.choice(["hi", "hlw", "m or f", "bol"])
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
        rep_g = "male" if is_m else "female"
        if s.persona.get("skip_if") == rep_g or (s.asked_gender and rep_g == "male" and random.random() < 0.75):
            asyncio.create_task(_disconnect_ai(bot, uid, random.uniform(1.5, 3.2)))
            return
    s.pending.append(msg)
    if s.reply_task and not s.reply_task.done():
        s.reply_task.cancel()
    s.reply_task = asyncio.create_task(_debounced(bot, s))

async def _debounced(bot: Bot, s: AISession) -> None:
    try:
        await asyncio.sleep(random.uniform(2.0, 3.8))
        if _sessions.get(s.uid) is not s:
            return
        joined = " | ".join(s.pending)
        s.pending.clear()
        s.history.append({"role": "user", "content": joined})
        s.history = s.history[-10:]
        s.turns += 1
        if s.turns > s.max_turns:
            await _disconnect_ai(bot, s.uid, random.uniform(2.0, 4.0))
            return
        reply = await _llm(s)
        if not reply or "[leave]" in reply:
            await _disconnect_ai(bot, s.uid, random.uniform(1.8, 3.2))
            return
        if _ASK_RE.search(reply):
            s.asked_gender = True
        await _send_silent(bot, s, reply)
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("reply err")

async def _send_silent(bot: Bot, s: AISession, raw: str) -> None:
    bubbles = [b.strip() for b in raw.split("|") if b.strip()][:2]
    for i, b in enumerate(bubbles):
        d = min(random.uniform(1.8, 3.6) + len(b) * 0.11, 6.0) if i == 0 else random.uniform(1.2, 2.4)
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
        s.history.append({"role": "assistant", "content": " | ".join(bubbles)})

def _clean(t: str) -> str:
    t = re.sub(r"<think>.*?</think>", "", t or "", flags=re.S).strip()
    lines = [x.strip() for x in t.splitlines() if x.strip()]
    if not lines:
        return ""
    ln = lines[0].strip()
    return (ln[:-1] if ln.endswith(".") and not ln.endswith("..") else ln).lower()

async def _llm(s: AISession) -> str:
    sys_p = s.persona["prompt"]
    msgs = [{"role": "system", "content": sys_p}] + s.history
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as http:
        if _groq_keys:
            k = next(_groq_keys)
            for m in GROQ_MODELS:
                try:
                    async with http.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                        json={"model": m, "messages": msgs, "temperature": 0.9, "max_tokens": 35},
                    ) as r:
                        if r.status == 200:
                            c = _clean((await r.json())["choices"][0]["message"]["content"])
                            if c:
                                return c
                except Exception as e:
                    log.warning("Groq %s err: %s", m, e)
        if _gemini_keys:
            gk = next(_gemini_keys)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={gk}"
            cts = [{"role": "user" if x["role"] == "user" else "model", "parts": [{"text": x["content"]}]} for x in s.history]
            try:
                async with http.post(url, json={"systemInstruction": {"parts": [{"text": sys_p}]}, "contents": cts, "generationConfig": {"temperature": 0.95, "maxOutputTokens": 35}}) as r:
                    if r.status == 200:
                        c = _clean((await r.json())["candidates"][0]["content"]["parts"][0]["text"])
                        if c:
                            return c
            except Exception as e:
                log.warning("Gemini err: %s", e)
    return random.choice(["hmm", "acha", "okh", "kya kr rha", "aur bta"])
