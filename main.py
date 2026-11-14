import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent

import admin
import chat
import db
import onboarding
import persist
import premium
import profile
import referral
import texts as T
from store import store
from config import BOT_TOKEN, DATABASE_URL

log = logging.getLogger("bot")


async def on_error(event: ErrorEvent) -> bool:
    """Log and swallow handler errors so polling never dies."""
    log.exception("Unhandled error: %s", event.exception)
    return True


async def notify_restart(bot: Bot) -> None:
    """Matches live only in memory, so a redeploy ends them. Tell those users instead
    of leaving them chatting with nobody."""
    uids = {u for u in (set(store.pairs) | set(store.queue)) if u > 0}
    for uid in uids:
        try:
            await asyncio.wait_for(bot.send_message(uid, T.t("bot_restarting")), timeout=3)
        except Exception:
            pass
        await asyncio.sleep(0.05)  # stay well under Telegram's broadcast limits


async def _persist_loop(dp: Dispatcher) -> None:
    """Saves live chats every few seconds. If a newer deployment took over, step aside."""
    while True:
        await asyncio.sleep(persist.INTERVAL)
        if not await persist.save():
            log.warning("A newer deployment took over, stopping this one")
            try:
                await dp.stop_polling()
            except Exception:
                pass
            return


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
    dp.include_router(admin.router)
    dp.include_router(onboarding.router)
    dp.include_router(premium.router)
    dp.include_router(referral.router)
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
            BotCommand(command="invite", description="Invite friends, earn free VIP"),
        ]
    )

    await persist.restore(bot)
    saver = asyncio.create_task(_persist_loop(dp))
    try:
        log.info("Bot starting (long polling)")
        await dp.start_polling(bot)
    finally:
        saver.cancel()
        await persist.save()
        await db.close_db()
        await bot.session.close()
        log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
