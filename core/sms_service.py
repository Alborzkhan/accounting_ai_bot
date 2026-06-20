import logging
import requests
from config import FARAPAYAMAK_USERNAME, FARAPAYAMAK_PASSWORD, FARAPAYAMAK_SENDER

logger = logging.getLogger(__name__)

FARAPAYAMAK_SEND_URL = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"


def send_otp_sms(mobile: str, code: str) -> bool:
    """ارسال کد تایید با فراپیامک (Payamak-Panel REST API). اگر یوزرنیم/پسورد تنظیم نشده باشد،
    کد فقط در لاگ سرور ثبت می‌شود (حالت توسعه) تا قبل از راه‌اندازی واقعی، جریان لاگین قابل تست باشد."""
    message = f"کد تایید نارین: {code}\nاین کد ۵ دقیقه اعتبار دارد."

    if not FARAPAYAMAK_USERNAME or not FARAPAYAMAK_PASSWORD:
        logger.warning("FARAPAYAMAK_USERNAME/PASSWORD تنظیم نشده. [DEV MODE] کد تایید برای %s: %s", mobile, code)
        return True

    try:
        payload = {
            "username": FARAPAYAMAK_USERNAME,
            "password": FARAPAYAMAK_PASSWORD,
            "to": mobile,
            "from": FARAPAYAMAK_SENDER,
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
