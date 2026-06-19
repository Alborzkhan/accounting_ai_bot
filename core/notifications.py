import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import Optional, Dict
from core.license_manager import LicenseManager

class NotificationService:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.license_manager = LicenseManager(db_path)

    def check_renewal_reminder(self, user_id: int) -> Optional[str]:
        status = self.license_manager.check_license(user_id)
        if not status["is_valid"]:
            return "⚠️ اشتراک شما به پایان رسیده است. لطفاً برای ادامه استفاده، نسبت به تمدید اشتراک خود اقدام کنید.\nبرای مشاهده پلن‌ها از دستور /pricing استفاده کنید."
        days_left = status.get("days_left", 0)
        if days_left <= 0:
            return "⚠️ اشتراک شما امروز به پایان می‌رسد. لطفاً برای تمدید اقدام کنید."
        if days_left <= 3:
            plan_name = status.get("plan_type", "جاری")
            return (
                f"⏳ {days_left} روز تا پایان اشتراک {plan_name} شما باقی مانده است.\n"
                f" لطفاً نسبت به تمدید اشتراک خود اقدام نمایید.\n"
                f"برای مشاهده پلن‌ها به صفحه قیمت‌گذاری مراجعه کنید."
            )
        if days_left <= 7:
            return (
                f"📅 {days_left} روز تا پایان اشتراک شما باقی مانده.\n"
                f"برای تمدید به موقع، می‌توانید هم‌اکنون اقدام کنید."
            )
        return None

    def get_voucher_limit_warning(self, user_id: int) -> Optional[str]:
        status = self.license_manager.check_license(user_id)
        max_v = status.get("max_vouchers", 0)
        used = status.get("used_vouchers", 0)
        if max_v > 0:
            remaining = max_v - used
            if remaining <= 5 and remaining > 0:
                return f"⚠️ تنها {remaining} سند از {max_v} سند مجاز شما باقی مانده است. برای ثبت سندهای بیشتر اشتراک خود را تمدید کنید."
            if remaining <= 0:
                return f"❌ سقف مجاز اسناد شما ({max_v} سند) به پایان رسیده است. لطفاً اشتراک خود را تمدید کنید."
        return None
