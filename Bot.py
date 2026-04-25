# bot.py - Instagram Username Extractor Bot
import asyncio
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Your bot token
TOKEN = "8688619118:AAGpi-bKUVidIt1R_ss6vlRhOw6GX5s5uEI"

# Simple cache
cache = {}

async def extract_username(url):
    """Extract username from Instagram URL"""
    
    # Check cache
    if url in cache:
        return cache[url]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()
            
            username = None
            
            # Method 1: Embedded JSON
            json_match = re.search(r'"owner":\s*{\s*"username":\s*"([^"]+)"', html)
            if json_match:
                username = json_match.group(1)
            
            # Method 2: Meta tag
            if not username:
                soup = BeautifulSoup(html, 'lxml')
                meta = soup.find('meta', property='og:title')
                if meta and meta.get('content'):
                    match = re.search(r'^([a-zA-Z0-9._]+)\s+on\s+Instagram', meta['content'])
                    if match:
                        username = match.group(1)
            
            # Method 3: Anchor tag
            if not username:
                soup = BeautifulSoup(html, 'lxml')
                anchor = soup.find('a', href=re.compile(r'^/([a-zA-Z0-9._]+)/?$'))
                if anchor:
                    match = re.search(r'^/([a-zA-Z0-9._]+)/?$', anchor['href'])
                    if match:
                        username = match.group(1)
            
            # Method 4: Popup text
            if not username:
                popup_match = re.search(r'Never\s+miss\s+a\s+post\s+from\s+([a-zA-Z0-9._]+)', html)
                if popup_match:
                    username = popup_match.group(1)
            
            # Cache result
            if username:
                cache[url] = username
                if len(cache) > 100:
                    cache.clear()
            
            return username
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return None
        finally:
            await browser.close()

async def start(update: Update, context):
    await update.message.reply_text(
        "🎯 **Instagram Username Extractor Bot**\n\n"
        "Send me Instagram reel or post links and I'll extract the uploader's username!\n\n"
        "**Examples:**\n"
        "• https://www.instagram.com/reel/abc123/\n"
        "• https://www.instagram.com/p/xyz789/\n\n"
        "**Features:**\n"
        "✅ Single or multiple links\n"
        "✅ Fast extraction\n"
        "✅ Works with public accounts\n\n"
        "Just paste your links and I'll do the rest!"
    )

async def help_command(update: Update, context):
    await update.message.reply_text(
        "📚 **How to use:**\n\n"
        "1. Copy Instagram reel/post URLs\n"
        "2. Paste them here (one per line)\n"
        "3. I'll extract the usernames\n\n"
        "**Example input:**\n"
        "https://www.instagram.com/reel/DABC123/\n"
        "https://www.instagram.com/p/XYZ789/\n\n"
        "**Output format:**\n"
        "Link | Username\n\n"
        "**Commands:**\n"
        "/start - Welcome message\n"
        "/help - This help\n"
        "/stats - Bot statistics"
    )

async def stats(update: Update, context):
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"✅ Status: Online\n"
        f"📦 Cache size: {len(cache)} URLs\n"
        f"⚡ Response time: Instant\n"
        f"👥 Ready for team use\n\n"
        f"Bot is working perfectly!"
    )

async def process_links(update: Update, context):
    text = update.message.text
    
    # Extract Instagram URLs
    pattern = r'https?://(?:www\.)?instagram\.com/(?:reel|p)/[A-Za-z0-9_-]+'
    links = re.findall(pattern, text)
    
    if not links:
        await update.message.reply_text(
            "❌ No Instagram links found.\n\n"
            "Please send links containing 'instagram.com/reel/' or 'instagram.com/p/'"
        )
        return
    
    # Remove duplicates
    links = list(dict.fromkeys(links))
    
    # Limit to 25 links
    if len(links) > 25:
        await update.message.reply_text(f"⚠️ Too many links! Processing first 25 out of {len(links)}")
        links = links[:25]
    
    status_msg = await update.message.reply_text(
        f"🔄 Processing {len(links)} link(s)...\n"
        f"⏳ Please wait..."
    )
    
    results = []
    success_count = 0
    
    for i, link in enumerate(links):
        try:
            if i % 5 == 0 and i > 0:
                await status_msg.edit_text(
                    f"🔄 Processing {i+1}/{len(links)}...\n"
                    f"✅ Found: {success_count} usernames"
                )
            
            username = await extract_username(link)
            
            if username:
                results.append(f"✅ `{link} | {username}`")
                success_count += 1
            else:
                results.append(f"❌ `{link} | Failed to extract username`")
                
        except Exception as e:
            results.append(f"❌ `{link} | Error: {str(e)[:50]}`")
        
        await asyncio.sleep(1)
    
    final_text = "✅ **Done!**\n\n" + "\n".join(results[:30])
    
    if len(results) > 30:
        final_text += f"\n\n... and {len(results)-30} more results"
    
    final_text += f"\n\n📊 **Summary:** ✅ Success: {success_count} | ❌ Failed: {len(links)-success_count}"
    
    await status_msg.edit_text(final_text, parse_mode='Markdown')

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_links))
    
    print("🤖 Bot is starting...")
    print(f"📱 Bot username: @ReelScrapper_bot")
    print("✅ Bot is running!")
    
    app.run_polling()

if __name__ == "__main__":
    main()