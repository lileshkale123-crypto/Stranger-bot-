import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

import db
import keyboards as K
import texts as T
from config import PLAN_BY_ID
from util import fmt_dt

log = logging.getLogger(__name__)
router = Router()


async def show_plans(message: Message, upsell: bool = False, user=None) -> None:
    text = T.t("plans_upsell" if upsell else "plans_menu")
    if user is not None and db.is_premium(user):
        text = T.t("vip_current", date=fmt_dt(user["premium_until"])) + text
    await message.answer(text, reply_markup=K.plans_kb())


@router.message(F.text == T.BTN_PREMIUM)
@router.message(Command("premium"))
async def premium_menu(message: Message) -> None:
    user = await db.get_user(message.from_user.id)
    await show_plans(message, user=user)


@router.callback_query(F.data == "pm:plans")
async def plans_button(cb: CallbackQuery) -> None:
    await cb.answer()
    user = await db.get_user(cb.from_user.id)
    await show_plans(cb.message, user=user)


@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery) -> None:
    await cb.answer()
    plan = PLAN_BY_ID.get(cb.data.split(":", 1)[1])
    if not plan:
        await cb.message.answer(T.t("plan_gone"))
        return
    # Telegram Stars: currency XTR, no provider token
    await cb.message.answer_invoice(
        title=T.t("invoice_title", name=plan["title"]),
        description=T.t("invoice_desc", days=plan["days"]),
        payload=f"plan:{plan['id']}",
        currency="XTR",
        prices=[LabeledPrice(label=plan["title"], amount=plan["stars"])],
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    plan_id = query.invoice_payload.removeprefix("plan:")
    user = await db.get_user(query.from_user.id)
    ok = plan_id in PLAN_BY_ID and query.currency == "XTR" and not (user and user["banned"])
    await query.answer(ok=ok, error_message=None if ok else T.t("plan_gone"))


@router.message(F.successful_payment)
async def payment_done(message: Message) -> None:
    sp = message.successful_payment
    plan = PLAN_BY_ID.get(sp.invoice_payload.removeprefix("plan:"))
    if not plan:
        log.critical("Paid for unknown plan: %s (charge %s)", sp.invoice_payload, sp.telegram_payment_charge_id)
        await message.answer(T.t("payment_problem"))
        return
    until = await db.apply_payment(
        message.from_user.id,
        plan["id"],
        plan["days"],
        sp.total_amount,
        sp.telegram_payment_charge_id,
    )
    if until is None:
        return  # duplicate delivery, already applied
    await message.answer(T.t("premium_active", date=fmt_dt(until)), reply_markup=K.main_menu())
