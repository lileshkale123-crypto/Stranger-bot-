"""All user-facing text lives here so more languages can be added later."""

# Reply-keyboard button labels (also used for matching incoming messages)
BTN_RANDOM = "🎲 Random Match"
BTN_STOP = "🛑 Stop Search"
BTN_FIND_F = "👩 Find Female (⭐)"
BTN_FIND_M = "👨 Find Male (⭐)"
BTN_PROFILE = "👤 My Profile"
BTN_PREMIUM = "💎 Get Premium"
BTN_CLOSE = "❌ Close Menu"
# Shown only while chatting
BTN_NEXT = "⏭ Next"
BTN_LEAVE = "🛑 Stop Chat"
BTN_REPORT = "🚩 Report"

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
        "not_registered": "Please send /start to set up your profile first.",
        "btn_yes_18": "✅ Yes, I'm 18+",
        "btn_no_18": "❌ No",
        "btn_male": "👨 Male",
        "btn_female": "👩 Female",
        # --- menu ---
        "menu_open": "📋 Menu",
        "menu_closed": "Menu closed. Send /menu to open it again.",
        # --- matching ---
        "already_in_chat": "You're already chatting. Use ⏭ Next or 🛑 Stop Chat first.",
        "already_searching": "🔎 You're already searching. Tap 🛑 Stop Search to cancel.",
        "searching_any": "🔎 <b>Searching the network…</b>\nTap <b>🛑 Stop Search</b> to cancel.",
        "searching_filter": "🔎 <b>Searching for a {gender}…</b>\nTap <b>🛑 Stop Search</b> to cancel.",
        "search_stopped": "🛑 Search stopped.",
        "you_left": "👋 You left the chat.\nTap <b>🎲 Random Match</b> to find someone new.",
        "nothing_to_stop": "You're not in a chat or a search right now.",
        "partner_left": "👋 <b>Your stranger left the chat.</b>\nTap <b>🎲 Random Match</b> to find someone new.",
        "match_found": "⚡ <b>Match found!</b> Say hi to your stranger.",
        "not_in_chat": "You're not in a chat. Tap <b>🎲 Random Match</b> to meet someone.",
        "no_match_filter": (
            "😕 Nobody matching your filter is online right now.\n"
            "Keep waiting, or match with anyone?"
        ),
        "btn_keep_waiting": "⏳ Keep waiting",
        "btn_match_anyone": "🎲 Match with anyone",
        "keep_waiting": "⏳ Okay, still searching…",
        "matching_anyone": "🎲 Okay, matching you with anyone…",
        "search_over": "That search already ended.",
        # --- chatting ---
        "media_premium": "🔒 Photos, voice, video and stickers are for VIP members.\nText is always free.",
        "blocked_content": "🚫 Sharing contacts, locations and polls isn't allowed.",
        "slow_down": "⏱ Slow down a little.",
        "send_failed": "⚠️ That message couldn't be delivered.",
        # --- report ---
        "report_ask": "🚩 <b>Report this stranger?</b>\nChoose a reason. The chat will end.",
        "report_sent": "✅ Thanks, your report was sent. The chat has ended.",
        "report_cancelled": "Report cancelled.",
        "chat_ended": "This chat has already ended.",
        "rp_spam": "Spam / ads",
        "rp_abuse": "Abuse / harassment",
        "rp_underage": "Underage",
        "rp_other": "Other",
        "btn_cancel": "Cancel",
        # --- profile ---
        "profile": (
            "👤 <b>Your profile</b>\n\n"
            "Gender: {gender}\n"
            "Age: {age}\n"
            "Region: {region}\n"
            "VIP: {vip}"
        ),
        "vip_on": "💎 Active until {date}",
        "vip_off": "❌ Not active",
        "btn_edit_gender": "✏️ Gender",
        "btn_edit_age": "✏️ Age",
        "btn_edit_region": "✏️ Region",
        "btn_back": "⬅️ Back",
        "edit_gender": "✏️ Pick your gender:",
        "edit_age": "✏️ Pick your age bracket:",
        "edit_region": "✏️ Pick your region:",
        # --- premium ---
        "plans_menu": (
            "💎 <b>VIP Pass</b>\n\n"
            "✅ Choose who you talk to (Find Female / Find Male)\n"
            "✅ Send photos, voice, video and stickers\n\n"
            "Pay with Telegram Stars ⭐. Buying again adds days on top of what you have left.\n\n"
            "Pick a plan:"
        ),
        "plans_upsell": (
            "🔒 <b>That's a VIP feature.</b>\n\n"
            "Want to choose who you talk to? Get a VIP Pass with Telegram Stars ⭐\n\n"
            "Pick a plan:"
        ),
        "vip_current": "💎 Your VIP is active until <b>{date}</b>.\n\n",
        "btn_get_premium": "💎 Get Premium",
        "invoice_title": "VIP Pass: {name}",
        "invoice_desc": "Unlock gender filters and media sharing for {days} days.",
        "plan_gone": "That plan is no longer available.",
        "premium_active": (
            "🎉 <b>VIP activated!</b>\n"
            "Your VIP is active until <b>{date}</b>.\n\n"
            "Enjoy the gender filters and media sharing."
        ),
        "payment_problem": (
            "⚠️ Your payment was received but the plan couldn't be applied automatically. "
            "Please contact support and mention this message."
        ),
    }
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    text = TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"][key]
    return text.format(**kwargs) if kwargs else text
