import logging
import requests
from config import FARAPAYAMAK_USERNAME, FARAPAYAMAK_PASSWORD, FARAPAYAMAK_SENDER

logger = logging.getLogger(__name__)

FARAPAYAMAK_SEND_URL = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"
FARAPAYAMAK_CREDIT_URL = "https://rest.payamak-panel.com/api/SendSMS/GetCredit"


def _load_credentials() -> dict:
    """تنظیمات پنل ادمین (دیتابیس) را اول می‌خواند؛ متغیرهای .env فقط fallback برای توسعه/سازگاری قدیمی‌اند."""
    settings = {}
    try:
        from core.platform_settings import PlatformSettingsManager
        settings = PlatformSettingsManager().get_all()
    except Exception:
        settings = {}
    return {
        "username": settings.get("sms_username") or FARAPAYAMAK_USERNAME,
        "password": settings.get("sms_password") or FARAPAYAMAK_PASSWORD,
        "sender": settings.get("sms_sender") or FARAPAYAMAK_SENDER,
    }


def has_sms_credentials() -> bool:
    creds = _load_credentials()
    return bool(creds["username"] and creds["password"])


def send_otp_sms(mobile: str, code: str) -> bool:
    """ارسال کد تایید با فراپیامک (Payamak-Panel REST API). اگر یوزرنیم/پسورد تنظیم نشده باشد،
    کد فقط در لاگ سرور ثبت می‌شود (حالت توسعه) تا قبل از راه‌اندازی واقعی، جریان لاگین قابل تست باشد."""
    message = f"کد تایید نارین: {code}\nاین کد ۵ دقیقه اعتبار دارد."
    creds = _load_credentials()

    if not creds["username"] or not creds["password"]:
        logger.warning("اطلاعات فراپیامک تنظیم نشده. [DEV MODE] کد تایید برای %s: %s", mobile, code)
        return True

    try:
        payload = {
            "username": creds["username"],
            "password": creds["password"],
            "to": mobile,
            "from": creds["sender"],
            "text": message,
            "isflash": False,
        }
        response = requests.post(FARAPAYAMAK_SEND_URL, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        ok = str(result.get("RetStatus")) == "1"
        if not ok:
            logger.error("ارسال پیامک به %s ناموفق بود: %s", mobile, result)
        return ok
    except Exception:
        logger.exception("خطا در ارسال پیامک کد تایید به %s", mobile)
        return False


def test_sms_connection() -> dict:
    """برای دکمه «تست اتصال» در پنل ادمین: اعتبار حساب فراپیامک را استعلام می‌کند (بدون ارسال پیامک واقعی)."""
    creds = _load_credentials()
    if not creds["username"] or not creds["password"]:
        return {"success": False, "message": "نام کاربری/رمز فراپیامک تنظیم نشده است."}

    try:
        response = requests.post(
            FARAPAYAMAK_CREDIT_URL,
            json={"username": creds["username"], "password": creds["password"]},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        ret_status = str(result.get("RetStatus"))
        if ret_status == "1":
            credit = result.get("Value", result.get("StrRetStatus", ""))
            return {"success": True, "message": f"✅ اتصال برقرار شد. اعتبار حساب: {credit}"}
        return {"success": False, "message": f"❌ اتصال ناموفق بود (کد: {ret_status}). نام کاربری/رمز را بررسی کنید."}
    except Exception as exc:
        logger.exception("خطا در تست اتصال فراپیامک")
        return {"success": False, "message": f"❌ خطا در اتصال به فراپیامک: {exc}"}
