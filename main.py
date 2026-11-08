import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent

import chat
import db
import onboarding
import premium
import profile
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

    # Order matters: chat must be last because its relay handler catches every message.
    dp.include_router(onboarding.router)
    dp.include_router(premium.router)
    dp.include_router(profile.router)
    dp.include_router(chat.router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Set up your profile"),
            BotCommand(command="search", description="Find a random stranger"),
            BotCommand(command="next", description="Skip to a new stranger"),
            BotCommand(command="stop", description="Leave the chat or stop searching"),
            BotCommand(command="menu", description="Show the menu"),
            BotCommand(command="profile", description="View or edit your profile"),
            BotCommand(command="premium", description="Get VIP with Telegram Stars"),
        ]
    )

    try:
        log.info("Bot starting (long polling)")
        await dp.start_polling(bot)
    finally:
        await db.close_db()
        await bot.session.close()
        log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
