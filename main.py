import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

import db
import onboarding
from config import BOT_TOKEN, DATABASE_URL

log = logging.getLogger("bot")


async def on_error(event: ErrorEvent) -> bool:
    """Log and swallow handler errors so polling never dies."""
    log.exception("Unhandled error: %s", event.exception)
    return True


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    await db.init_db(DATABASE_URL)

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.errors.register(on_error)
    dp.include_router(onboarding.router)

    try:
        log.info("Bot starting (long polling)")
        await dp.start_polling(bot)
    finally:
        await db.close_db()
        await bot.session.close()
        log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
