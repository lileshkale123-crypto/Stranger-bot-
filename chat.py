import asyncio, logging, random
from collections import OrderedDict
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, ReplyParameters

import ai_partner, db, keyboards as K, premium, texts as T
from config import AI_MATCH_DELAY_MAX, AI_MATCH_DELAY_MIN, FILTER_FALLBACK_SECONDS, RATE_LIMIT_MSGS, RATE_LIMIT_WINDOW
from store import store
from util import safe_edit

log = logging.getLogger(__name__)
router = Router()
_fallbacks: dict[int, asyncio.Task] = {}
_ai_fallbacks: dict[int, asyncio.Task] = {}
_reply_map: "OrderedDict[tuple[int, int], int]" = OrderedDict()   # (chat, msg) -> same message in partner's chat


def _remember(a_chat: int, a_msg: int, b_chat: int, b_msg: int) -> None:
    _reply_map[(a_chat, a_msg)] = b_msg
    _reply_map[(b_chat, b_msg)] = a_msg
    while len(_reply_map) > 40000:
        _reply_map.popitem(last=False)

def _registered(user) -> bool:
    return bool(user and user["gender"] and user["age_bracket"] and user["region"])

async def _ready_user(message: Message):
    user = await db.get_user(message.from_user.id)
    if not _registered(user):
        await message.answer(T.t("not_registered"))
        return None
    if user["banned"]:
        await message.answer(T.t("banned"))
        return None
    return user

def _cancel_fallback(uid: int) -> None:
    for d in (_fallbacks, _ai_fallbacks):
        t = d.pop(uid, None)
        if t and not t.done():
            t.cancel()

async def _fallback(bot: Bot, uid: int) -> None:
    try:
        await asyncio.sleep(FILTER_FALLBACK_SECONDS)
        if store.in_queue(uid):
            await bot.send_message(uid, T.t("no_match_filter"), reply_markup=K.fallback_kb())
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("fallback failed for %s", uid)
    finally:
        _fallbacks.pop(uid, None)

async def _ai_fallback(bot: Bot, uid: int, gender: str, want: str | None) -> None:
    try:
        await asyncio.sleep(random.uniform(AI_MATCH_DELAY_MIN, AI_MATCH_DELAY_MAX))
        if not store.in_queue(uid):
            return
        if store.pair_ai(uid) is None:
            return
        ft = _fallbacks.pop(uid, None)
        if ft and not ft.done():
            ft.cancel()
        try:
            await bot.send_message(uid, T.t("match_found"), reply_markup=K.chat_menu())
        except (TelegramForbiddenError, TelegramBadRequest):
            store.end_chat(uid)
            return
        await ai_partner.start_session(bot, uid, gender, want)
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("AI fallback failed for %s", uid)
    finally:
        _ai_fallbacks.pop(uid, None)

async def _announce(bot: Bot, a: int, b: int) -> None:
    _cancel_fallback(a)
    _cancel_fallback(b)
    for uid, other in ((a, b), (b, a)):
        try:
            await bot.send_message(uid, T.t("match_found"), reply_markup=K.chat_menu())
        except (TelegramForbiddenError, TelegramBadRequest):
            store.end_chat(uid)
            try:
                await bot.send_message(other, T.t("partner_left"), reply_markup=K.main_menu())
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
            return

async def _begin(bot: Bot, user, want: str | None) -> None:
    uid = user["id"]
    partner = store.enqueue(uid, user["gender"], want)
    if partner is not None:
        await _announce(bot, uid, partner)
        return
    text = T.t("searching_filter", gender=want) if want else T.t("searching_any")
    await bot.send_message(uid, text, reply_markup=K.main_menu())
    _cancel_fallback(uid)
    if want:
        _fallbacks[uid] = asyncio.create_task(_fallback(bot, uid))
    _ai_fallbacks[uid] = asyncio.create_task(_ai_fallback(bot, uid, user["gender"], want))

async def _search(message: Message, bot: Bot, want: str | None) -> None:
    user = await _ready_user(message)
    if not user:
        return
    uid = user["id"]
    if store.partner_of(uid) is not None:
        await message.answer(T.t("already_in_chat"))
        return
    if store.in_queue(uid):
        await message.answer(T.t("already_searching"))
        return
    if want and not db.is_premium(user):
        await premium.show_plans(message, upsell=True)
        return
    await _begin(bot, user, want)

async def _end_current(bot: Bot, uid: int) -> bool:
    partner = store.end_chat(uid)
    if partner is None:
        return False
    if store.is_ai(partner):
        ai_partner.cleanup_session(uid)
        return True
    try:
        await bot.send_message(partner, T.t("partner_left"), reply_markup=K.main_menu())
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    return True

@router.message(Command("menu"))
async def menu(message: Message) -> None:
    in_chat = store.partner_of(message.from_user.id) is not None
    await message.answer(T.t("menu_open"), reply_markup=K.chat_menu() if in_chat else K.main_menu())

