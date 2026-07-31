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
FARAPAYAMAK_USERNAME = os.getenv("FARAPAYAMAK_USERNAME", "")
FARAPAYAMAK_PASSWORD = os.getenv("FARAPAYAMAK_PASSWORD", "")
FARAPAYAMAK_SENDER = os.getenv("FARAPAYAMAK_SENDER", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8000")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounting.db')}")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "168"))


def get_public_app_url() -> str:
    """مقدار فعلی PUBLIC_APP_URL را تازه از فایل .env می‌خواند (نه نسخه کش‌شده در زمان import).

    در محیط تست با تونل، آدرس ممکن است هر چند دقیقه تغییر کند؛ بات‌هایی که از این مقدار
    برای ساخت دکمه مینی‌اپ استفاده می‌کنند باید همیشه آخرین آدرس را بفرستند، نه آدرسی که
    موقع روشن شدن پردازه بات معتبر بوده.
    """
    try:
        from dotenv import dotenv_values
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        fresh = dotenv_values(env_path)
        return fresh.get("PUBLIC_APP_URL") or PUBLIC_APP_URL
    except Exception:
        return PUBLIC_APP_URL

def validate_config():
    errors = []
    if not TELEGRAM_TOKEN:
        errors.append("TELEGRAM_TOKEN")
    if not BALE_TOKEN:
        errors.append("BALE_TOKEN")
    if errors:
        print(f"⚠️ متغیرهای محیطی تنظیم نشده‌اند: {', '.join(errors)}")
        print("لطفاً فایل .env را بررسی کنید.")
