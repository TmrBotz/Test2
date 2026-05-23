"""
🎬 Movie RSS Telegram Bot
Render / Koyeb + MongoDB Atlas compatible version
"""

import os
import time
import logging
import asyncio
import threading
import feedparser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from pymongo import MongoClient
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ══════════════════════════════════════════════
# ⚙️  CONFIGURATION
# ══════════════════════════════════════════════

BOT_TOKEN      = os.environ["BOT_TOKEN"]
CHANNEL_ID     = os.environ["CHANNEL_ID"]
MONGO_URI      = os.environ["MONGO_URI"]          # MongoDB Atlas connection string
RSS_FEED_URL   = os.environ.get("RSS_FEED_URL", "https://uncutbaba.best/feed/")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))
PORT           = int(os.environ.get("PORT", "8000"))

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
    log.info(f"Health check server port {PORT} pe shuru hua")
    server.serve_forever()

# ══════════════════════════════════════════════
# 🌐  HEADERS
# ══════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ══════════════════════════════════════════════
# 🍃  MONGODB — seen posts store karo
# ══════════════════════════════════════════════

def get_db_collection():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db     = client["movie_rss_bot"]
    return db["seen_posts"]

def is_seen(url: str) -> bool:
    try:
        col = get_db_collection()
        return col.find_one({"url": url}) is not None
    except Exception as e:
        log.error(f"MongoDB is_seen error: {e}")
        return False  # Error pe safe side — process karo

def mark_seen(url: str):
    try:
        col = get_db_collection()
        col.update_one({"url": url}, {"$set": {"url": url}}, upsert=True)
        log.info(f"  💾 MongoDB mein save kiya: {url[:60]}...")
    except Exception as e:
        log.error(f"MongoDB mark_seen error: {e}")

# ══════════════════════════════════════════════
# 📡  STEP 1: RSS feed se naye posts
# ══════════════════════════════════════════════

def fetch_rss_posts() -> list:
    log.info(f"RSS check: {RSS_FEED_URL}")
    feed = feedparser.parse(RSS_FEED_URL)
    posts = []
    for entry in feed.entries:
        thumbnail = ""
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            thumbnail = entry.media_thumbnail[0].get("url", "")
        elif hasattr(entry, "enclosures") and entry.enclosures:
            thumbnail = entry.enclosures[0].get("href", "")
        posts.append({
            "title": entry.get("title", "Unknown Title"),
            "url":   entry.get("link", ""),
            "thumb": thumbnail,
        })
    log.info(f"{len(posts)} posts mile RSS mein")
    return posts

# ══════════════════════════════════════════════
# 🕷️  STEP 2: Movie page → openlinks.xyz URLs
# ══════════════════════════════════════════════

def scrape_openlinks_urls(movie_url: str) -> list:
    log.info(f"Movie page scrape: {movie_url}")
    try:
        resp = SESSION.get(movie_url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Movie page error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    seen_links = set()

    for heading in soup.find_all(["h3", "h4"]):
        text = heading.get_text(strip=True)
        if "download" not in text.lower() and "link" not in text.lower():
            continue

        quality_label = text.strip()
        found_link = None

        a_in_heading = heading.find("a")
        if a_in_heading and "openlinks" in a_in_heading.get("href", ""):
            found_link = a_in_heading["href"]

        if not found_link:
            for sibling in heading.find_next_siblings(["a", "p", "div", "span"])[:5]:
                if sibling.name == "a" and "openlinks" in sibling.get("href", ""):
                    found_link = sibling["href"]
                    break
                inner = sibling.find("a")
                if inner and "openlinks" in inner.get("href", ""):
                    found_link = inner["href"]
                    break

        if found_link and found_link not in seen_links:
            seen_links.add(found_link)
            results.append({"quality": quality_label, "openlink": found_link})
            log.info(f"  ✓ {quality_label} → {found_link}")

    if not results:
        log.warning("Heading se nahi mila, fallback mode...")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "openlinks.xyz" in href and href not in seen_links:
                seen_links.add(href)
                label = a_tag.get_text(strip=True) or "Download"
                results.append({"quality": label, "openlink": href})
                log.info(f"  Fallback: {label} → {href}")

    return results

# ══════════════════════════════════════════════
# 🔓  STEP 3: openlinks.xyz unlock → final links
# ══════════════════════════════════════════════

def unlock_openlinks(openlink_url: str) -> list:
    log.info(f"  Unlock: {openlink_url}")
    try:
        resp = SESSION.get(openlink_url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"  GET error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")

    if not form:
        log.warning("  Form nahi mila, seedhe links dhundhta hun")
        return extract_final_links(soup)

    form_data = {}
    for inp in form.find_all("input"):
        name  = inp.get("name", "")
        value = inp.get("value", "")
        if name:
            form_data[name] = value

    action = form.get("action", openlink_url)
    if action.startswith("/"):
        parsed = urlparse(openlink_url)
        action = f"{parsed.scheme}://{parsed.netloc}{action}"
    elif not action.startswith("http"):
        action = openlink_url

    log.info(f"  POST → {action}")
    try:
        post_resp = SESSION.post(
            action,
            data=form_data,
            timeout=15,
            headers={**HEADERS, "Referer": openlink_url},
        )
        post_resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"  POST error: {e}")
        return []

    return extract_final_links(BeautifulSoup(post_resp.text, "html.parser"))


