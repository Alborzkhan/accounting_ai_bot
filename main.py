
def run_bot(bot_name: str = "telegram"):
    if bot_name == "telegram":
        from bot_handlers.telegram_bot import TelegramBot
        bot = TelegramBot()
        bot.run()
    elif bot_name == "bale":
        from bot_handlers.bale_bot import BaleBot
        bot = BaleBot()
        bot.run()
    elif bot_name == "web":
        import uvicorn
        uvicorn.run("web_app.main:app", host="0.0.0.0", port=8000, reload=False)
    else:
        print(f"نام ربات نامعتبر: {bot_name}. گزینه‌ها: telegram, bale, web")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="نارین - حسابدار شخصی شما")
    parser.add_argument("--bot", choices=["telegram", "bale", "web"], default="telegram",
                        help="ربات مورد نظر برای اجرا (پیش‌فرض: telegram)")
    args = parser.parse_args()
    run_bot(args.bot)
