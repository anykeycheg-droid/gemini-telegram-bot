import os
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from .handlers import router
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
)

bot = Bot(token=settings.bot_token.get_secret_value(), parse_mode="HTML")
dp = Dispatcher()
dp.include_router(router)

async def health(_):
    return web.json_response({"status": "ok"})

async def on_startup(app: web.Application):
    wh_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await bot.set_webhook(wh_url, secret_token=settings.webhook_secret, drop_pending_updates=True)
    logging.info("Webhook установлен: %s", wh_url)

async def on_shutdown(_):
    await bot.delete_webhook()

def create_app() -> web.Application:
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    app.router.add_get("/", health)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=settings.port)
