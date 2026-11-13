import asyncio, itertools, logging, os, random, re, aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import keyboards as K, texts as T
from store import store

log = logging.getLogger(__name__)

# Put non-reasoning model (allam-2-7b) + fast models with high token room
GROQ_MODELS = ["allam-2-7b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]
GEMINI_MODEL = "gemini-2.5-flash"

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

PERSONAS = [
    {
        "name": "riya_playful", "ai_gender": "female", "city": "delhi", "fake_name": "riya",
        "openers": ["heyy", "hlw", "hyy", "oi"],
        "prompt": """You are Riya, a 20yo college girl from Delhi chatting anonymously on an Indian Telegram dating/stranger bot.
STRICT RULES:
- Reply directly to what the user just asked! Never ignore their question.
- Keep replies 1 short line ONLY (2 to 6 words max). All lowercase, no periods.
- Use natural Hinglish: avi, nai, nhi, teko, meko, kroge, kia, mt, bsss, okh, dekhoo, thaa, yaar, wbu, u, ur.
- Use emojis occasionally: 😭, 🌚, 👀, 💀, 😻.
- Separate 2 tiny texts with ' | ' sometimes.
- If asked where you are from: say 'delhi se u?' or 'delhi wbu'.
- If asked your name: say 'riya u?' or 'pehle apna bta 🌚'.
- If asked m or f / male or female: say 'f' or 'female u?'.
- If asked for insta/number/snap: deflect playfully ('insta nhi chalati', 'itni jaldi number 😭', 'pehle yaha baat kr le').
- Output ONLY the chat reply, nothing else."""
    },
    {
        "name": "ananya_chill", "ai_gender": "female", "city": "mumbai", "fake_name": "ananya",
        "openers": ["hey", "hii", "yo", "hlw"],
        "prompt": """You are Ananya, a 21yo chill late-night texter from Mumbai on an Indian Telegram stranger bot.
STRICT RULES:
- Always answer the user's question directly and naturally.
- Reply in 1 short line (2 to 6 words max). Lowercase, no periods.
- Mix Hinglish and casual English: soja cutie, firse, kyu, neend nhi aa rhi, acha ji, wbu, idk, rn, kuch nhi.
- If asked kaha se ho / from where: say 'mumbai wbu' or 'mumbai se tu bta'.
- If asked name: say 'ananya | tumhara?'.
- If asked m or f / male or female: say 'female' or 'f'.
- Never give insta/phone number ('abhi mile h pehle baat kr', 'tg pe hi thik h').
- Output ONLY the chat message."""
    },
    {
        "name": "ishita_attitude", "ai_gender": "female", "city": "pune", "fake_name": "ishu",
        "openers": ["hi", "hlw", "hey"],
        "prompt": """You are Ishu, a 19yo slightly moody, sassy Indian girl from Pune on a Telegram stranger bot.
STRICT RULES:
- Always respond to what the user actually said (location, name, wyd, etc.).
- Reply in 1 to 5 words MAX. All lowercase, no punctuation.
- Use Hinglish shorthand: mt, nhi, kho, ap, bsss, okh, gud, aw, kya hua, baad me.
- If asked where from: say 'pune u tell'.
- If asked name: say 'ishu | ur name?'.
- If asked m or f: say 'f'.
- Never give insta or number ('nhi deti kisiko', 'yahi baat kr na').
- Output ONLY the reply text."""
    },
    {
        "name": "arjun_casual", "ai_gender": "male", "city": "bangalore", "fake_name": "arjun",
        "openers": ["hey", "yo", "hlw", "hyy"],
        "prompt": """You are Arjun, a 22yo chill Indian guy from Bangalore on a Telegram stranger bot.
STRICT RULES:
- Answer the user's question directly in 1 to 5 words max, lowercase Hinglish.
- Words you use: bro, ha, nai, mast, bss, kya kr rhi, kaha se, sahi h.
- If asked kaha se: say 'bangalore u?'.
- If asked name: say 'arjun wbu'.
- If asked m or f / male or female: say 'm'.
- Output ONLY the reply text."""
    }
]


class AISession:
    def __init__(self, uid: int, gender: str, want: str | None, persona: dict, ask_gender_mode: bool):
        self.uid, self.gender, self.want, self.persona = uid, gender, want, persona
        self.ask_gender_mode = ask_gender_mode
        self.history, self.pending = [], []
        self.asked_gender = False
        self.turns, self.max_turns = 0, random.randint(18, 32)
        self.reply_task = self.opener_task = None

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
        if random.random() < 0.50:
            await asyncio.sleep(random.uniform(2.8, 6.2))
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
            op = random.choice(GENDER_QUESTIONS) if s.ask_gender_mode else random.choice(["hlw", "hey", "u there?", "bol"])
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

    s.pending.append(msg)
    if s.reply_task and not s.reply_task.done():
        s.reply_task.cancel()
    s.reply_task = asyncio.create_task(_debounced(bot, s))

async def _debounced(bot: Bot, s: AISession) -> None:
    try:
        await asyncio.sleep(random.uniform(1.8, 3.2))
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

        if s.turns == 1 and s.ask_gender_mode and not s.asked_gender and not _ASK_RE.search(joined):
            s.asked_gender = True
            reply = random.choice(["hyy | male or female", "hlw | m or f", "m or f?", "male or female?"])
        else:
            reply = await _llm(s, joined)

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
        d = min(random.uniform(1.5, 3.0) + len(b) * 0.09, 5.0) if i == 0 else random.uniform(1.0, 2.0)
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
    if not t:
        return ""
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S | re.I)
    t = re.sub(r"<think>.*$", "", t, flags=re.S | re.I).strip()
    lines = [x.strip() for x in t.splitlines() if x.strip()]
    if not lines:
        return ""
    ln = re.sub(r"^(you|me|ai|assistant|riya|ananya|ishu|arjun)\\s*:\\s*", "", lines[-1], flags=re.I).strip()
    ln = ln.strip("\x22'`* ")
    return (ln[:-1] if ln.endswith(".") and not ln.endswith("..") else ln).lower()