def extract_final_links(soup: BeautifulSoup) -> list:
    hosting_domains = [
        "gdflix", "hubdrive", "gofile.io", "streamtape", "mega.nz",
        "megaup", "voe.sx", "vidara.to", "tpead.net", "filepress",
        "send.now", "clicknupload", "dsvplay", "uploadhub",
        "drive.google", "pixeldrain", "1fichier", "rapidgator",
    ]
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http") and any(d in href for d in hosting_domains):
            if href not in links:
                links.append(href)

    if not links:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("http") and "openlinks" not in href:
                if href not in links:
                    links.append(href)

    log.info(f"  {len(links)} final links mile")
    return links

# ══════════════════════════════════════════════
# 📨  STEP 4: Telegram channel mein bhejo
# ══════════════════════════════════════════════

async def send_to_telegram(bot: Bot, post: dict, quality_links: list):
    title = post["title"]
    thumb = post["thumb"]

    lines = [f"🎬 <b>{title}</b>\n"]
    for ql in quality_links:
        quality = ql["quality"]
        links   = ql["final_links"]
        if not links:
            continue
        lines.append(f"📥 <b>{quality}</b>")
        for i, link in enumerate(links, 1):
            try:
                domain = urlparse(link).netloc.replace("www.", "")
            except Exception:
                domain = f"Link {i}"
            lines.append(f"  {i}. <a href='{link}'>{domain}</a>")
        lines.append("")

    if len(lines) <= 1:
        log.warning(f"Koi links nahi mile: {title}")
        return

    message = "\n".join(lines)
    try:
        if thumb:
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=thumb,
                caption=message[:1024],
                parse_mode=ParseMode.HTML,
            )
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=message[:4096],
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
        log.info(f"✅ Bheja: {title}")
    except TelegramError as e:
        log.error(f"❌ Telegram error ({title}): {e}")

# ══════════════════════════════════════════════
# 🔄  MAIN LOOP
# ══════════════════════════════════════════════

async def main():
    # Health check server background mein
    threading.Thread(target=start_health_server, daemon=True).start()

    # MongoDB connection test
    try:
        col = get_db_collection()
        col.database.client.admin.command("ping")
        log.info("✅ MongoDB connected!")
    except Exception as e:
        log.error(f"❌ MongoDB connection failed: {e}")
        raise

    bot = Bot(token=BOT_TOKEN)

    log.info("🤖 Bot shuru ho gaya!")
    log.info(f"   Channel : {CHANNEL_ID}")
    log.info(f"   RSS     : {RSS_FEED_URL}")
    log.info(f"   Interval: {CHECK_INTERVAL}s")

    while True:
        try:
            posts     = fetch_rss_posts()
            new_posts = [p for p in posts if not is_seen(p["url"])]

            if not new_posts:
                log.info("Koi naya post nahi.")
            else:
                log.info(f"🆕 {len(new_posts)} naye posts!")
                for post in new_posts:
                    log.info(f"\n▶ {post['title']}")
                    openlink_items = scrape_openlinks_urls(post["url"])

                    if not openlink_items:
                        log.warning("  Koi openlinks URL nahi mila, skip")
                        mark_seen(post["url"])
                        continue

                    quality_links = []
                    for item in openlink_items:
                        final = unlock_openlinks(item["openlink"])
                        quality_links.append({
                            "quality":     item["quality"],
                            "final_links": final,
                        })
                        time.sleep(2)

                    await send_to_telegram(bot, post, quality_links)
                    mark_seen(post["url"])
                    time.sleep(3)

        except Exception as e:
            log.error(f"Loop error: {e}", exc_info=True)

        log.info(f"⏳ {CHECK_INTERVAL}s mein phir check...\n")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
