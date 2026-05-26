# ======================================================
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# ======================================================

"""
🎬  bot.py — RogMovies Only Bot

Sirf RogMovies.club se movies scrape karega
Download karega aur Telegram channel pe upload karega
"""

import os
import logging
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from pymongo import MongoClient
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# ══════════════════════════════════════════════
# 📦  SCRAPER — Sirf RogMovies
# ══════════════════════════════════════════════

import rogmovies

# ══════════════════════════════════════════════
# ⚙️  CONFIG
# ══════════════════════════════════════════════

BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
PORT      = int(os.environ.get("PORT", "8000"))

# ══════════════════════════════════════════════
# 📝  LOGGING
# ══════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# 🏥  HEALTH CHECK SERVER
# ══════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info(f"Health server port {PORT} pe shuru hua")
    server.serve_forever()

# ══════════════════════════════════════════════
# 💬  COMMANDS
# ══════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 <b>RogMovies Uploader Bot</b>\n\n"
        "Ye bot RogMovies.club se movies scrape karta hai\n"
        "aur directly Telegram channel pe upload kar deta hai.\n\n"
        "📋 <b>Commands:</b>\n"
        "• /start — Yeh message\n"
        "• /help — Help\n"
        "• /status — Bot status\n"
        "• /rogmovies &lt;url&gt; — Manual upload\n\n"
        "🚂 <b>Features:</b>\n"
        "• Real-time progress bar\n"
        "• Download speed display\n"
        "• Auto upload to channel\n"
        "• Max file size: 2GB",
        parse_mode=ParseMode.HTML,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>How to use RogMovies Bot</b>\n\n"
        "🔹 <b>Manual Upload:</b>\n"
        "   <code>/rogmovies https://rogmovies.club/movie-name/</code>\n\n"
        "🔹 <b>Auto Upload:</b>\n"
        "   Bot har 5 minute mein naye movies check karega\n"
        "   aur automatically channel pe upload kar dega.\n\n"
        "🔹 <b>Check Status:</b>\n"
        "   <code>/status</code>\n\n"
        "⚡ <b>Note:</b>\n"
        "• Sirf 2GB se chote files upload honge\n"
        "• Ek time mein sirf ek video upload hota hai\n"
        "• Upload progress live dikhega",
        parse_mode=ParseMode.HTML,
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    try:
        db.client.admin.command("ping")
        db_status = "✅ Connected"
        rg_count = db["rogmovies_seen"].count_documents({})
    except Exception as e:
        db_status = f"❌ {e}"
        rg_count = "N/A"

    await update.message.reply_text(
        "📊 <b>RogMovies Bot Status</b>\n\n"
        f"🤖 Bot      : ✅ Running\n"
        f"🍃 MongoDB  : {db_status}\n"
        f"📊 Movies Uploaded: {rg_count}\n\n"
        f"⚡ Config:\n"
        f"• Channel: <code>{rogmovies.CHANNEL_ID}</code>\n"
        f"• Interval: {rogmovies.CHECK_INTERVAL}s\n"
        f"• Max Size: 2GB\n"
        f"• Temp Dir: {rogmovies.TEMP_DIR}\n\n"
        f"🚂 Auto-loop active — Naye movies apne aap upload honge!",
        parse_mode=ParseMode.HTML,
    )

# ══════════════════════════════════════════════
# 🚀  MAIN
# ══════════════════════════════════════════════

async def main():
    # 1. Health server
    threading.Thread(target=start_health_server, daemon=True).start()

    # 2. MongoDB connection
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command("ping")
        db = mongo_client["movie_rss_bot"]
        log.info("✅ MongoDB connected!")
    except Exception as e:
        log.error(f"❌ MongoDB failed: {e}")
        raise

    # 3. RogMovies init
    rogmovies.init(db)
    log.info("✅ RogMovies module initialized")

    # 4. Telegram app
    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["db"] = db

    # 5. Commands
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("rogmovies", rogmovies.cmd_rogmovies))

    log.info("🤖 RogMovies Bot shuru ho raha hai...")
    log.info(f"📢 Channel ID: {rogmovies.CHANNEL_ID}")
    log.info(f"⏱️ Check interval: {rogmovies.CHECK_INTERVAL}s")

    bot = Bot(token=BOT_TOKEN)

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # 6. Sirf RogMovies ka loop chalega
        await rogmovies.rss_loop(bot)

        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())

# ======================================================
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# ======================================================
