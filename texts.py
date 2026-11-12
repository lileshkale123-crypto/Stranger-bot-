"""All user-facing text lives here so more languages can be added later.

Messages use Telegram HTML: <b> <i> <code> <blockquote> <blockquote expandable> <tg-spoiler>.
"""

# Reply-keyboard button labels (also used for matching incoming messages).
# Existing labels are unchanged on purpose: users who still have the old keyboard
# on screen keep working after an update.
BTN_RANDOM = "🎲 Random Match"
BTN_STOP = "🛑 Stop Search"
BTN_FIND_F = "👩 Find Female (⭐)"
BTN_FIND_M = "👨 Find Male (⭐)"
BTN_PROFILE = "👤 My Profile"
BTN_PREMIUM = "💎 Get Premium"
BTN_INVITE = "🎁 Invite & Earn"
BTN_CLOSE = "❌ Close Menu"
# Shown only while chatting
BTN_NEXT = "⏭ Next"
BTN_LEAVE = "🛑 Stop Chat"
BTN_REPORT = "🚩 Report"

DIV = "━━━━━━━━━━━━━━━"

# ---------------------------------------------------------------- font styling
# Telegram can't change fonts, but Unicode has lookalike alphabets. Everything inside
# <b>…</b> is converted to the style chosen by the FONT_STYLE env var:
#   bold (default) · smallcaps · script · off
import os
import re

FONT_STYLE = os.getenv("FONT_STYLE", "bold").lower()

_SMALLCAPS = dict(zip(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
))


def _map_bold(ch: str) -> str:  # 𝗦𝗮𝗻𝘀 𝗕𝗼𝗹𝗱
    if "A" <= ch <= "Z":
        return chr(0x1D5D4 + ord(ch) - 65)
    if "a" <= ch <= "z":
        return chr(0x1D5EE + ord(ch) - 97)
    if "0" <= ch <= "9":
        return chr(0x1D7EC + ord(ch) - 48)
    return ch


def _map_script(ch: str) -> str:  # 𝓢𝓬𝓻𝓲𝓹𝓽
    if "A" <= ch <= "Z":
        return chr(0x1D4D0 + ord(ch) - 65)
    if "a" <= ch <= "z":
        return chr(0x1D4EA + ord(ch) - 97)
    return ch


def _map_smallcaps(ch: str) -> str:  # ꜱᴍᴀʟʟ ᴄᴀᴘꜱ
    return _SMALLCAPS.get(ch.lower(), ch)


_MAPPERS = {"bold": _map_bold, "script": _map_script, "smallcaps": _map_smallcaps}
_TOKEN = re.compile(r"(<[^>]+>|&\w+;)")  # HTML tags and entities are never touched
_BOLD = re.compile(r"<b>(.*?)</b>", re.S)


def stylize(text: str) -> str:
    """Restyle <b>…</b> segments. Safe on any HTML text; a no-op when FONT_STYLE=off."""
    mapper = _MAPPERS.get(FONT_STYLE)
    if not mapper:
        return text

    def conv(m: "re.Match") -> str:
        parts = _TOKEN.split(m.group(1))
        out = "".join(p if i % 2 else "".join(mapper(c) for c in p) for i, p in enumerate(parts))
        return out

    return _BOLD.sub(conv, text)