@router.message(F.text == T.BTN_CLOSE)
async def close_menu(message: Message) -> None:
    await message.answer(T.t("menu_closed"), reply_markup=ReplyKeyboardRemove())

@router.message(F.text == T.BTN_RANDOM)
@router.message(Command("search"))
async def random_match(message: Message, bot: Bot) -> None:
    await _search(message, bot, None)

@router.message(F.text == T.BTN_FIND_F)
async def find_female(message: Message, bot: Bot) -> None:
    await _search(message, bot, "female")

@router.message(F.text == T.BTN_FIND_M)
async def find_male(message: Message, bot: Bot) -> None:
    await _search(message, bot, "male")

@router.message(F.text == T.BTN_STOP)
@router.message(F.text == T.BTN_LEAVE)
@router.message(Command("stop"))
async def stop(message: Message, bot: Bot) -> None:
    uid = message.from_user.id
    if store.dequeue(uid):
        _cancel_fallback(uid)
        await message.answer(T.t("search_stopped"), reply_markup=K.main_menu())
    elif await _end_current(bot, uid):
        await message.answer(T.t("you_left"), reply_markup=K.main_menu())
    else:
        await message.answer(T.t("nothing_to_stop"), reply_markup=K.main_menu())

@router.message(F.text == T.BTN_NEXT)
@router.message(Command("next"))
async def next_stranger(message: Message, bot: Bot) -> None:
    user = await _ready_user(message)
    if not user:
        return
    uid = user["id"]
    await _end_current(bot, uid)
    if store.dequeue(uid):
        _cancel_fallback(uid)
    await _begin(bot, user, None)

@router.callback_query(F.data.startswith("mm:"))
async def fallback_choice(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    uid = cb.from_user.id
    if cb.data == "mm:wait":
        await safe_edit(cb.message, T.t("keep_waiting"))
        return
    if not store.in_queue(uid):
        await safe_edit(cb.message, T.t("search_over"))
        return
    store.dequeue(uid)
    _cancel_fallback(uid)
    user = await db.get_user(uid)
    await safe_edit(cb.message, T.t("matching_anyone"))
    await _begin(bot, user, None)

@router.message(F.text == T.BTN_REPORT)
async def report(message: Message) -> None:
    partner = store.partner_of(message.from_user.id)
    if partner is None:
        await message.answer(T.t("not_in_chat"), reply_markup=K.main_menu())
        return
    await message.answer(T.t("report_ask"), reply_markup=K.report_kb(partner))

@router.callback_query(F.data.startswith("rp:"))
async def report_choice(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    _, reason, partner_raw = cb.data.split(":", 2)
    uid = cb.from_user.id
    if reason == "cancel":
        await safe_edit(cb.message, T.t("report_cancelled"))
        return
    partner = int(partner_raw)
    if store.partner_of(uid) != partner:
        await safe_edit(cb.message, T.t("chat_ended"))
        return
    if not store.is_ai(partner):
        await db.add_report(uid, partner, reason)
    await _end_current(bot, uid)
    await safe_edit(cb.message, T.t("report_sent"))
    await cb.message.answer(T.t("menu_open"), reply_markup=K.main_menu())

@router.message(F.chat.type == "private")
async def relay(message: Message, bot: Bot) -> None:
    uid = message.from_user.id
    partner = store.partner_of(uid)
    if message.text and message.text.startswith("/"):
        return
    if partner is None:
        await message.answer(T.t("not_in_chat"), reply_markup=K.main_menu())
        return
    if message.contact or message.location or message.venue or message.poll:
        await message.answer(T.t("blocked_content"))
        return
    if message.text is None:
        user = await db.get_user(uid)
        if not user or not db.is_premium(user):
            await message.answer(T.t("media_premium"), reply_markup=K.premium_prompt_kb())
            return
    if not store.allow_message(uid, RATE_LIMIT_MSGS, RATE_LIMIT_WINDOW):
        await message.answer(T.t("slow_down"))
        return
    if store.is_ai(partner):
        rq = message.reply_to_message
        quote = (rq.text or rq.caption) if rq else None
        await ai_partner.handle_user_message(bot, uid, message.text or "nice", quote, message.message_id)
        return
    try:
        rt = message.reply_to_message
        target = _reply_map.get((uid, rt.message_id)) if rt else None
        extra = {"reply_parameters": ReplyParameters(message_id=target, allow_sending_without_reply=True)} if target else {}
        sent = await bot.copy_message(chat_id=partner, from_chat_id=uid, message_id=message.message_id, **extra)
        _remember(uid, message.message_id, partner, sent.message_id)
    except TelegramForbiddenError:
        store.end_chat(uid)
        await message.answer(T.t("partner_left"), reply_markup=K.main_menu())
    except TelegramBadRequest as e:
        log.warning("copy_message failed: %s", e)
        await message.answer(T.t("send_failed"))
