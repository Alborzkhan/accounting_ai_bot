# bot_handlers/base_bot.py
"""کلاس پایه مشترک برای ربات‌های تلگرام و بله - حذف کد تکراری"""

import sys, os

import re
from datetime import datetime
from typing import Dict, Optional, Any

from core.accounting_engine import AccountingEngine
from core.text_command_handler import TextCommandHandler
from core.smart_dialog_engine import SmartDialogEngine
from ai_handlers.voice_to_accounting import VoiceToAccounting
from core.auth import AuthManager
from core.notifications import NotificationService
from core.license_manager import LicenseManager
from ai_handlers.llm_processor import LLMProcessor


class BaseBot:
    """کلاس پایه با منطق مشترک برای همه پلتفرم‌های پیام‌رسان.

    پلتفرم‌های فرزند (TelegramBot, BaleBot) فقط متدهای send_message و دریافت پیام را
    مطابق API خود پیاده‌سازی می‌کنند و بقیه منطق از این کلاس ارث‌بری می‌شود.
    """

    BOT_NAME = "نارین"

    # کلمات کلیدی عددی فارسی
    PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
    ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

    def __init__(self) -> None:
        self.engine = AccountingEngine()
        self.text_handler = TextCommandHandler(self.engine)
        self.dialog = SmartDialogEngine(self.engine)
        self.voice_handler = VoiceToAccounting(model_size="base")
        self.auth_manager = AuthManager()
        self.notifier = NotificationService()
        self.license_manager = LicenseManager()
        self.llm = LLMProcessor()

    # ---- متدهای انتزاعی (باید در کلاس فرزند پیاده‌سازی شوند) ----
    def send_message(self, chat_id: Any, text: str, **kwargs) -> None:
        """ارسال پیام به کاربر (مخصوص هر پلتفرم)."""
        raise NotImplementedError

    # ---- منطق مشترک ----

    def normalize_mobile(self, raw: str) -> str:
        """تبدیل اعداد فارسی/عربی به انگلیسی و استانداردسازی شماره موبایل."""
        out = []
        for ch in raw.strip():
            if ch in self.PERSIAN_DIGITS:
                out.append(str(self.PERSIAN_DIGITS.index(ch)))
            elif ch in self.ARABIC_DIGITS:
                out.append(str(self.ARABIC_DIGITS.index(ch)))
            elif ch.isdigit():
                out.append(ch)
        digits = "".join(out)
        if digits.startswith("98") and len(digits) == 12:
            digits = "0" + digits[2:]
        elif digits.startswith("9") and len(digits) == 10:
            digits = "0" + digits
        return digits

    def normalize_business_type(self, raw: str) -> str:
        """نرمال‌سازی نوع کسب‌وکار."""
        mapping = {
            "اهن": "آهن‌آلات", "آهن": "آهن‌آلات", "فلز": "آهن‌آلات",
            "بازرگانی": "بازرگانی عمومی", "بازرگانی عمومی": "بازرگانی عمومی",
            "خدمات": "خدماتی", "خدماتی": "خدماتی",
            "تولید": "تولیدی", "تولیدی": "تولیدی",
            "پیمانکاری": "پیمانکاری",
            "غذا": "مواد غذایی", "مواد غذایی": "مواد غذایی",
            "لباس": "پوشاک", "پوشاک": "پوشاک",
            "آرایش": "آرایشگاهی", "آرایشگاهی": "آرایشگاهی",
        }
        return mapping.get(raw.strip(), raw.strip())

    def clean_name(self, raw: str) -> str:
        """پاکسازی نام از کلمات اضافی."""
        words_to_remove = ["هستم", "من", "اسم", "نام", "بنده", "حقیر"]
        for w in words_to_remove:
            raw = raw.replace(w, "")
        return raw.strip()

    def get_onboarding_start_text(self) -> str:
        return (
            f"سلام! 👋 من {self.BOT_NAME} هستم 🤖\n"
            "حسابدار شخصی و هوشمند شما\n\n"
            "هنوز حساب خود را به نارین وصل نکردی. اگه قبلاً از وب‌اپ یا پیام‌رسان دیگر ثبت‌نام کرده باشی،\n"
            "با وارد کردن همون شماره موبایل، مستقیم به همون حساب وصل می‌شی - نیازی به ثبت‌نام دوباره نیست.\n\n"
            "📱 شماره موبایلت رو بگو (مثلاً 09121234567):"
        )

    def get_welcome_text(self, name: str = "کاربر") -> str:
        return (
            f"سلام {name} جان! 👋\n\n"
            f"من {self.BOT_NAME} هستم 🤖 حسابدار شخصی شما\n"
            "هر وقت نیاز به ثبت سند داری، بهم بگو.\n\n"
            "📝 مثال:\n"
            "• خرید ۱۰۰ عدد خودکار ۵۰۰۰ تومان از شرکت آذر\n"
            "• علی کریمی ۵۰۰ هزار تومان پول زد\n"
            "• پرداخت به شرکت آذر ۲۰۰ هزار تومان\n"
            "• مانده حساب علی کریمی\n\n"
            "🎤 می‌تونی ویس هم بفرستی!\n"
            "📊 /report برای گزارش\n"
            "📋 /help برای راهنما"
        )

    def get_help_text(self) -> str:
        return (
            f"📋 راهنمای {self.BOT_NAME}\n\n"
            "/start - شروع مجدد\n"
            "/report - دریافت گزارش PDF\n"
            "/status - وضعیت اشتراک\n"
            "/pricing - قیمت پلن‌ها\n"
            "/help - این راهنما\n\n"
            "📝 ثبت سند با متن:\n"
            "• خرید ۱۰۰ عدد خودکار ۵۰۰۰ تومان\n"
            "• فروش ۵۰ عدد کتاب ۲۰۰۰۰ تومان\n"
            "• علی کریمی ۵۰۰ هزار تومان پول زد\n"
            "• پرداخت به شرکت آذر ۲۰۰ هزار تومان\n"
            "• مانده حساب علی کریمی\n"
            "• پرداخت اجاره مغازه ۱۰ میلیون تومان\n\n"
            "🎤 ثبت سند با ویس:\n"
            "یک ویس بفرست. خودم تشخیص می‌دم."
        )

    def handle_onboarding_mobile(self, chat_id: Any, user_states: Dict,
                                 text: str, platform: str = "telegram",
                                 platform_user_id: Optional[str] = None) -> Optional[str]:
        """پردازش شماره موبایل در مرحله onboarding.
        state_name نام state ذخیره‌شده برای این مرحله است.
        معمولاً 'onboarding_mobile_link'
        اگر ثبت‌نام کامل شد اسم کاربر را برمی‌گرداند."""
        mobile = self.normalize_mobile(text)
        if not re.match(r'^09\d{9}$', mobile):
            self.send_message(chat_id, "شماره موبایل معتبر نیست. لطفاً به شکل 09121234567 وارد کن:")
            return None

        otp_result = self.auth_manager.request_otp(mobile)
        if not otp_result.get("success"):
            self.send_message(chat_id, f"❌ {otp_result.get('message')}")
            return None

        user_states[chat_id] = {
            "state": "onboarding_otp",
            "reg_mobile": mobile,
            "platform": platform,
            "platform_user_id": platform_user_id,
            "name_hint": "",
        }

        if otp_result.get("dev_code"):
            # حالت توسعه: کد رو نشون بده
            self.send_message(chat_id, f"🔐 کد تایید (توسعه): {otp_result['dev_code']}\nلطفاً کد ۶ رقمی را وارد کنید:")
        else:
            self.send_message(chat_id, "✅ کد تایید ۶ رقمی به شماره شما ارسال شد.\nلطفاً کد را وارد کنید:")

        return None

    def handle_onboarding_otp(self, chat_id: Any, user_states: Dict, text: str) -> bool:
        """پردازش کد OTP در مرحله onboarding. اگر موفق بود True برمی‌گرداند."""
        st = user_states.get(chat_id, {})
        mobile = st.get("reg_mobile", "")
        if not mobile:
            self.send_message(chat_id, "خطا: دوباره /start را بزنید.")
            return False

        code = text.strip()
        result = self.auth_manager.verify_otp(mobile, code)

        if not result.get("success"):
            self.send_message(chat_id, f"❌ {result.get('message')}")
            return False

        # اتصال حساب پیام‌رسان
        platform = st.get("platform", "telegram")
        platform_user_id = st.get("platform_user_id")
        user_id = result["user_id"]

        if platform == "telegram" and platform_user_id:
            self.auth_manager.link_telegram(user_id, platform_user_id)
        elif platform == "bale" and platform_user_id:
            self.auth_manager.link_bale(user_id, platform_user_id)

        del user_states[chat_id]
        name = st.get("name_hint") or result.get("name", "")
        self.send_message(chat_id, self.get_welcome_text(name or "کاربر"))
        return True

    def process_text_command(self, text: str, user_id: int) -> Dict:
        """پردازش متن به عنوان سند حسابداری (ابتدا قانون‌محور، سپس AI)."""
        result = self.text_handler.parse_and_create_voucher(text, user_id=user_id)
        if not result.get("success"):
            from core.ai_voucher_fallback import try_ai_voucher
            ai_result = try_ai_voucher(self.engine, text, user_id)
            if ai_result.get("success"):
                return ai_result
        return result
