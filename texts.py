"""All user-facing text lives here so more languages can be added later."""

# Reply-keyboard button labels (also used for matching incoming messages)
BTN_RANDOM = "🎲 Random Match"
BTN_STOP = "🛑 Stop Search"
BTN_FIND_F = "👩 Find Female (⭐)"
BTN_FIND_M = "👨 Find Male (⭐)"
BTN_PROFILE = "👤 My Profile"
BTN_PREMIUM = "💎 Get Premium"

TEXTS = {
    "en": {
        # --- intro animation frames (edited in place) ---
        "intro_0": "🔌 <b>Connecting to the network…</b>\n\n▱▱▱▱▱▱▱▱▱▱  0%",
        "intro_1": "🔐 <b>Encrypting your identity…</b>\n\n▰▰▰▱▱▱▱▱▱▱  30%",
        "intro_2": "🛰 <b>Scanning for strangers…</b>\n\n▰▰▰▰▰▰▱▱▱▱  60%",
        "intro_3": "🎭 <b>Creating your anonymous alias…</b>\n\n▰▰▰▰▰▰▰▰▱▱  80%",
        "intro_4": "✅ <b>Connected!</b>\n\n▰▰▰▰▰▰▰▰▰▰  100%",
        # --- onboarding ---
        "age_gate": (
            "⚡ <b>Welcome to {bot_name}</b>\n\n"
            "Chat with random strangers. Fully anonymous, no typing needed to set up.\n\n"
            "First things first: <b>are you 18 or older?</b>"
        ),
        "under_age": "🚫 Sorry, {bot_name} is for adults (18+) only.",
        "ask_gender": "🎭 <b>Let's build your anonymous alias.</b>\n\nWhat's your gender?",
        "ask_age": "🎂 <b>Nice.</b> Which age bracket are you in?",
        "ask_region": "🌍 <b>Last step.</b> Where are you from?",
        "setup_done": (
            "🎉 <b>You're all set!</b>\n\n"
            "Tap <b>🎲 Random Match</b> to meet a stranger.\n"
            "Use /next to skip and /stop to leave a chat."
        ),
        "welcome_back": "👋 <b>Welcome back to {bot_name}!</b>\nTap <b>🎲 Random Match</b> to start.",
        "banned": "⛔ Your account has been banned.",
        "btn_yes_18": "✅ Yes, I'm 18+",
        "btn_no_18": "❌ No",
        "btn_male": "👨 Male",
        "btn_female": "👩 Female",
    }
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    text = TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"][key]
    return text.format(**kwargs) if kwargs else text
