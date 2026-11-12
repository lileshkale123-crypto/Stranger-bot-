import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import db
import keyboards as K
import referral
import texts as T
from config import AGE_BRACKETS, BOT_NAME, INTRO_FRAME_DELAY, REGIONS

log = logging.getLogger(__name__)
router = Router()

INTRO_FRAMES = ("intro_0", "intro_1", "intro_2", "intro_3", "intro_4")
VALID_REGIONS = {code for code, _ in REGIONS}


def _registered(user) -> bool:
    return bool(user["gender"] and user["age_bracket"] and user["region"])


async def _safe_edit(msg: Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await msg.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        # "message is not modified" or message deleted: never crash the flow
        log.debug("edit skipped: %s", e)


async def play_intro(message: Message) -> Message:
    """Self-editing 'connecting' animation. Returns the message so it can be reused."""
    msg = await message.answer(T.t(INTRO_FRAMES[0]))
    for key in INTRO_FRAMES[1:]:
        await asyncio.sleep(INTRO_FRAME_DELAY)
        await _safe_edit(msg, T.t(key))
    await asyncio.sleep(INTRO_FRAME_DELAY)
    return msg


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    uid = message.from_user.id
    referrer = referral.parse_referrer(command.args, uid)
    if referrer is not None:
        ref_user = await db.get_user(referrer)
        if not ref_user or ref_user["banned"]:
            referrer = None
    # referrer is only stored if this is a brand-new user
    user = await db.get_or_create_user(uid, referrer)

    if user["banned"]:
        await message.answer(T.t("banned"))
        return

    if _registered(user):
        await message.answer(T.t("welcome_back", bot_name=BOT_NAME), reply_markup=K.main_menu())
        return

    if user["referred_by"] and user["is_new"]:
        await message.answer(T.t("ref_welcome"))
    msg = await play_intro(message)
    await _safe_edit(msg, T.t("age_gate", bot_name=BOT_NAME), K.age_gate_kb())


@router.callback_query(F.data.startswith("ob:"))
async def onboarding_step(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()  # stop the loading spinner immediately
    _, step, value = cb.data.split(":", 2)
    uid = cb.from_user.id
    msg = cb.message

    if step == "18":
        if value == "yes":
            await _safe_edit(msg, T.t("ask_gender"), K.gender_kb())
        else:
            await _safe_edit(msg, T.t("under_age", bot_name=BOT_NAME))

    elif step == "g" and value in ("male", "female"):
        await db.set_field(uid, "gender", value)
        await _safe_edit(msg, T.t("ask_age"), K.age_kb())

    elif step == "a" and value in AGE_BRACKETS:
        await db.set_field(uid, "age_bracket", value)
        await _safe_edit(msg, T.t("ask_region"), K.region_kb())

    elif step == "r" and value in VALID_REGIONS:
        await db.set_field(uid, "region", value)
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        # The persistent reply keyboard can only be attached to a new message
        await msg.answer(T.t("setup_done"), reply_markup=K.main_menu())
        # Reward the person who invited them (no-op for everyone else, and only once)
        user = await db.get_user(uid)
        if user and _registered(user):
            await referral.credit_on_setup(bot, uid)
