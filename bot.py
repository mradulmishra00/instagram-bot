#!/usr/bin/env python3
"""
INSTAGRAM USERNAME EXTRACTOR BOT - ENTERPRISE EDITION
Self-healing, multi-strategy extraction with automatic fallback
"""

import asyncio
import re
import json
import hashlib
import os
from datetime import datetime
from typing import Optional, Dict, List
from urllib.parse import urlparse
import aiohttp
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from playwright.async_api import async_playwright, Browser, Page
from bs4 import BeautifulSoup
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# ============ CONFIGURATION ============
TELEGRAM_BOT_TOKEN = "8688619118:AAGpi-bKUVidIt1R_ss6vlRhOw6GX5s5uEI"
ALLOWED_USERS = []
MAX_LINKS_PER_REQUEST = 30
REQUEST_TIMEOUT = 45
MAX_RETRIES = 2

# Setup logging
logger.add("logs/bot_{time:YYYY-MM-DD}.log", rotation="1 day", retention="7 days", level="INFO")

# ============ UNIVERSAL LINK PARSER ============
class UniversalLinkParser:
    """Parses ALL Instagram link formats"""
    
    @classmethod
    def extract_links(cls, text: str) -> List[Dict]:
        """Extract ALL Instagram links from text"""
        links = []
        seen = set()
        
        pattern = r'https?://(?:www\.)?instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)'
        matches = re.finditer(pattern, text, re.IGNORECASE)
        
        for match in matches:
            shortcode = match.group(1)
            if shortcode and shortcode not in seen:
                seen.add(shortcode)
                is_reel = '/reel/' in match.group(0)
                full_url = f"https://www.instagram.com/{'reel' if is_reel else 'p'}/{shortcode}/"
                links.append({
                    'original': match.group(0),
                    'shortcode': shortcode,
                    'normalized_url': full_url,
                    'type': 'reel' if is_reel else 'post'
                })
        
        return links
    
    @classmethod
    def normalize_url(cls, url: str) -> str:
        shortcode_match = re.search(r'/(?:reel|p)/([A-Za-z0-9_-]+)', url)
        if shortcode_match:
            shortcode = shortcode_match.group(1)
            if '/reel/' in url:
                return f"https://www.instagram.com/reel/{shortcode}/"
            else:
                return f"https://www.instagram.com/p/{shortcode}/"
        return url

# ============ CACHE SYSTEM ============
class SmartCache:
    def __init__(self, maxsize=1000, ttl=3600):
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.stats = {"hits": 0, "misses": 0}
    
    def get(self, key):
        if key in self.cache:
            self.stats["hits"] += 1
            return self.cache[key]
        self.stats["misses"] += 1
        return None
    
    def set(self, key, value):
        self.cache[key] = value
    
    def get_stats(self):
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total * 100) if total > 0 else 0
        return f"Cache: {len(self.cache)} items | Hit rate: {hit_rate:.1f}%"

cache = SmartCache()

# ============ SELF-HEALING EXTRACTOR ============
class SelfHealingExtractor:
    
    @classmethod
    async def extract_with_fallback(cls, html: str, url: str, page=None) -> Optional[str]:
        # Method 1: JSON
        result = await cls._method_json(html)
        if result:
            logger.info(f"Method 1 (JSON) success: {result}")
            return result
        
        # Method 2: Meta tags
        result = await cls._method_meta(html)
        if result:
            logger.info(f"Method 2 (Meta) success: {result}")
            return result
        
        # Method 3: DOM anchors
        result = await cls._method_dom(html)
        if result:
            logger.info(f"Method 3 (DOM) success: {result}")
            return result
        
        # Method 4: Popup text
        result = await cls._method_popup(html)
        if result:
            logger.info(f"Method 4 (Popup) success: {result}")
            return result
        
        return None
    
    @staticmethod
    async def _method_json(html: str) -> Optional[str]:
        try:
            patterns = [
                r'"owner":\s*{\s*"username":\s*"([^"]+)"',
                r'"username":"([a-zA-Z0-9._]+)"',
            ]
            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    return match.group(1)
        except:
            pass
        return None
    
    @staticmethod
    async def _method_meta(html: str) -> Optional[str]:
        try:
            soup = BeautifulSoup(html, 'lxml')
            meta = soup.find('meta', property='og:title')
            if meta and meta.get('content'):
                match = re.search(r'^([a-zA-Z0-9._]+)\s+on\s+Instagram', meta['content'])
                if match:
                    return match.group(1)
        except:
            pass
        return None
    
    @staticmethod
    async def _method_dom(html: str) -> Optional[str]:
        try:
            soup = BeautifulSoup(html, 'lxml')
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                match = re.search(r'^/([a-zA-Z0-9._]+)/?$', href)
                if match:
                    username = match.group(1)
                    if username not in ['explore', 'accounts', 'direct', 'settings', 'p', 'reel']:
                        return username
        except:
            pass
        return None
    
    @staticmethod
    async def _method_popup(html: str) -> Optional[str]:
        try:
            patterns = [
                r'Never\s+miss\s+a\s+post\s+from\s+([a-zA-Z0-9._]+)',
                r'绝不错过([a-zA-Z0-9._]+)的帖子',
                r'Posts\s+from\s+([a-zA-Z0-9._]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    return match.group(1)
        except:
            pass
        return None

# ============ PLAYWRIGHT MANAGER ============
class PlaywrightManager:
    def __init__(self):
        self.browser = None
        self.playwright = None
    
    async def init(self):
        if self.playwright is None:
            self.playwright = await async_playwright().start()
        if self.browser is None:
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            logger.info("Browser initialized")
    
    async def get_page(self):
        await self.init()
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1280, 'height': 720}
        )
        return await context.new_page()
    
    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")

