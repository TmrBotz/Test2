# ======================================================
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# 🔥 Fast Upload Engine v3.0 - With Progress Bar
# ======================================================

"""
🎬  rogmovies.py — RogMovies.club Scraper
🚂 Download → Upload Engine with Progress Bars
"""

import os
import re
import html
import time
import asyncio
import logging
import requests
import aiofiles
import aiohttp
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from typing import Optional, Tuple
import gc

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# ⚙️  CONFIG
# ══════════════════════════════════════════════

SOURCE_NAME    = "RogMovies"
CHANNEL_ID     = os.environ["ROGMOVIES_CHANNEL_ID"]
BASE_URL       = os.environ.get("ROGMOVIES_URL", "https://rogmovies.club/")
CHECK_INTERVAL = int(os.environ.get("ROGMOVIES_INTERVAL", "300"))
DB_COLLECTION  = "rogmovies_seen"

# Download temp directory
TEMP_DIR = os.environ.get("ROGMOVIES_TEMP_DIR", "/tmp/rogmovies")

# Quality priority
QUALITY_PRIORITY = os.environ.get("ROGMOVIES_QUALITY", "").lower()

# Max file size for Telegram (2GB)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
MAX_FILE_SIZE_MB = 2048

# Upload settings
MAX_RETRIES = 3

# Progress bar settings
PROGRESS_BAR_LENGTH = 20

# ══════════════════════════════════════════════
# 🔌  INIT
# ══════════════════════════════════════════════

_col = None
_status_messages = {}  # Store status message objects for updating

def init(db):
    global _col
    _col = db[DB_COLLECTION]
    os.makedirs(TEMP_DIR, exist_ok=True)
    log.info(f"[{SOURCE_NAME}] ✅ MongoDB ready | Temp: {TEMP_DIR}")
    log.info(f"[{SOURCE_NAME}] 🚂 Max file size: {MAX_FILE_SIZE_MB} MB")

# ══════════════════════════════════════════════
# 📊 PROGRESS BAR
# ══════════════════════════════════════════════

def create_progress_bar(current: int, total: int, bar_length: int = PROGRESS_BAR_LENGTH) -> str:
    """Create a visual progress bar"""
    if total == 0:
        return "█" * bar_length
    
    percentage = current / total
    filled_length = int(bar_length * percentage)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    percent = percentage * 100
    return f"{bar} {percent:.1f}%"

def format_size(bytes_size: int) -> str:
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def format_speed(speed_bytes: float) -> str:
    """Format speed in MB/s"""
    speed_mb = speed_bytes / (1024 * 1024)
    return f"{speed_mb:.1f} MB/s"

async def update_status_message(context, chat_id: int, message_id: int, text: str):
    """Update status message without spamming"""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        log.warning(f"Status update failed: {e}")

# ══════════════════════════════════════════════
# 🌐  HTTP SESSION
# ══════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ══════════════════════════════════════════════
# 🍃  MONGODB
# ══════════════════════════════════════════════

def is_seen(post_id: str) -> bool:
    try:
        return _col.find_one({"post_id": post_id}) is not None
    except Exception as e:
        log.error(f"[{SOURCE_NAME}] DB error: {e}")
        return False

def mark_seen(post_id: str, url: str):
    try:
        _col.update_one({"post_id": post_id}, {"$set": {"post_id": post_id, "url": url}}, upsert=True)
    except Exception as e:
        log.error(f"[{SOURCE_NAME}] DB error: {e}")

# ══════════════════════════════════════════════
# 📡  HOMEPAGE SCRAPE
# ══════════════════════════════════════════════