TEXTS = {
    "en": {
        # --- intro animation frames (edited in place) ---
        "intro_0": "🔌 <b>Connecting to the network…</b>\n\n<code>▱▱▱▱▱▱▱▱▱▱  0%</code>",
        "intro_1": "🔐 <b>Encrypting your identity…</b>\n\n<code>▰▰▰▱▱▱▱▱▱▱  30%</code>",
        "intro_2": "🛰 <b>Scanning for strangers…</b>\n\n<code>▰▰▰▰▰▰▱▱▱▱  60%</code>",
        "intro_3": "🎭 <b>Creating your anonymous alias…</b>\n\n<code>▰▰▰▰▰▰▰▰▱▱  80%</code>",
        "intro_4": "✅ <b>Connected!</b>\n\n<code>▰▰▰▰▰▰▰▰▰▰  100%</code>",
        # --- onboarding ---
        "age_gate": (
            "⚡ <b>Welcome to {bot_name}</b>\n"
            f"{DIV}\n"
            "<blockquote>🎭 Anonymous\n💬 Instant\n🌍 Strangers from everywhere</blockquote>\n"
            "Setup takes 10 seconds, no typing.\n\n"
            "🔞 <b>Are you 18 or older?</b>"
        ),
        "under_age": "🚫 Sorry, <b>{bot_name}</b> is for adults (18+) only.",
        "ask_gender": "🎭 <b>Step 1 of 3</b>\n\nLet's build your anonymous alias.\n<b>What's your gender?</b>",
        "ask_age": "🎂 <b>Step 2 of 3</b>\n\n<b>Which age bracket are you in?</b>",
        "ask_region": "🌍 <b>Step 3 of 3</b>\n\n<b>Where are you from?</b>",
        "setup_done": (
            "🎉 <b>You're all set!</b>\n"
            f"{DIV}\n"
            "🎲 Tap <b>Random Match</b> to meet a stranger\n"
            "⏭ /next to skip · 🛑 /stop to leave\n"
            "🎁 Invite friends to earn <b>free VIP</b>"
        ),
        "welcome_back": (
            "👋 <b>Welcome back to {bot_name}!</b>\n"
            f"{DIV}\n"
            "Tap <b>🎲 Random Match</b> to start chatting."
        ),
        "banned": "⛔ <b>Your account has been banned.</b>",
        "not_registered": "👋 Please send /start to set up your profile first.",
        "btn_yes_18": "✅ Yes, I'm 18+",
        "btn_no_18": "❌ No",
        "btn_male": "👨 Male",
        "btn_female": "👩 Female",
        # --- menu ---
        "menu_open": "📋 <b>Menu</b>",
        "menu_closed": "✅ Menu closed. Send /menu to open it again.",
        # --- matching ---
        "already_in_chat": "💬 You're already chatting. Use <b>⏭ Next</b> or <b>🛑 Stop Chat</b> first.",
        "already_searching": "🔎 You're already searching. Tap <b>🛑 Stop Search</b> to cancel.",
        "searching_any": "🔎 <b>Searching the network…</b>\n<i>Tap 🛑 Stop Search to cancel.</i>",
        "searching_filter": "🔎 <b>Searching for a {gender}…</b>\n<i>Tap 🛑 Stop Search to cancel.</i>",
        "search_stopped": "🛑 <b>Search stopped.</b>",
        "you_left": "👋 <b>You left the chat.</b>\nTap <b>🎲 Random Match</b> to find someone new.",
        "nothing_to_stop": "ℹ️ You're not in a chat or a search right now.",
        "partner_left": "👋 <b>Your stranger left the chat.</b>\nTap <b>🎲 Random Match</b> to find someone new.",
        "match_found": (
            "⚡ <b>Match found!</b>\n"
            f"{DIV}\n"
            "💬 Say hi to your stranger.\n"
            "<i>⏭ Next to skip · 🚩 Report if something's wrong</i>"
        ),
        "not_in_chat": "💤 You're not in a chat. Tap <b>🎲 Random Match</b> to meet someone.",
        "no_match_filter": (
            "😕 <b>Nobody matching your filter is online right now.</b>\n"
            "Keep waiting, or match with anyone?"
        ),
        "btn_keep_waiting": "⏳ Keep waiting",
        "btn_match_anyone": "🎲 Match with anyone",
        "keep_waiting": "⏳ Okay, still searching…",
        "matching_anyone": "🎲 Okay, matching you with anyone…",
        "search_over": "ℹ️ That search already ended.",
        "bot_restarting": (
            "🔧 <b>We just updated the bot.</b>\n"
            "Your chat was interrupted. Tap <b>🎲 Random Match</b> to continue, sorry about that!"
        ),
        # --- chatting ---
        "media_premium": (
            "🔒 <b>Media is for VIP members.</b>\n"
            "Photos, voice, video and stickers need VIP. Text is always free."
        ),
        "blocked_content": "🚫 Sharing contacts, locations and polls isn't allowed.",
        "slow_down": "⏱ Slow down a little.",
        "send_failed": "⚠️ That message couldn't be delivered.",
        # --- report ---
        "report_ask": "🚩 <b>Report this stranger?</b>\nChoose a reason. The chat will end.",
        "report_sent": "✅ <b>Thanks, your report was sent.</b> The chat has ended.",
        "report_cancelled": "↩️ Report cancelled.",
        "chat_ended": "ℹ️ This chat has already ended.",
        "rp_spam": "📢 Spam / ads",
        "rp_abuse": "🤬 Abuse / harassment",
        "rp_underage": "🔞 Underage",
        "rp_other": "❓ Other",
        "btn_cancel": "✖️ Cancel",
        # --- profile ---
        "profile": (
            "👤 <b>Your profile</b>\n"
            f"{DIV}\n"
            "🎭 Gender  ·  <b>{gender}</b>\n"
            "🎂 Age  ·  <b>{age}</b>\n"
            "🌍 Region  ·  <b>{region}</b>\n"
            "💎 VIP  ·  {vip}\n"
            "🎁 Friends invited  ·  <b>{invited}</b>"
        ),
        "vip_on": "<b>Active</b> until {date}",
        "vip_off": "<i>Not active</i>",
        "btn_edit_gender": "✏️ Gender",
        "btn_edit_age": "✏️ Age",
        "btn_edit_region": "✏️ Region",
        "btn_back": "⬅️ Back",
        "edit_gender": "✏️ <b>Pick your gender:</b>",
        "edit_age": "✏️ <b>Pick your age bracket:</b>",
        "edit_region": "✏️ <b>Pick your region:</b>",
        # --- premium ---
        "plans_menu": (
            "💎 <b>VIP Pass</b>\n"
            f"{DIV}\n"
            "<blockquote>✅ Choose who you talk to (Find Female / Find Male)\n"
            "✅ Send photos, voice, video and stickers</blockquote>\n"
            "Pay with Telegram Stars ⭐. Buying again adds days on top of what you have left.\n\n"
            "🎁 <i>Or get VIP free: invite friends with /invite</i>\n\n"
            "<b>Pick a plan:</b>"
        ),
        "plans_upsell": (
            "🔒 <b>That's a VIP feature.</b>\n"
            f"{DIV}\n"
            "Want to choose who you talk to? Get a VIP Pass with Telegram Stars ⭐\n\n"
            "🎁 <i>Or get VIP free: invite friends with /invite</i>\n\n"
            "<b>Pick a plan:</b>"
        ),
        "vip_current": "💎 Your VIP is active until <b>{date}</b>.\n\n",
        "btn_get_premium": "💎 Get Premium",
        "invoice_title": "VIP Pass: {name}",
        "invoice_desc": "Unlock gender filters and media sharing for {days} days.",
        "plan_gone": "⚠️ That plan is no longer available.",
        "premium_active": (
            "🎉 <b>VIP activated!</b>\n"
            f"{DIV}\n"
            "💎 Active until <b>{date}</b>\n\n"
            "Enjoy the gender filters and media sharing."
        ),
        "payment_problem": (
            "⚠️ Your payment was received but the plan couldn't be applied automatically. "
            "Please contact support and mention this message."
        ),
        # --- referrals ---
        "invite": (
            "🎁 <b>Invite &amp; Earn VIP</b>\n"
            f"{DIV}\n"
            "Get <b>{days} days of free VIP</b> for every <b>{target} friends</b> who join with your link.\n\n"
            "<blockquote>📈 Progress to next reward\n"
            "<code>{bar}</code>  <b>{progress}/{target}</b></blockquote>\n"
            "👥 Total invited: <b>{total}</b>\n"
            "🏆 Rewards earned: <b>{rewards}</b>\n\n"
            "🔗 <b>Your personal link</b> (tap to copy):\n"
            "<code>{link}</code>\n\n"
            "<i>A friend counts once they finish setup.</i>"
        ),
        "btn_share": "📤 Share my link",
        "share_text": "💬 Chat with random strangers anonymously on {bot_name}! Join here:",
        "ref_joined": (
            "🙌 <b>A friend joined with your link!</b>\n"
            "<code>{bar}</code>  <b>{progress}/{target}</b>"
        ),
        "ref_reward": (
            "🏆 <b>Reward unlocked!</b>\n"
            f"{DIV}\n"
            "You invited <b>{count}</b> friends and earned <b>{days} days of VIP</b> 🎉\n"
            "💎 Active until <b>{date}</b>"
        ),
        "ref_welcome": "🤝 <b>You were invited by a friend.</b> Let's get you set up!",
        # --- admin ---
        "admin_stats": (
            "📊 <b>Bot stats</b>\n"
            f"{DIV}\n"
            "👥 Users: <b>{users}</b>\n"
            "🆕 New (24h): <b>{new_24h}</b>\n"
            "💎 VIP now: <b>{vip}</b>\n"
            "🎁 Joined via referral: <b>{referred}</b>\n"
            "🟢 Online (chat + queue): <b>{online}</b>\n"
            "💬 Active chats: <b>{chats}</b>"
        ),
    }
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    text = TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"][key]
    return stylize(text.format(**kwargs) if kwargs else text)


def progress_bar(done: int, total: int, width: int = 10) -> str:
    filled = min(width, round(width * done / total)) if total else 0
    return "▰" * filled + "▱" * (width - filled)
