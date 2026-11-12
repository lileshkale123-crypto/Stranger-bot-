"""Admin panel: /admin (inline buttons, admins only).

Features: stats, reports queue, ban/unban, VIP grant/remove, user lookup, broadcast.
Access is limited to the ids in the ADMIN_IDS environment variable.
"""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup, Message

import db
import keyboards as K
import texts as T
from config import ADMIN_IDS
from store import store
from util import fmt_dt, safe_edit

log = logging.getLogger(__name__)
router = Router()
# Everything in this router is invisible to non-admins (their updates fall through)
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

DIV = T.DIV
_bc_running = False
_bc_tasks: set[asyncio.Task] = set()


class Admin(StatesGroup):
    wait_id = State()      # data: mode = ban | vip | info
    wait_days = State()    # data: uid
    wait_broadcast = State()


def _kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def _menu_btn() -> Btn:
    return Btn(text="⬅️ Admin menu", callback_data="ad:menu")


def _cancel_kb() -> InlineKeyboardMarkup:
    return _kb([Btn(text="✖️ Cancel", callback_data="ad:menu")])


# ---------------------------------------------------------------- dashboard

async def _dashboard() -> tuple[str, InlineKeyboardMarkup]:
    d = await db.stats()
    open_reports = await db.open_report_count()
    text = T.stylize(
        "🛠 <b>Admin panel</b>\n"
        f"{DIV}\n"
        f"👥 Users: <b>{d['users']}</b>   🆕 24h: <b>{d['new_24h']}</b>\n"
        f"💎 VIP now: <b>{d['vip']}</b>   🎁 Referred: <b>{d['referred']}</b>\n"
        f"🟢 Online: <b>{store.online()}</b>   💬 Chats: <b>{store.active_chats()}</b>\n"
        f"🚩 Open reports: <b>{open_reports}</b>"
    )
    kb = _kb(
        [Btn(text=f"🚩 Reports ({open_reports})", callback_data="ad:rep:0"),
         Btn(text="🔄 Refresh", callback_data="ad:menu")],
        [Btn(text="🔨 Ban / Unban", callback_data="ad:ask:ban"),
         Btn(text="💎 VIP", callback_data="ad:ask:vip")],
        [Btn(text="🔍 User lookup", callback_data="ad:ask:info"),
         Btn(text="📢 Broadcast", callback_data="ad:bc")],
    )
    return text, kb


@router.message(Command("admin"))
@router.message(Command("stats"))
async def admin_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, kb = await _dashboard()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "ad:menu")
async def admin_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.clear()
    text, kb = await _dashboard()
    await safe_edit(cb.message, text, kb)


# ---------------------------------------------------------------- reports

async def _show_report(cb: CallbackQuery, after_id: int) -> None:
    r = await db.next_open_report(after_id)
    if not r:
        await safe_edit(cb.message, T.stylize("✅ <b>No open reports.</b>"), _kb([_menu_btn()]))
        return
    text = T.stylize(
        f"🚩 <b>Report #{r['id']}</b>\n"
        f"{DIV}\n"
        f"Reason: <b>{r['reason']}</b>\n"
        f"Reported: <code>{r['reported_id']}</code>  ({r['reports_against']} total against)\n"
        f"Reporter: <code>{r['reporter_id']}</code>\n"
        f"Date: {fmt_dt(r['created_at'])}"
    )
    kb = _kb(
        [Btn(text="🔨 Ban reported user", callback_data=f"ad:rban:{r['id']}"),
         Btn(text="✅ Dismiss", callback_data=f"ad:rdis:{r['id']}")],
        [Btn(text="👤 User card", callback_data=f"ad:u:{r['reported_id']}"),
         Btn(text="⏭ Skip", callback_data=f"ad:rep:{r['id']}")],
        [_menu_btn()],
    )
    await safe_edit(cb.message, text, kb)


@router.callback_query(F.data.startswith("ad:rep:"))
async def report_next(cb: CallbackQuery) -> None:
    await cb.answer()
    await _show_report(cb, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("ad:rdis:"))
async def report_dismiss(cb: CallbackQuery) -> None:
    await cb.answer("Dismissed")
    await db.set_report_status(int(cb.data.split(":")[2]), "dismissed")
    await _show_report(cb, 0)


@router.callback_query(F.data.startswith("ad:rban:"))
async def report_ban(cb: CallbackQuery, bot: Bot) -> None:
    rid = int(cb.data.split(":")[2])
    r = await db.next_open_report(rid - 1)
    if r and r["id"] == rid:
        await _ban(bot, r["reported_id"])
        await cb.answer("Banned")
    else:
        await cb.answer("Already handled")
    await _show_report(cb, 0)


# ---------------------------------------------------------------- user card

