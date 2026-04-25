
Need more help? Contact @admin
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def stats(self, update: Update, context):
        """Handle /stats command"""
        cache_stats = cache.get_stats()
        heal_stats = SelfHealingExtractor.successful_patterns
        
        stats_text = f"""
📊 **Bot Statistics - Enterprise Edition**

**Status:** 🟢 Online
**Version:** 4.0 (Universal Link Parser)

**Performance:**
{cache_stats}

**Successful extractions by method:**
• 📦 JSON: {heal_stats.get('json', 0)}
• 📝 Meta: {heal_stats.get('meta', 0)}
• 🔗 DOM: {heal_stats.get('dom', 0)}
• 💬 Popup: {heal_stats.get('popup', 0)}
• 📄 Text: {heal_stats.get('text', 0)}
• 🎭 Dynamic: {heal_stats.get('dynamic', 0)}

**Link Formats Supported:**
• HTTPS/HTTP: ✅
• WWW/No WWW: ✅
• Direct shortcode: ✅

**Limits:**
• Max links/request: {MAX_LINKS_PER_REQUEST}
• Cache TTL: 1 hour
• Timeout: {REQUEST_TIMEOUT}s

✨ **Bot is fully operational with universal link support!**
        """
        await update.message.reply_text(stats_text, parse_mode='Markdown')
    
    async def cache_info(self, update: Update, context):
        """Handle /cache command"""
        info = f"""
📦 **Cache Information**

{cache.get_stats()}

**Cache TTL:** 1 hour
**Auto-cleanup:** Enabled
**Strategy:** LRU (Least Recently Used)

💡 Use /stats for more details
        """
        await update.message.reply_text(info, parse_mode='Markdown')
    
    async def process_links(self, update: Update, context):
        """Main handler for processing Instagram links - Accepts ANY format"""
        user = update.effective_user
        message = update.message
        text = message.text
        
        logger.info(f"User {user.id} sent: {text[:100]}...")
        
        # Use universal parser to extract ALL link formats
        extracted = UniversalLinkParser.extract_links(text)
        
        if not extracted:
            await message.reply_text(
                "❌ No valid Instagram links found.\n\n"
                "**Supported formats:**\n"
                "• `https://www.instagram.com/reel/...`\n"
                "• `http://instagram.com/p/...`\n"
                "• `www.instagram.com/reel/...`\n"
                "• `instagram.com/p/...`\n\n"
                "**Example:**\n"
                "`https://www.instagram.com/reel/DXj9g58AuJx`",
                parse_mode='Markdown'
            )
            return
        
        # Get unique links
        unique_links = []
        seen_shortcodes = set()
        for item in extracted:
            if item['shortcode'] not in seen_shortcodes:
                seen_shortcodes.add(item['shortcode'])
                unique_links.append(item)
        
        # Limit check
        if len(unique_links) > MAX_LINKS_PER_REQUEST:
            await message.reply_text(
                f"⚠️ Too many links! Maximum {MAX_LINKS_PER_REQUEST} per request.\n"
                f"You sent {len(unique_links)} links. Please split into multiple messages."
            )
            return
        
        # Send processing message
        status_msg = await message.reply_text(
            f"🔄 **Processing {len(unique_links)} link(s)...**\n\n"
            f"⏳ Estimated time: {len(unique_links) * 3} seconds\n"
            f"🔧 Using {len(SelfHealingExtractor.PATTERNS) + 6} extraction methods\n"
            f"🌐 Universal link parser active\n\n"
            f"Please wait..."
        )
        
        # Process links
        results = []
        success_count = 0
        
        for i, item in enumerate(unique_links):
            # Update status periodically
            if i % 3 == 0 and i > 0:
                await status_msg.edit_text(
                    f"🔄 **Processing {i+1}/{len(unique_links)}...**\n"
                    f"✅ Found: {success_count} usernames\n"
                    f"⏳ Remaining: {len(unique_links) - i}"
                )
            
            # Check cache by shortcode
            cached = cache.get(item['shortcode'])
            
            if cached:
                results.append(f"📦 `{item['original']} | {cached}`")
                success_count += 1
                logger.info(f"Cache hit for {item['shortcode']}")
                continue
            
            # Extract username
            try:
                result = await self.scraper.extract_username(item['normalized_url'])
                
                if result['success']:
                    results.append(f"✅ `{item['original']} | {result['username']}`")
                    success_count += 1
                    cache.set(item['shortcode'], result['username'])
                else:
                    results.append(f"❌ `{item['original']} | {result['error']}`")
                
                # Small delay between requests
                await asyncio.sleep(1.5)
                
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                results.append(f"❌ `{item['original']} | Unexpected error: {str(e)[:50]}`")
        
        # Format final response
        success_rate = (success_count / len(unique_links) * 100) if unique_links else 0
        
        final_text = "✅ **Extraction Complete!**\n\n"
        final_text += "\n".join(results[:25])
        
        if len(results) > 25:
            final_text += f"\n\n... and {len(results) - 25} more results"
        
        final_text += f"\n\n📊 **Summary:**\n"
        final_text += f"✅ Success: {success_count}/{len(unique_links)}\n"
        final_text += f"📈 Success Rate: {success_rate:.1f}%\n"
        final_text += f"🔧 Methods used: {len([p for p in SelfHealingExtractor.successful_patterns if SelfHealingExtractor.successful_patterns[p] > 0])}\n"
        
        if success_rate < 50:
            final_text += f"\n💡 **Tip:** Try public accounts for better results!"
        elif success_rate >= 90:
            final_text += f"\n⭐ **Excellent!** Your links are working perfectly!"
        
        await status_msg.edit_text(final_text, parse_mode='Markdown')
    
    async def button_callback(self, update: Update, context):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "stats":
            await self.stats(update, context)
        elif query.data == "cache":
            await self.cache_info(update, context)
        elif query.data == "help":
            await self.help(update, context)
    
    async def error_handler(self, update: Update, context):
        """Global error handler"""
        logger.error(f"Update {update} caused error {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ An unexpected error occurred. Please try again or contact support."
            )
    
    async def run(self):
        """Start the bot"""
        # Create application
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("stats", self.stats))
        app.add_handler(CommandHandler("cache", self.cache_info))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_links))
        app.add_handler(CallbackQueryHandler(self.button_callback))
        app.add_error_handler(self.error_handler)
        
        # Start bot
        logger.info("🚀 Bot is starting...")
        logger.info(f"📱 Bot username: @ReelScrapper_bot")
        logger.info(f"⚙️ Max links: {MAX_LINKS_PER_REQUEST}")
        logger.info(f"🔄 Extraction methods: {len(SelfHealingExtractor.PATTERNS) + 6}")
        logger.info(f"🌐 Universal link parser: ACTIVE")
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        logger.info("✅ Bot is running and ready!")
        logger.info("📝 Accepts ALL Instagram link formats!")
        
        # Keep running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await self.scraper.close()
            await app.stop()

# ============ MAIN ============
async def main():
    bot = InstagramBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
