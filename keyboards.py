from urllib.parse import quote

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import texts as T
from config import AGE_BRACKETS, PLANS, REGIONS


# ---------- reply keyboards ----------

def main_menu() -> ReplyKeyboardMarkup:
    # is_persistent=False lets users collapse it with the keyboard icon;
    # the Close Menu button removes it completely (/menu brings it back).
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=T.BTN_RANDOM), KeyboardButton(text=T.BTN_STOP)],
            [KeyboardButton(text=T.BTN_FIND_F), KeyboardButton(text=T.BTN_FIND_M)],
            [KeyboardButton(text=T.BTN_PROFILE), KeyboardButton(text=T.BTN_PREMIUM)],
            [KeyboardButton(text=T.BTN_INVITE), KeyboardButton(text=T.BTN_CLOSE)],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


def chat_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=T.BTN_NEXT), KeyboardButton(text=T.BTN_LEAVE)],
            [KeyboardButton(text=T.BTN_REPORT)],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


# ---------- onboarding / profile editing (prefix "ob" or "pf") ----------

def age_gate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=T.t("btn_yes_18"), callback_data="ob:18:yes"),
                InlineKeyboardButton(text=T.t("btn_no_18"), callback_data="ob:18:no"),
            ]
        ]
    )


def gender_kb(prefix: str = "ob") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=T.t("btn_male"), callback_data=f"{prefix}:g:male"),
                InlineKeyboardButton(text=T.t("btn_female"), callback_data=f"{prefix}:g:female"),
            ]
        ]
    )


def age_kb(prefix: str = "ob") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=b, callback_data=f"{prefix}:a:{b}") for b in AGE_BRACKETS]
        ]
    )


def region_kb(prefix: str = "ob") -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"{prefix}:r:{code}")
        for code, label in REGIONS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def with_back(kb: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    back = [InlineKeyboardButton(text=T.t("btn_back"), callback_data="pf:back")]
    return InlineKeyboardMarkup(inline_keyboard=[*kb.inline_keyboard, back])


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=T.t("btn_edit_gender"), callback_data="pf:eg"),
                InlineKeyboardButton(text=T.t("btn_edit_age"), callback_data="pf:ea"),
                InlineKeyboardButton(text=T.t("btn_edit_region"), callback_data="pf:er"),
            ]
        ]
    )


# ---------- matching ----------

def fallback_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=T.t("btn_keep_waiting"), callback_data="mm:wait"),
                InlineKeyboardButton(text=T.t("btn_match_anyone"), callback_data="mm:any"),
            ]
        ]
    )


def report_kb(partner_id: int) -> InlineKeyboardMarkup:
    reasons = ["spam", "abuse", "underage", "other"]
    rows = [
        [InlineKeyboardButton(text=T.t(f"rp_{r}"), callback_data=f"rp:{r}:{partner_id}")]
        for r in reasons
    ]
    rows.append([InlineKeyboardButton(text=T.t("btn_cancel"), callback_data="rp:cancel:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- premium ----------

def plans_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"⭐ {p['stars']} — {p['title']}", callback_data=f"buy:{p['id']}"
            )
        ]
        for p in PLANS
    ]
    rows.append([InlineKeyboardButton(text=T.BTN_INVITE, callback_data="ref:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invite_kb(link: str, bot_name: str) -> InlineKeyboardMarkup:
    share = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(T.t('share_text', bot_name=bot_name))}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=T.t("btn_share"), url=share)],
            [InlineKeyboardButton(text=T.t("btn_get_premium"), callback_data="pm:plans")],
        ]
    )


def premium_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=T.t("btn_get_premium"), callback_data="pm:plans")]
        ]
    )
