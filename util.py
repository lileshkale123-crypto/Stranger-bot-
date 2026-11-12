import logging
from datetime import datetime, timezone

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

log = logging.getLogger(__name__)


async def safe_edit(msg: Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit a message without ever raising (e.g. 'message is not modified')."""
    try:
        await msg.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        log.debug("edit skipped: %s", e)


def fmt_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
