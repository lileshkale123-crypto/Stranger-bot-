from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import texts as T
from config import AGE_BRACKETS, REGIONS


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=T.BTN_RANDOM), KeyboardButton(text=T.BTN_STOP)],
            [KeyboardButton(text=T.BTN_FIND_F), KeyboardButton(text=T.BTN_FIND_M)],
            [KeyboardButton(text=T.BTN_PROFILE), KeyboardButton(text=T.BTN_PREMIUM)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def age_gate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=T.t("btn_yes_18"), callback_data="ob:18:yes"),
                InlineKeyboardButton(text=T.t("btn_no_18"), callback_data="ob:18:no"),
            ]
        ]
    )


def gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=T.t("btn_male"), callback_data="ob:g:male"),
                InlineKeyboardButton(text=T.t("btn_female"), callback_data="ob:g:female"),
            ]
        ]
    )


def age_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=b, callback_data=f"ob:a:{b}") for b in AGE_BRACKETS]
        ]
    )


def region_kb() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"ob:r:{code}")
        for code, label in REGIONS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)