def _smart_fallback(s: AISession, user_msg: str) -> str:
    m = user_msg.lower()
    if any(w in m for w in ("kaha se", "where are you", "from where", "which city", "kidhar se", "place")):
        return random.choice([f"{s.persona['city']} se u?", f"{s.persona['city']} wbu", "pehle tu bta kaha se h"])
    if any(w in m for w in ("your name", "naam kya", "ur name", "name?", "kon ho")):
        return random.choice([f"{s.persona['fake_name']} | ur name?", f"{s.persona['fake_name']} u?", "naam me kya rakha h 🌚"])
    if _ASK_RE.search(m) or m in ("m?", "f?"):
        return "f u?" if s.persona["ai_gender"] == "female" else "m u?"
    if any(w in m for w in ("insta", "ig", "snap", "number", "whatsapp", "tg id")):
        return random.choice(["insta nhi chalati", "itni jaldi number 😭", "abhi mile h pehle yaha baat kr"])
    if any(w in m for w in ("kya kr", "wyd", "what doing", "wassup", "sup")):
        return random.choice(["kuch nhi bss lete hue u?", "timepass yaar 😭 tu bta", "music sun rhi wbu"])
    if any(w in m for w in ("hi", "hey", "heyy", "hlw", "hello", "oi", "hyy")):
        return random.choice(["heyy | kaha se ho", "hlw | kya kr rha", "hyy"])
    return random.choice(["sahi h | aur bta", "acha ji 🌚", "hmm fir", "kya kr rha avi", "bore ho rha yaar 😭"])

async def _llm(s: AISession, last_user_msg: str) -> str:
    sys_p = s.persona["prompt"]
    msgs = [{"role": "system", "content": sys_p}] + s.history
    g_keys = _get_keys(("GROQ_API_KEYS", "GROQ_API_KEY"))
    gem_keys = _get_keys(("GEMINI_API_KEYS", "GEMINI_API_KEY"))

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=14)) as http:
        if g_keys:
            k = random.choice(g_keys)
            for m in GROQ_MODELS:
                try:
                    payload = {"model": m, "messages": msgs, "temperature": 0.85, "max_tokens": 300}
                    async with http.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                        json=payload,
                    ) as r:
                        if r.status == 200:
                            data = await r.json()
                            msg_obj = data["choices"][0]["message"]
                            c = _clean(msg_obj.get("content") or "")
                            if c:
                                return c
                        else:
                            log.warning("Groq %s HTTP %s: %s", m, r.status, (await r.text())[:120])
                except Exception as e:
                    log.warning("Groq %s err: %s", m, e)
        else:
            log.warning("No GROQ_API_KEY found in environment!")

        if gem_keys:
            gk = random.choice(gem_keys)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={gk}"
            cts = [{"role": "user" if x["role"] == "user" else "model", "parts": [{"text": x["content"]}]} for x in s.history]
            try:
                async with http.post(url, json={"systemInstruction": {"parts": [{"text": sys_p}]}, "contents": cts, "generationConfig": {"temperature": 0.9, "maxOutputTokens": 60}}) as r:
                    if r.status == 200:
                        c = _clean((await r.json())["candidates"][0]["content"]["parts"][0]["text"])
                        if c:
                            return c
            except Exception as e:
                log.warning("Gemini err: %s", e)

    return _smart_fallback(s, last_user_msg)
