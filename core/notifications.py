import sys, os

from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import sessionmaker
from core.license_manager import LicenseManager
from core.inventory_reconciler import InventoryReconciler
from database.models import init_db
from database.license_models import User

INVENTORY_REMINDER_COOLDOWN_HOURS = 24

class NotificationService:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.license_manager = LicenseManager(db_path)
        self.inventory_reconciler = InventoryReconciler(db_path)
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)

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

    def get_inventory_deficit_reminder(self, user_id: int) -> Optional[str]:
        """یادآوری دوره‌ای (هر ۲۴ ساعت حداکثر یک‌بار) برای کالاهایی که فروخته شده‌اند
        ولی هنوز فاکتور خرید یا موجودی اول دوره‌ای برایشان ثبت نشده."""
        session = self.Session()
        try:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            now = datetime.now()
            if user.last_inventory_reminder_at and (now - user.last_inventory_reminder_at) < timedelta(hours=INVENTORY_REMINDER_COOLDOWN_HOURS):
                return None

            deficits = self.inventory_reconciler.get_all_deficits(user_id)
            if not deficits:
                return None

            user.last_inventory_reminder_at = now
            session.commit()

            lines = [
                f"  • «{d['product_name']}»: {d['deficit']:,.0f} بیش از خرید/موجودی اول دوره فروخته شده"
                for d in deficits[:5]
            ]
            more = f"\n  …و {len(deficits) - 5} کالای دیگر" if len(deficits) > 5 else ""
            return (
                "📦 یادآوری: هنوز برای این کالاها فاکتور خریدی ثبت نکرده‌اید:\n"
                + "\n".join(lines) + more +
                "\n\nاگر این کالا را قبلاً (قبل از استفاده از نارین) خریده بودید، می‌توانید موجودی اول دوره‌اش را ثبت کنید."
            )
        finally:
            session.close()