def fetch_latest_posts() -> list:
    log.info(f"[{SOURCE_NAME}] Fetching: {BASE_URL}")
    posts = []
    try:
        resp = SESSION.get(BASE_URL, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        grid = soup.find("div", class_="movies-grid")
        if not grid:
            log.warning(f"[{SOURCE_NAME}] No movies-grid found")
            return posts

        for a in grid.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            
            slug = href.rstrip("/").split("/")[-1]
            if not slug:
                continue
                
            title_tag = a.find("p", class_="poster-title")
            title = title_tag.get_text(strip=True) if title_tag else slug
            posts.append({"post_id": slug, "title": title, "url": href})

    except Exception as e:
        log.error(f"[{SOURCE_NAME}] Fetch error: {e}")
    
    log.info(f"[{SOURCE_NAME}] Found {len(posts)} posts")
    return posts

# ══════════════════════════════════════════════
# 🔗  RESOLVERS
# ══════════════════════════════════════════════

def _resolve_vcloud(url: str) -> list:
    log.info(f"    [VCloud] Resolving...")
    links = []
    try:
        resp1 = SESSION.get(url, timeout=15)
        resp1.raise_for_status()
        
        m = re.search(r"var url\s*=\s*'(https://vcloud\.zip/[^']+)'", resp1.text)
        if not m:
            return links
            
        token_url = m.group(1)
        time.sleep(1)
        
        resp2 = SESSION.get(token_url, timeout=15)
        resp2.raise_for_status()
        soup = BeautifulSoup(resp2.text, "html.parser")
        
        s3_tag = soup.find("a", id="s3")
        if s3_tag and s3_tag.get("href", "").startswith("http"):
            links.append(("⚡ FSLv2", s3_tag["href"]))
        
        fsl_tag = soup.find("a", id="fsl")
        if fsl_tag and fsl_tag.get("href", "").startswith("http"):
            links.append(("📀 FSL", fsl_tag["href"]))
        
        pxl_m = re.search(r'var pxl\s*=\s*"(https://pixeldrain[^"]+)"', resp2.text)
        if pxl_m:
            links.append(("☁️ PixelDrain", pxl_m.group(1)))
            
    except Exception as e:
        log.warning(f"    [VCloud] Error: {e}")
    
    return links

def _resolve_nexdrive(url: str) -> list:
    log.info(f"  [NexDrive] Fetching...")
    links = []
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        vcloud_tag = soup.find("a", href=re.compile(r"vcloud\.zip/"))
        if vcloud_tag:
            vcloud_href = vcloud_tag["href"].strip()
            vlinks = _resolve_vcloud(vcloud_href)
            for label, vurl in vlinks:
                links.append((label, vurl))
            time.sleep(1)
    except Exception as e:
        log.warning(f"  [NexDrive] Error: {e}")
    
    return links

# ══════════════════════════════════════════════
# 🕷️  SCRAPE FUNCTION
# ══════════════════════════════════════════════

def scrape_download_links(movie_url: str) -> list:
    log.info(f"[{SOURCE_NAME}] Scraping: {movie_url}")
    quality_data = []
    
    try:
        resp = SESSION.get(movie_url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log.error(f"[{SOURCE_NAME}] Fetch error: {e}")
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    page_body = soup.find("main", class_="page-body") or soup.find("div", class_="entry-inner")
    if not page_body:
        log.warning(f"[{SOURCE_NAME}] No page-body found")
        return []
    
    for h5 in page_body.find_all("h5"):
        quality_label = h5.get_text(strip=True)
        if not quality_label:
            continue
        
        nexdrive_url = None
        for sibling in h5.find_next_siblings():
            a = sibling.find("a", href=re.compile(r"nexdrive\.pro/")) if sibling.name != "a" else sibling
            if a is None and sibling.name == "a" and "nexdrive.pro" in sibling.get("href", ""):
                a = sibling
            if a:
                nexdrive_url = a["href"].strip()
                break
            if sibling.name == "h5":
                break
        
        if not nexdrive_url:
            continue
        
        log.info(f"[{SOURCE_NAME}] Quality: {quality_label}")
        links = _resolve_nexdrive(nexdrive_url)
        if links:
            quality_data.append({"quality": quality_label, "links": links})
        time.sleep(1)
    
    return quality_data

# ══════════════════════════════════════════════
# 📥 DOWNLOAD WITH PROGRESS BAR
# ══════════════════════════════════════════════

async def get_file_size(url: str) -> int:
    """Get file size without downloading"""
    try:
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            async with session.head(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    return int(resp.headers.get("Content-Length", 0))
    except Exception as e:
        log.warning(f"Size check failed: {e}")
    return 0

def _pick_best_download_url(links: list) -> Tuple[str, str]:
    priority_map = {"fslv2": 0, "fsl": 1, "pixeldrain": 2}
    for label, url in links:
        label_lower = label.lower()
        for key in priority_map:
            if key in label_lower:
                return label, url
    return links[0] if links else ("", "")

def _pick_quality(quality_data: list) -> Optional[dict]:
    if not quality_data:
        return None
    if QUALITY_PRIORITY:
        for ql in quality_data:
            if QUALITY_PRIORITY in ql["quality"].lower():
                return ql
    return quality_data[0]

def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name.strip(". ")[:200] or "video"

async def download_with_progress(url: str, dest_path: str, title: str, status_msg_id: int, chat_id: int, context) -> Tuple[bool, str]:
    """Download file with visual progress bar"""
    
    log.info(f"📥 Starting download: {title[:50]}...")
    
    # Check file size first
    file_size = await get_file_size(url)
    if file_size > MAX_FILE_SIZE:
        return False, f"❌ File too large: {format_size(file_size)} (Max: {MAX_FILE_SIZE_MB}MB)"
    
    try:
        timeout = aiohttp.ClientTimeout(total=3600, connect=30)
        headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://vcloud.zip/"}
        
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False, f"HTTP {resp.status}"
                
                total = int(resp.headers.get("Content-Length", file_size))
                downloaded = 0
                start_time = time.time()
                last_update = 0
                
                async with aiofiles.open(dest_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(512 * 1024):  # 512KB chunks
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress bar every 2 seconds or every 5%
                        now = time.time()
                        if total > 0:
                            percentage = (downloaded / total) * 100
                            if now - last_update >= 2 or int(percentage) % 5 == 0:
                                last_update = now
                                elapsed = now - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                
                                # Create progress bar
                                bar = create_progress_bar(downloaded, total)
                                downloaded_fmt = format_size(downloaded)
                                total_fmt = format_size(total)
                                speed_fmt = format_speed(speed)
                                
                                status_text = (
                                    f"🚂 <b>Downloading...</b>\n\n"
                                    f"🎬 <b>{html.escape(title[:60])}</b>\n\n"
                                    f"<code>{bar}</code>\n\n"
                                    f"📥 {downloaded_fmt} / {total_fmt}\n"
                                    f"⚡ Speed: {speed_fmt}\n"
                                    f"⏱️ Elapsed: {elapsed:.1f}s"
                                )
                                
                                await update_status_message(context, chat_id, status_msg_id, status_text)
                
                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0
                log.info(f"✅ Download complete: {format_size(downloaded)} in {elapsed:.1f}s ({format_speed(speed)})")
                return True, "Download complete"
                
    except Exception as e:
        return False, f"Download error: {e}"

# ══════════════════════════════════════════════
# 📤 UPLOAD WITH PROGRESS BAR
# ══════════════════════════════════════════════

def _build_caption(title: str, quality_label: str) -> str:
    return f"🎬 <b>{html.escape(title)}</b>\n\n📦 <b>{html.escape(quality_label)}</b>"

async def upload_with_progress(bot: Bot, file_path: str, caption: str, title: str, status_msg_id: int, chat_id: int, context) -> bool:
    """Upload file with progress indication (Telegram doesn't provide upload progress, so we show pre-upload status)"""
    
    file_size = Path(file_path).stat().st_size
    size_mb = file_size / (1024 * 1024)
    
    if file_size > MAX_FILE_SIZE:
        log.error(f"File too large: {size_mb:.1f}MB")
        return False
    
    # Show preparing for upload
    status_text = (
        f"📤 <b>Preparing for upload...</b>\n\n"
        f"🎬 <b>{html.escape(title[:60])}</b>\n\n"
        f"📦 Size: {format_size(file_size)}\n"
        f"⏳ Starting upload to Telegram..."
    )
    await update_status_message(context, chat_id, status_msg_id, status_text)
    
    for attempt in range(MAX_RETRIES):
        try:
            start_time = time.time()
            
            with open(file_path, "rb") as f:
                await bot.send_video(
                    chat_id=CHANNEL_ID,
                    video=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    supports_streaming=True,
                    read_timeout=600,
                    write_timeout=600,
                    connect_timeout=60,
                    pool_timeout=600
                )
            
            elapsed = time.time() - start_time
            log.info(f"✅ Upload complete: {format_size(file_size)} in {elapsed:.1f}s")
            
            # Show success status
            status_text = (
                f"✅ <b>Upload Complete!</b>\n\n"
                f"🎬 <b>{html.escape(title[:60])}</b>\n\n"
                f"📦 Size: {format_size(file_size)}\n"
                f"⏱️ Time: {elapsed:.1f}s"
            )
            await update_status_message(context, chat_id, status_msg_id, status_text)
            return True
            
        except TelegramError as e:
            error_str = str(e).lower()
            if "file is too big" in error_str or "413" in error_str:
                status_text = f"❌ <b>Upload Failed</b>\n\nFile too large: {format_size(file_size)}\nMax: 2GB"
                await update_status_message(context, chat_id, status_msg_id, status_text)
                return False
            
            if attempt < MAX_RETRIES - 1:
                wait_time = (attempt + 1) * 5
                status_text = (
                    f"🔄 <b>Retry {attempt+1}/{MAX_RETRIES}</b>\n\n"
                    f"🎬 {html.escape(title[:60])}\n"
                    f"⏳ Waiting {wait_time}s..."
                )
                await update_status_message(context, chat_id, status_msg_id, status_text)
                await asyncio.sleep(wait_time)
            else:
                status_text = f"❌ <b>Upload Failed</b>\n\n{str(e)[:100]}"
                await update_status_message(context, chat_id, status_msg_id, status_text)
                log.error(f"Upload failed after {MAX_RETRIES} attempts: {e}")
                
        except Exception as e:
            log.error(f"Upload error: {e}")
            status_text = f"❌ <b>Upload Error</b>\n\n{str(e)[:100]}"
            await update_status_message(context, chat_id, status_msg_id, status_text)
    
    return False

def _cleanup(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
            log.info(f"🗑️ Deleted: {os.path.basename(path)}")
    except Exception as e:
        log.warning(f"Cleanup error: {e}")

# ══════════════════════════════════════════════
# 🚂 MAIN ENGINE WITH PROGRESS
# ══════════════════════════════════════════════

_upload_lock = asyncio.Lock()

async def process_movie_with_progress(bot: Bot, title: str, quality_data: list, status_msg_id: int, chat_id: int, context) -> Tuple[bool, str]:
    """Process movie with progress updates"""
    
    async with _upload_lock:
        try:
            # Select quality
            ql = _pick_quality(quality_data)
            if not ql:
                return False, "No quality found"
            
            label, dl_url = _pick_best_download_url(ql["links"])
            if not dl_url:
                return False, "No download URL found"
            
            quality_label = ql["quality"]
            log.info(f"Selected: [{quality_label}] via {label}")
            
            # Update status - preparing
            status_text = (
                f"🚂 <b>Processing Movie</b>\n\n"
                f"🎬 <b>{html.escape(title[:60])}</b>\n\n"
                f"📦 Quality: {html.escape(quality_label)}\n"
                f"🔗 Source: {label}\n\n"
                f"⏳ Preparing download..."
            )
            await update_status_message(context, chat_id, status_msg_id, status_text)
            
            # Prepare filename
            ext = ".mp4"
            for ext_check in [".mp4", ".mkv", ".avi"]:
                if ext_check in dl_url.lower():
                    ext = ext_check
                    break
            
            safe_name = _safe_filename(f"{title}_{quality_label}")
            dest_path = os.path.join(TEMP_DIR, f"{safe_name}{ext}")
            
            # Download with progress
            download_success, download_msg = await download_with_progress(
                dl_url, dest_path, title, status_msg_id, chat_id, context
            )
            
            if not download_success:
                _cleanup(dest_path)
                return False, download_msg
            
            # Upload with progress
            caption = _build_caption(title, quality_label)
            upload_success = await upload_with_progress(
                bot, dest_path, caption, title, status_msg_id, chat_id, context
            )
            
            # Cleanup
            _cleanup(dest_path)
            gc.collect()
            
            if upload_success:
                return True, "Movie uploaded successfully!"
            else:
                return False, "Upload failed"
                
        except Exception as e:
            log.error(f"Process error: {e}")
            return False, str(e)

# ══════════════════════════════════════════════
# 🎯  PROCESS URL
# ══════════════════════════════════════════════

async def process_url(bot: Bot, movie_url: str, post: dict = None, status_msg_id: int = None, chat_id: int = None, context=None) -> Tuple[bool, str]:
    """Scrape and upload movie with progress"""
    
    # Scrape links
    quality_data = scrape_download_links(movie_url)
    if not quality_data:
        return False, "No download links found"
    
    # Get title
    title = post.get("title", "Unknown") if post else "Unknown"
    if not post or title == "Unknown":
        try:
            resp = SESSION.get(movie_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("h1", class_="post-title")
            if title_tag:
                title = title_tag.get_text(strip=True)
        except:
            pass
    
    # If no status message provided, create one
    if status_msg_id is None and context:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🚂 <b>Starting RogMovies Processor</b>\n\n🎬 {html.escape(title[:50])}...",
            parse_mode=ParseMode.HTML
        )
        status_msg_id = status_msg.message_id
    
    return await process_movie_with_progress(bot, title, quality_data, status_msg_id, chat_id, context)

# ══════════════════════════════════════════════
# 💬  COMMAND HANDLER
# ══════════════════════════════════════════════

async def cmd_rogmovies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            f"🎬 <b>RogMovies Uploader</b>\n\n"
            f"<code>/rogmovies https://rogmovies.club/movie-name/</code>\n\n"
            f"⚡ Features:\n"
            f"• 📊 Real-time progress bar\n"
            f"• 📥 Download speed display\n"
            f"• 📤 Auto upload to channel\n"
            f"• 📏 Max file size: 2GB\n"
            f"• 🔄 Auto retry on failure",
            parse_mode=ParseMode.HTML
        )
        return
    
    movie_url = context.args[0].strip()
    if not movie_url.startswith("http"):
        await update.message.reply_text("❌ Valid URL required (http/https)")
        return
    
    # Send initial status message
    status_msg = await update.message.reply_text(
        f"🚂 <b>RogMovies Processor</b>\n\n"
        f"🔗 <code>{movie_url[:80]}</code>\n\n"
        f"⏳ Initializing...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        success, result_msg = await process_url(
            context.bot, 
            movie_url, 
            None, 
            status_msg.message_id, 
            update.effective_chat.id,
            context
        )
        
        if not success:
            await status_msg.edit_text(
                f"❌ <b>Failed</b>\n\n{result_msg}",
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        log.error(f"Command error: {e}")
        await status_msg.edit_text(
            f"❌ <b>Error</b>\n\n{str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ══════════════════════════════════════════════
# 🔄  AUTO LOOP
# ══════════════════════════════════════════════

async def rss_loop(bot: Bot):
    log.info(f"[{SOURCE_NAME}] 🔁 Auto-loop started | Interval: {CHECK_INTERVAL}s")
    log.info(f"[{SOURCE_NAME}] 📏 Max file size: {MAX_FILE_SIZE_MB} MB")
    
    while True:
        try:
            posts = fetch_latest_posts()
            new_posts = [p for p in posts if not is_seen(p["post_id"])]
            
            if new_posts:
                log.info(f"[{SOURCE_NAME}] 🆕 {len(new_posts)} new posts!")
                for post in new_posts:
                    log.info(f"  ▶ {post['title']}")
                    
                    # For auto mode, we can't send progress to channel (would spam)
                    # So just log progress
                    success, msg = await process_url(bot, post["url"], post)
                    
                    if success:
                        mark_seen(post["post_id"], post["url"])
                        log.info(f"  ✅ Success: {post['title']}")
                    else:
                        log.warning(f"  ⚠️ Failed: {post['title']} - {msg}")
                    
                    await asyncio.sleep(10)
                    gc.collect()
            else:
                log.info(f"[{SOURCE_NAME}] No new posts")
                
        except Exception as e:
            log.error(f"[{SOURCE_NAME}] Loop error: {e}")
        
        log.info(f"[{SOURCE_NAME}] ⏳ Waiting {CHECK_INTERVAL}s...")
        await asyncio.sleep(CHECK_INTERVAL)

# ======================================================
# 🔥 Code Created by @TMR_Supportt_bot | Tmr_Developer
# ======================================================