ASK_TEXT = {
    "ban": "🔨 <b>Ban / Unban</b>\nSend the user's Telegram ID:",
    "vip": "💎 <b>VIP</b>\nSend the user's Telegram ID:",
    "info": "🔍 <b>User lookup</b>\nSend the user's Telegram ID:",
}


@router.callback_query(F.data.startswith("ad:ask:"))
async def ask_id(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    mode = cb.data.split(":")[2]
    await state.set_state(Admin.wait_id)
    await state.update_data(mode=mode)
    await safe_edit(cb.message, T.stylize(ASK_TEXT[mode]), _cancel_kb())


async def _card(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    u = await db.user_card(uid)
    if not u:
        return T.stylize("❌ <b>User not found.</b>"), _kb([_menu_btn()])
    vip = f"until {fmt_dt(u['premium_until'])}" if db.is_premium(u) else "none"
    chat = "in a chat" if store.partner_of(uid) else ("searching" if store.in_queue(uid) else "idle")
    text = T.stylize(
        f"👤 <b>User</b> <code>{uid}</code>\n"
        f"{DIV}\n"
        f"Status: <b>{'🔨 BANNED' if u['banned'] else '✅ Active'}</b>  ·  {chat}\n"
        f"Gender: {u['gender'] or '-'}  ·  Age: {u['age_bracket'] or '-'}  ·  Region: {u['region'] or '-'}\n"
        f"💎 VIP: <b>{vip}</b>\n"
        f"⭐ Stars spent: <b>{u['stars_spent']}</b>\n"
        f"🎁 Invited: <b>{u['invited']}</b>  ·  Rewards: <b>{u['referral_rewards']}</b>\n"
        f"🚩 Reports against: <b>{u['reports_against']}</b>  ·  made: <b>{u['reports_made']}</b>\n"
        f"Joined: {fmt_dt(u['created_at'])}\n"
        f"Last seen: {fmt_dt(u['last_seen'])}"
    )
    ban_btn = (
        Btn(text="♻️ Unban", callback_data=f"ad:unban:{uid}")
        if u["banned"]
        else Btn(text="🔨 Ban", callback_data=f"ad:ban:{uid}")
    )
    kb = _kb(
        [ban_btn, Btn(text="❌ Remove VIP", callback_data=f"ad:unvip:{uid}")],
        [Btn(text="+1d", callback_data=f"ad:vip:{uid}:1"),
         Btn(text="+7d", callback_data=f"ad:vip:{uid}:7"),
         Btn(text="+30d", callback_data=f"ad:vip:{uid}:30"),
         Btn(text="✏️ Custom", callback_data=f"ad:vipc:{uid}")],
        [Btn(text="🔄 Refresh", callback_data=f"ad:u:{uid}"), _menu_btn()],
    )
    return text, kb


@router.message(StateFilter(Admin.wait_id), F.text, ~F.text.startswith("/"))
async def got_id(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(T.stylize("⚠️ <b>That's not a numeric ID.</b> Try again:"), reply_markup=_cancel_kb())
        return
    await state.clear()
    text, kb = await _card(int(raw))
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("ad:u:"))
async def show_user(cb: CallbackQuery) -> None:
    await cb.answer()
    text, kb = await _card(int(cb.data.split(":")[2]))
    await safe_edit(cb.message, text, kb)


# ---------------------------------------------------------------- ban / vip actions

async def _ban(bot: Bot, uid: int) -> bool:
    ok = await db.set_banned(uid, True)
    if not ok:
        return False
    # remove them from matching right now so a live chat can't continue
    store.dequeue(uid)
    partner = store.end_chat(uid)
    if partner is not None:
        try:
            await bot.send_message(partner, T.t("partner_left"), reply_markup=K.main_menu())
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    try:
        await bot.send_message(uid, T.t("banned"))
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    return True


@router.callback_query(F.data.startswith("ad:ban:"))
async def do_ban(cb: CallbackQuery, bot: Bot) -> None:
    uid = int(cb.data.split(":")[2])
    await cb.answer("Banned" if await _ban(bot, uid) else "User not found")
    text, kb = await _card(uid)
    await safe_edit(cb.message, text, kb)


@router.callback_query(F.data.startswith("ad:unban:"))
async def do_unban(cb: CallbackQuery) -> None:
    uid = int(cb.data.split(":")[2])
    await cb.answer("Unbanned" if await db.set_banned(uid, False) else "User not found")
    text, kb = await _card(uid)
    await safe_edit(cb.message, text, kb)


@router.callback_query(F.data.startswith("ad:vip:"))
async def do_vip(cb: CallbackQuery, bot: Bot) -> None:
    _, _, uid, days = cb.data.split(":")
    until = await db.grant_vip(int(uid), int(days))
    await cb.answer(f"+{days} days" if until else "User not found")
    if until:
        try:
            await bot.send_message(
                int(uid), T.t("premium_active", date=fmt_dt(until)), reply_markup=K.main_menu()
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    text, kb = await _card(int(uid))
    await safe_edit(cb.message, text, kb)


@router.callback_query(F.data.startswith("ad:unvip:"))
async def do_unvip(cb: CallbackQuery) -> None:
    uid = int(cb.data.split(":")[2])
    await cb.answer("VIP removed" if await db.remove_vip(uid) else "User not found")
    text, kb = await _card(uid)
    await safe_edit(cb.message, text, kb)


@router.callback_query(F.data.startswith("ad:vipc:"))
async def ask_days(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(Admin.wait_days)
    await state.update_data(uid=int(cb.data.split(":")[2]))
    await safe_edit(
        cb.message,
        T.stylize("✏️ <b>Custom VIP days</b>\nSend a number of days (1-3650):"),
        _cancel_kb(),
    )


@router.message(StateFilter(Admin.wait_days), F.text, ~F.text.startswith("/"))
async def got_days(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 3650:
        await message.answer(T.stylize("⚠️ <b>Send a whole number between 1 and 3650.</b>"), reply_markup=_cancel_kb())
        return
    uid = (await state.get_data())["uid"]
    await state.clear()
    until = await db.grant_vip(uid, int(raw))
    if until:
        try:
            await bot.send_message(uid, T.t("premium_active", date=fmt_dt(until)), reply_markup=K.main_menu())
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    text, kb = await _card(uid)
    await message.answer(text, reply_markup=kb)


# ---------------------------------------------------------------- broadcast

@router.callback_query(F.data == "ad:bc")
async def bc_ask(cb: CallbackQuery, state: FSMContext) -> None:
    if _bc_running:
        await cb.answer("A broadcast is already running", show_alert=True)
        return
    await cb.answer()
    await state.set_state(Admin.wait_broadcast)
    await safe_edit(
        cb.message,
        T.stylize(
            "📢 <b>Broadcast</b>\n"
            f"{DIV}\n"
            "Send the message you want everyone to get. Text, photo, formatting and buttons-free media all work.\n"
            "<i>You'll see a preview and confirm before anything is sent.</i>"
        ),
        _cancel_kb(),
    )


@router.message(StateFilter(Admin.wait_broadcast))
async def bc_preview(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.text and message.text.startswith("/"):
        raise SkipHandler  # let commands like /admin work normally
    ids = await db.broadcast_ids()
    await state.update_data(chat_id=message.chat.id, msg_id=message.message_id)
    await message.answer(
        T.stylize(f"👆 <b>Preview above.</b> Send it to <b>{len(ids)}</b> users?"),
        reply_markup=_kb(
            [Btn(text=f"✅ Send to {len(ids)}", callback_data="ad:bcgo"),
             Btn(text="✖️ Cancel", callback_data="ad:menu")]
        ),
        reply_to_message_id=message.message_id,
    )


@router.callback_query(F.data == "ad:bcgo")
async def bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    global _bc_running
    data = await state.get_data()
    await state.clear()
    if _bc_running or "msg_id" not in data:
        await cb.answer("Nothing to send (or one is already running)", show_alert=True)
        return
    await cb.answer("Sending…")
    _bc_running = True
    status = await cb.message.edit_text(T.stylize("📤 <b>Broadcast started…</b>"))
    task = asyncio.create_task(_broadcast(bot, data["chat_id"], data["msg_id"], status))
    _bc_tasks.add(task)  # keep a reference so it isn't garbage collected mid-run
    task.add_done_callback(_bc_tasks.discard)


async def _broadcast(bot: Bot, from_chat: int, msg_id: int, status: Message) -> None:
    global _bc_running
    sent = blocked = failed = 0
    try:
        ids = await db.broadcast_ids()
        total = len(ids)
        for i, uid in enumerate(ids, 1):
            for attempt in range(2):
                try:
                    await bot.copy_message(uid, from_chat, msg_id)
                    sent += 1
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)
                    continue  # retry once after Telegram's requested pause
                except TelegramForbiddenError:
                    blocked += 1
                except Exception:
                    failed += 1
                break
            await asyncio.sleep(0.05)  # ~20 msgs/s, under Telegram's ~30/s limit
            if i % 100 == 0:
                try:
                    await status.edit_text(T.stylize(f"📤 <b>Sending…</b> {i}/{total}"))
                except TelegramBadRequest:
                    pass
        await status.edit_text(
            T.stylize(
                "✅ <b>Broadcast finished</b>\n"
                f"{DIV}\n"
                f"Delivered: <b>{sent}</b>\nBlocked the bot: <b>{blocked}</b>\nFailed: <b>{failed}</b>"
            ),
            reply_markup=_kb([_menu_btn()]),
        )
    except Exception:
        log.exception("broadcast crashed")
    finally:
        _bc_running = False
