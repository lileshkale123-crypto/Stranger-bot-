from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import db
import keyboards as K
import texts as T
from config import AGE_BRACKETS, REGIONS
from util import fmt_dt, safe_edit

router = Router()

REGION_LABEL = dict(REGIONS)
GENDER_LABEL = {"male": "👨 Male", "female": "👩 Female"}


def _render(user) -> str:
    if db.is_premium(user):
        vip = T.t("vip_on", date=fmt_dt(user["premium_until"]))
    else:
        vip = T.t("vip_off")
    return T.t(
        "profile",
        gender=GENDER_LABEL.get(user["gender"], "-"),
        age=user["age_bracket"] or "-",
        region=REGION_LABEL.get(user["region"], "-"),
        vip=vip,
    )


@router.message(F.text == T.BTN_PROFILE)
@router.message(Command("profile"))
async def profile(message: Message) -> None:
    user = await db.get_user(message.from_user.id)
    if not user or not (user["gender"] and user["age_bracket"] and user["region"]):
        await message.answer(T.t("not_registered"))
        return
    await message.answer(_render(user), reply_markup=K.profile_kb())


@router.callback_query(F.data.startswith("pf:"))
async def profile_choice(cb: CallbackQuery) -> None:
    await cb.answer()
    parts = cb.data.split(":", 2)
    step = parts[1]
    value = parts[2] if len(parts) > 2 else ""
    uid = cb.from_user.id
    msg = cb.message

    # open an edit screen
    if step == "eg":
        await safe_edit(msg, T.t("edit_gender"), K.with_back(K.gender_kb("pf")))
        return
    if step == "ea":
        await safe_edit(msg, T.t("edit_age"), K.with_back(K.age_kb("pf")))
        return
    if step == "er":
        await safe_edit(msg, T.t("edit_region"), K.with_back(K.region_kb("pf")))
        return

    # save a choice (or go back) and show the profile again
    if step == "g" and value in GENDER_LABEL:
        await db.set_field(uid, "gender", value)
    elif step == "a" and value in AGE_BRACKETS:
        await db.set_field(uid, "age_bracket", value)
    elif step == "r" and value in REGION_LABEL:
        await db.set_field(uid, "region", value)
    elif step != "back":
        return

    user = await db.get_user(uid)
    if user:
        await safe_edit(msg, _render(user), K.profile_kb())
