"""Referral system: personal invite links that reward free VIP."""
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import db
import keyboards as K
import texts as T
from config import BOT_NAME, REFERRAL_REPEAT, REFERRAL_REWARD_DAYS, REFERRAL_TARGET
from util import fmt_dt

log = logging.getLogger(__name__)
router = Router()

REF_PREFIX = "ref_"


def parse_referrer(args: str | None, me: int) -> int | None:
    """'ref_12345' -> 12345 (None if malformed or self-referral)."""
    if not args or not args.startswith(REF_PREFIX):
        return None
    raw = args[len(REF_PREFIX):]
    if not raw.isdigit():
        return None
    rid = int(raw)
    return rid if rid != me else None


async def _link(bot: Bot, uid: int) -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}?start={REF_PREFIX}{uid}"


async def render(bot: Bot, uid: int) -> tuple[str, object]:
    user = await db.get_user(uid)
    total = await db.referral_count(uid)
    progress = total % REFERRAL_TARGET
    link = await _link(bot, uid)
    text = T.t(
        "invite",
        days=REFERRAL_REWARD_DAYS,
        target=REFERRAL_TARGET,
        bar=T.progress_bar(progress, REFERRAL_TARGET),
        progress=progress,
        total=total,
        rewards=user["referral_rewards"] if user else 0,
        link=link,
    )
    return text, K.invite_kb(link, BOT_NAME)


@router.message(F.text == T.BTN_INVITE)
@router.message(Command("invite"))
async def invite(message: Message, bot: Bot) -> None:
    user = await db.get_user(message.from_user.id)
    if not user or not (user["gender"] and user["age_bracket"] and user["region"]):
        await message.answer(T.t("not_registered"))
        return
    text, kb = await render(bot, message.from_user.id)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "ref:open")
async def invite_button(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    text, kb = await render(bot, cb.from_user.id)
    await cb.message.answer(text, reply_markup=kb)


async def credit_on_setup(bot: Bot, new_user_id: int) -> None:
    """Call when a user finishes onboarding. Safe to call for anyone: does nothing
    unless they were referred, and can only ever credit once."""
    try:
        res = await db.credit_referral(
            new_user_id, REFERRAL_TARGET, REFERRAL_REWARD_DAYS, REFERRAL_REPEAT
        )
    except Exception:
        log.exception("credit_referral failed for %s", new_user_id)
        return
    if not res:
        return
    referrer = res["referrer"]
    try:
        if res["rewarded_days"]:
            await bot.send_message(
                referrer,
                T.t(
                    "ref_reward",
                    count=res["count"],
                    days=res["rewarded_days"],
                    date=fmt_dt(res["until"]),
                ),
                message_effect_id=CONFETTI,
            )
        else:
            progress = res["count"] % REFERRAL_TARGET or REFERRAL_TARGET
            await bot.send_message(
                referrer,
                T.t(
                    "ref_joined",
                    bar=T.progress_bar(progress, REFERRAL_TARGET),
                    progress=progress,
                    target=REFERRAL_TARGET,
                ),
                disable_notification=True,
            )
    except TelegramBadRequest:
        # effect id rejected: resend plainly so the reward message is never lost
        if res["rewarded_days"]:
            try:
                await bot.send_message(
                    referrer,
                    T.t("ref_reward", count=res["count"], days=res["rewarded_days"], date=fmt_dt(res["until"])),
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
    except TelegramForbiddenError:
        pass  # referrer blocked the bot; the reward is still saved in the database


# Telegram's built-in 🎉 message effect (private chats only)
CONFETTI = "5046509860389126442"