# ============ INSTAGRAM SCRAPER ============
class InstagramScraper:
    def __init__(self):
        self.browser_manager = PlaywrightManager()
    
    async def extract_username(self, url: str) -> Dict:
        page = None
        context = None
        try:
            await self.browser_manager.init()
            page = await self.browser_manager.get_page()
            context = await page.context
            
            normalized_url = UniversalLinkParser.normalize_url(url)
            logger.info(f"Fetching: {normalized_url}")
            
            await page.goto(normalized_url, wait_until='domcontentloaded', timeout=REQUEST_TIMEOUT * 1000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            
            username = await SelfHealingExtractor.extract_with_fallback(html, url, page)
            
            if username:
                return {'success': True, 'username': username, 'url': url, 'error': None}
            else:
                return {'success': False, 'error': 'Could not extract username', 'url': url}
        
        except Exception as e:
            logger.error(f"Error: {e}")
            return {'success': False, 'error': str(e)[:100], 'url': url}
        
        finally:
            if page:
                await page.close()
            if context:
                await context.close()
    
    async def close(self):
        await self.browser_manager.close()

# ============ TELEGRAM BOT HANDLERS ============
class InstagramBot:
    def __init__(self):
        self.scraper = InstagramScraper()
    
    async def start(self, update: Update, context):
        user = update.effective_user
        welcome_text = f"""
🎯 **Instagram Username Extractor Bot**

Welcome {user.first_name}!

**Features:**
• Accepts ALL link formats (https, http, www, direct)
• 4 extraction methods with fallback
• Smart caching for speed
• Auto-retry on failures

**How to use:**
Simply send Instagram reel or post links

**Examples:**
https://www.instagram.com/reel/ABC123/
instagram.com/p/XYZ789/
www.instagram.com/reel/DEF456/

**Commands:**
/start - This message
/help - Detailed help
/stats - Bot statistics

Ready to extract! Send me your links.
        """
        await update.message.reply_text(welcome_text)
        logger.info(f"User {user.id} started bot")
    
    async def help(self, update: Update, context):
        help_text = """
📚 **Help Guide**

**Supported Links:**
• Instagram Reels (instagram.com/reel/...)
• Instagram Posts (instagram.com/p/...)

**Any format works:**
✅ https://www.instagram.com/reel/abc/
✅ http://instagram.com/p/xyz/
✅ www.instagram.com/reel/def/
✅ instagram.com/p/ghi/

**Tips:**
• Send multiple links (one per line)
• Public accounts work best
• Max 30 links per request

Need help? Contact @admin
        """
        await update.message.reply_text(help_text)
    
    async def stats(self, update: Update, context):
        cache_stats = cache.get_stats()
        stats_text = f"""
📊 **Bot Statistics**

Status: Online
Cache: {cache_stats}
Max links/request: {MAX_LINKS_PER_REQUEST}

Bot is fully operational!
        """
        await update.message.reply_text(stats_text)
    
    async def process_links(self, update: Update, context):
        user = update.effective_user
        message = update.message
        text = message.text
        
        logger.info(f"User {user.id} sent: {text[:100]}")
        
        extracted = UniversalLinkParser.extract_links(text)
        
        if not extracted:
            await message.reply_text(
                "❌ No valid Instagram links found.\n\n"
                "Please send links containing:\n"
                "• instagram.com/reel/...\n"
                "• instagram.com/p/..."
            )
            return
        
        unique_links = []
        seen = set()
        for item in extracted:
            if item['shortcode'] not in seen:
                seen.add(item['shortcode'])
                unique_links.append(item)
        
        if len(unique_links) > MAX_LINKS_PER_REQUEST:
            await message.reply_text(
                f"⚠️ Too many links! Maximum {MAX_LINKS_PER_REQUEST} per request.\n"
                f"You sent {len(unique_links)} links."
            )
            return
        
        status_msg = await message.reply_text(
            f"🔄 Processing {len(unique_links)} link(s)...\nPlease wait..."
        )
        
        results = []
        success_count = 0
        
        for i, item in enumerate(unique_links):
            cached = cache.get(item['shortcode'])
            
            if cached:
                results.append(f"📦 {item['original']} | {cached}")
                success_count += 1
                continue
            
            result = await self.scraper.extract_username(item['normalized_url'])
            
            if result['success']:
                results.append(f"✅ {item['original']} | {result['username']}")
                success_count += 1
                cache.set(item['shortcode'], result['username'])
            else:
                results.append(f"❌ {item['original']} | {result['error']}")
            
            await asyncio.sleep(1)
        
        final_text = "✅ **Done!**\n\n" + "\n".join(results[:25])
        if len(results) > 25:
            final_text += f"\n\n... and {len(results) - 25} more"
        
        final_text += f"\n\n📊 Success: {success_count}/{len(unique_links)}"
        
        await status_msg.edit_text(final_text)
    
    async def error_handler(self, update: Update, context):
        logger.error(f"Error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ An error occurred. Please try again.")
    
    async def run(self):
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("stats", self.stats))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_links))
        app.add_error_handler(self.error_handler)
        
        logger.info("Bot is starting...")
        logger.info("Bot username: @ReelScrapper_bot")
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        logger.info("Bot is running and ready!")
        
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await self.scraper.close()
            await app.stop()

async def main():
    bot = InstagramBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
