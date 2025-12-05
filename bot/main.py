# main.py — окончательная версия, работает на Render без ошибок
import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from .handlers import router
from .config import settings

logging.basicConfig(level=logging.INFO)

bot = Bot(token=settings.bot_token.get_secret_value(), parse_mode="HTML")
dp = Dispatcher()
dp.include_router(router)


async def health(_):
    return web.json_response({"status": "ok"})


async def on_startup(app: web.Application):
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=True
    )
    logging.info("Webhook установлен: %s", webhook_url)


async def on_shutdown(app: web.Application):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()


# ← ВОТ ЭТА СТРОКА САМАЯ ВАЖНАЯ
def create_app(argv=None) -> web.Application:   # ← argv=None обязателен!
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    app.router.add_get("/", health)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    web.run_app(create_app(), host="0.0.0.0", port=port)