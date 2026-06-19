import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_BOT_NAME = os.getenv("TELEGRAM_BOT_NAME", "Hesabdarbazarbot")
BALE_TOKEN = os.getenv("BALE_TOKEN")
BALE_BOT_NAME = os.getenv("BALE_BOT_NAME", "hesabdarkuchakbot")
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "")
ZARINPAL_CALLBACK_URL = os.getenv("ZARINPAL_CALLBACK_URL", "")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "09120000000")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
KAVENEGAR_API_KEY = os.getenv("KAVENEGAR_API_KEY", "")
KAVENEGAR_SENDER = os.getenv("KAVENEGAR_SENDER", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

def validate_config():
    errors = []
    if not TELEGRAM_TOKEN:
        errors.append("TELEGRAM_TOKEN")
    if not BALE_TOKEN:
        errors.append("BALE_TOKEN")
    if errors:
        print(f"⚠️ متغیرهای محیطی تنظیم نشده‌اند: {', '.join(errors)}")
        print("لطفاً فایل .env را بررسی کنید.")
