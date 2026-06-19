import logging
import requests
from config import KAVENEGAR_API_KEY, KAVENEGAR_SENDER

logger = logging.getLogger(__name__)

KAVENEGAR_SEND_URL = "https://api.kavenegar.com/v1/{api_key}/sms/send.json"


def send_otp_sms(mobile: str, code: str) -> bool:
    """ارسال کد تایید با کاوه‌نگار. اگر KAVENEGAR_API_KEY تنظیم نشده باشد، کد فقط در لاگ سرور
    ثبت می‌شود (حالت توسعه) تا قبل از راه‌اندازی واقعی، جریان لاگین قابل تست باشد."""
    message = f"کد تایید نارین: {code}\nاین کد ۵ دقیقه اعتبار دارد."

    if not KAVENEGAR_API_KEY:
        logger.warning("KAVENEGAR_API_KEY تنظیم نشده. [DEV MODE] کد تایید برای %s: %s", mobile, code)
        return True

    try:
        url = KAVENEGAR_SEND_URL.format(api_key=KAVENEGAR_API_KEY)
        params = {"receptor": mobile, "message": message}
        if KAVENEGAR_SENDER:
            params["sender"] = KAVENEGAR_SENDER
        response = requests.post(url, data=params, timeout=10)
        response.raise_for_status()
        result = response.json()
        ok = result.get("return", {}).get("status") == 200
        if not ok:
            logger.error("ارسال پیامک به %s ناموفق بود: %s", mobile, result)
        return ok
    except Exception:
        logger.exception("خطا در ارسال پیامک کد تایید به %s", mobile)
        return False
