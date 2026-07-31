# bot_handlers/bale_bot.py

import os
import re
import time
from core.logging_config import setup_logging
setup_logging()

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from core.accounting_engine import AccountingEngine
from core.text_command_handler import TextCommandHandler
from core.smart_dialog_engine import SmartDialogEngine
from ai_handlers.voice_to_accounting import VoiceToAccounting

# توجه: برای بله از کتابخانه requests استفاده می‌کنیم (API ساده)
import requests
import json
from typing import List, Optional, Dict, Any

from core.auth import AuthManager
from core.notifications import NotificationService
from core.license_manager import LicenseManager
from ai_handlers.llm_processor import LLMProcessor
from config import BALE_TOKEN, get_public_app_url
from bot_handlers.base_bot import BaseBot
BOT_NAME = "نارین"
BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/"

class BaleBot(BaseBot):
    def __init__(self) -> None:
        super().__init__()
        os.makedirs("voice_files", exist_ok=True)
        self.last_update_id = 0
        self.user_states: Dict[int, dict] = {}

    def _normalize_mobile(self, raw: str) -> str:
        persian_digits = "۰۱۲۳۴۵۶۷۸۹"
        arabic_digits = "٠١٢٣٤٥٦٧٨٩"
        out = []
        for ch in raw.strip():
            if ch in persian_digits:
                out.append(str(persian_digits.index(ch)))
            elif ch in arabic_digits:
                out.append(str(arabic_digits.index(ch)))
            elif ch.isdigit():
                out.append(ch)
        digits = "".join(out)
        if digits.startswith("98") and len(digits) == 12:
            digits = "0" + digits[2:]
        elif digits.startswith("9") and len(digits) == 10:
            digits = "0" + digits
        return digits

    def _normalize_business_type(self, raw: str) -> str:
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

    def start_onboarding(self, chat_id: int) -> None:
        self.user_states[chat_id] = {"state": "onboarding_mobile_link"}
        self.send_message(
            chat_id,
            "سلام! 👋 من نارین هستم 🤖\n"
            "حسابدار شخصی و هوشمند شما\n\n"
            "هنوز حساب بله‌ت رو به نارین وصل نکردی. اگه قبلاً از وب‌اپ یا تلگرام ثبت‌نام کرده باشی،\n"
            "با وارد کردن همون شماره موبایل، مستقیم به همون حساب وصل می‌شی - نیازی به ثبت‌نام دوباره نیست.\n\n"
            "📱 شماره موبایلت رو بگو (مثلاً 09121234567):"
        )

    def handle_onboarding(self, chat_id: int, text: str) -> None:
        st = self.user_states.get(chat_id, {})
        state = st.get("state")

        if state == "onboarding_mobile_link":
            mobile = self._normalize_mobile(text)
            if not re.match(r'^09\d{9}$', mobile):
                self.send_message(chat_id, "شماره موبایل معتبر نیست. لطفاً به شکل 09121234567 وارد کن:")
                return
            otp_result = self.auth_manager.request_otp(mobile)
            if not otp_result.get("success"):
                self.send_message(chat_id, f"❌ {otp_result.get('message')}")
                return
            st["reg_mobile"] = mobile
            st["state"] = "onboarding_otp_link"
            dev_code = otp_result.get("dev_code")
            msg = f"یک کد تایید ۶ رقمی به شماره {mobile} پیامک شد. لطفاً همون کد رو بفرست:"
            if dev_code:
                msg += f"\n\n(حالت تست، چون پیامک واقعی وصل نیست: {dev_code})"
            self.send_message(chat_id, msg)

        elif state == "onboarding_otp_link":
            code = "".join(ch for ch in text if ch.isdigit())
            mobile = st.get("reg_mobile", "")
            verify_result = self.auth_manager.verify_otp(mobile, code)
            if not verify_result.get("success"):
                self.send_message(chat_id, f"❌ {verify_result.get('message')}\nدوباره کد رو بفرست، یا با /start از اول شروع کن.")
                return
            linked_user_id = verify_result["user_id"]
            link_result = self.auth_manager.link_bale(linked_user_id, str(chat_id))
            if not link_result.get("success"):
                self.send_message(chat_id, f"❌ {link_result.get('message')}")
                self.user_states.pop(chat_id, None)
                return
            if not verify_result.get("is_new"):
                profile = self.auth_manager.get_user_profile(linked_user_id) or {}
                self.user_states.pop(chat_id, None)
                self.send_message(
                    chat_id,
                    f"✅ وصل شد! خوش اومدی {profile.get('name') or ''} جان 👋\n\n"
                    f"کسب و کار: {profile.get('business_name') or '-'}\n\n"
                    "حساب بله‌ت به همون حساب قبلیت وصل شد. هر سندی داری بگو!"
                )
                return
            st["reg_mobile"] = mobile
            st["state"] = "onboarding_name"
            self.send_message(chat_id, "خب، حساب جدیدی برات می‌سازم!\n\n❓ لطفاً نام و نام خانوادگی خودت رو بگو:")

        elif state == "onboarding_name":
            st["reg_name"] = text.strip()
            st["state"] = "onboarding_business_type"
            self.send_message(
                chat_id,
                f"خوشحالم {st['reg_name']} جان! 😊\n\n"
                "کسب و کارت تو چه زمینه‌ایه؟\n"
                "مثلاً: بازرگانی عمومی، آهن‌آلات، آرایشگاهی، مواد غذایی، پوشاک، خدمات"
            )

        elif state == "onboarding_business_type":
            st["reg_business_type"] = self._normalize_business_type(text)
            st["state"] = "onboarding_business_name"
            self.send_message(chat_id, "عالیه! اسم کسب و کارت چیه؟\nمثلاً: البرز فلز، شرکت آذر، فروشگاه بهار")

        elif state == "onboarding_business_name":
            biz_type = st.get("reg_business_type", "بازرگانی عمومی")
            biz_name = text.strip()
            user_id = self.auth_manager.get_user_by_bale(str(chat_id))
            self.auth_manager.update_user_profile(user_id, business_type=biz_type, business_name=biz_name)
            self.user_states.pop(chat_id, None)
            self.send_message(
                chat_id,
                f"✅ اطلاعات کسب و کارت ذخیره شد!\n"
                f"نوع: {biz_type}\n"
                f"نام: {biz_name}\n\n"
                "حالا می‌تونیم شروع کنیم. هر سندی داری بگو!"
            )
    
    def send_message(self, chat_id: int, text: str, reply_markup: Optional[dict] = None) -> Optional[dict]:
        """ارسال پیام به کاربر"""
        url = BASE_URL + "sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(url, json=payload)
            return response.json()
        except Exception as e:
            print(f"خطا در ارسال پیام: {e}")
            return None

    def send_app_button(self, chat_id: int, text: str) -> Optional[dict]:
        """ارسال پیام همراه با دکمه‌ای که مینی‌اپ (وب‌اپ نارین) را باز می‌کند"""
        reply_markup = {
            "inline_keyboard": [[
                {"text": "📱 برنامه نارین", "web_app": {"url": f"{get_public_app_url()}/app"}}
            ]]
        }
        return self.send_message(chat_id, text, reply_markup=reply_markup)
    
    def send_document(self, chat_id: int, file_path: str) -> Optional[dict]:
        """ارسال فایل PDF به کاربر"""
        url = BASE_URL + "sendDocument"
        try:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': chat_id}
                response = requests.post(url, files=files, data=data)
            return response.json()
        except Exception as e:
            print(f"خطا در ارسال فایل: {e}")
            return None
    
    def download_file(self, file_id: str, save_path: str) -> bool:
        """دانلود فایل صوتی از بله"""
        url = BASE_URL + "getFile"
        payload = {"file_id": file_id}
        try:
            response = requests.post(url, json=payload)
            file_path = response.json().get('result', {}).get('file_path')
            if file_path:
                file_url = f"https://tapi.bale.ai/file/bot{BALE_TOKEN}/{file_path}"
                file_response = requests.get(file_url)
                with open(save_path, 'wb') as f:
                    f.write(file_response.content)
                return True
        except Exception as e:
            print(f"خطا در دانلود فایل: {e}")
        return False
    
    def handle_voice(self, chat_id: int, file_id: int, message_id: int) -> None:
        """پردازش ویس دریافتی"""
        user_id = self.auth_manager.get_user_by_bale(str(chat_id))
        if not user_id:
            self.send_message(chat_id, "به نظر میاد هنوز ثبت نام نکردی.\nبرای شروع /start رو بزن.")
            return
        self.send_message(chat_id, "🎤 در حال پردازش ویس شما...")

        file_path = f"voice_files/bale_{message_id}.ogg"
        if self.download_file(file_id, file_path):
            try:
                data, transcript = self.voice_handler.voice_to_voucher(file_path)

                amount = data.get("amount", 0)
                if data["type"] and amount >= 1000:
                    lic = self.license_manager.can_create_voucher(user_id)
                    if not lic.get("allowed", True):
                        self.send_message(chat_id, f"❌ {lic.get('message', 'محدودیت مجوز')}")
                        return
                    entry_id = self.engine.create_voucher(
                        date=datetime.now(),
                        description=data["description"],
                        lines=[
                            (data["debit_account"], amount, 'debit'),
                            (data["credit_account"], amount, 'credit')
                        ]
                    )
                    self.send_message(
                        chat_id,
                        f"✅ سند شماره {entry_id} ثبت شد.\n\n"
                        f"💰 مبلغ: {amount:,} تومان\n"
                        f"📝 شرح: {data['description'][:100]}"
                    )
                else:
                    from core.ai_voucher_fallback import try_ai_voucher
                    ai_result = try_ai_voucher(self.engine, transcript, user_id)
                    if ai_result.get("success"):
                        self.send_message(
                            chat_id,
                            f"✅ سند شماره {ai_result['entry_id']} ثبت شد.\n\n"
                            f"💰 مبلغ: {ai_result['amount']:,.0f} تومان\n"
                            f"📝 شرح: {ai_result['description'][:100]}"
                        )
                    else:
                        self.send_message(
                            chat_id,
                            "مبلغ تشخیص داده نشد. لطفاً مبلغ رو به تومان بگو.\n"
                            "مثال: خرید ۱۰۰ خودکار ۵۰۰۰ تومان"
                        )
            except Exception as e:
                self.send_message(chat_id, f"❌ خطا در پردازش ویس")
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            self.send_message(chat_id, "❌ خطا در دانلود فایل صوتی")
    
    def handle_text(self, chat_id: int, text: str) -> None:
        """پردازش متن دریافتی"""
        if chat_id in self.user_states and not text.startswith("/"):
            self.handle_onboarding(chat_id, text)
            return

        # بررسی دستورات خاص
        if text == "/start":
            user_id = self.auth_manager.get_user_by_bale(str(chat_id))
            if user_id:
                self.send_app_button(
                    chat_id,
                    f"🤖 به {BOT_NAME}، حسابدار هوشمند خوش آمدید!\n\n"
                    "🎤 قابلیت‌ها:\n"
                    "• ارسال ویس برای ثبت خودکار سند\n"
                    "• تایپ متن ساده\n"
                    "• برنامه اختصاصی (دکمه پایین یا دستور /app)\n"
                    "• دریافت گزارش PDF\n\n"
                    "📝 مثال ویس: 'خرید 100 عدد خودکار 5000 تومان'\n"
                    "📝 مثال متن: 'فروش 50 عدد کتاب 20000 تومان'\n"
                    "📊 دستور /report برای دریافت گزارش\n"
                    "📋 دستور /help برای راهنما"
                )
            else:
                self.start_onboarding(chat_id)
        elif text == "/help":
            self.send_message(
                chat_id,
                "📋 راهنمای دستورات:\n\n"
                "/start - شروع مجدد\n"
                "/report - دریافت گزارش PDF تراز آزمایشی\n"
                "/status - وضعیت اشتراک\n"
                "/pricing - قیمت پلن‌ها\n"
                "/help - نمایش این راهنما\n"
                "/app - برنامه اختصاصی\n\n"
                "📝 ثبت سند با متن:\n"
                "• خرید 100 عدد خودکار 5000 تومان\n"
                "• فروش 50 عدد کتاب 20000 تومان\n"
                "• پرداخت به شرکت آذر 1000000 تومان\n"
                "• دریافت از علی کریمی 500000 تومان\n\n"
                "🎤 ثبت سند با ویس:\n"
                "فقط کافی است یک ویس بفرستید.\n\n"
                "💡 ثبت هوشمند:\n"
                "• مشتری علی کریمی 500 هزار تومان پول زد\n"
                "• پرداخت به شرکت آذر 200 هزار تومان\n"
                "• مانده حساب علی کریمی"
            )
        elif text == "/app":
            self.send_app_button(chat_id, "برای باز کردن برنامه نارین، روی دکمه پایین بزنید:")
        elif text == "/status":
            user_id = self.auth_manager.get_user_by_bale(str(chat_id))
            if user_id:
                self.handle_status(chat_id, user_id)
            else:
                self.send_message(chat_id, "اول /start رو بزن.")
        elif text == "/pricing":
            self.handle_pricing(chat_id)
        elif text == "/report":
            user_id = self.auth_manager.get_user_by_bale(str(chat_id))
            if not user_id:
                self.send_message(chat_id, "اول /start رو بزن تا ثبت نام کنی.")
                return
            self.send_message(chat_id, "📊 در حال تولید گزارش...")
            try:
                from reports.pdf_generator import PDFReportGenerator
                reporter = PDFReportGenerator(self.engine)
                pdf_file = reporter.create_trial_balance_pdf(f"temp_report_{user_id}.pdf", user_id)
                self.send_document(chat_id, pdf_file)
                os.remove(pdf_file)
            except Exception as e:
                self.send_message(chat_id, f"❌ خطا در تولید گزارش")
        else:
            user_id = self.auth_manager.get_user_by_bale(str(chat_id))
            if not user_id:
                self.send_message(chat_id, "به نظر میاد هنوز ثبت نام نکردی.\nبرای شروع /start رو بزن.")
                return

            # بررسی کامل بودن پروفایل
            profile = self.auth_manager.get_user_profile(user_id)
            if profile and (not profile["business_type"] or not profile["business_name"]):
                self.send_message(chat_id, "هنوز اطلاعات کسب و کارت رو ثبت نکردی!\nکسب و کارت تو چه زمینه‌ایه؟\nمثلاً: بازرگانی عمومی، آهن‌آلات، آرایشگاهی")
                self.user_states[chat_id] = {"state": "onboarding_business_type", "reg_mobile": profile.get("mobile", "")}
                return

            # تشخیص درخواست اطلاعات من
            profile_keywords = ["کسب", "کارم", "شغل", "پروفایل", "اطلاعات", "لوگو", "شماره",
                               "تلفن", "شناسه", "اقتصادی", "آدرس", "دفتر", "همراه",
                               "اطلاعات من", "پروفایل من"]
            if any(k in text for k in profile_keywords):
                if profile:
                    msg = (
                        f"📋 {profile.get('name', 'کاربر')} جان\n\n"
                        f"🏢 {profile.get('business_name', '') or 'نامشخص'} ({profile.get('business_type', '') or 'نامشخص'})\n\n"
                    )
                    if profile.get("phone_office"): msg += f"📞 دفتر: {profile['phone_office']}\n"
                    if profile.get("phone_mobile"): msg += f"📱 همراه: {profile['phone_mobile']}\n"
                    if profile.get("national_id"): msg += f"🆔 ملی: {profile['national_id']}\n"
                    if profile.get("economic_code"): msg += f"💰 اقتصادی: {profile['economic_code']}\n"
                    if profile.get("address"): msg += f"📍 آدرس: {profile['address']}\n"
                    msg += "\nبرای ویرایش، هر کدوم رو به این شکل بفرست:\n"
                    msg += "تلفن دفتر: ۰۲۱۱۲۳۴۵۶۷۸\n"
                    msg += "تلفن همراه: ۰۹۱۲۳۴۵۶۷۸۹\n"
                    msg += "شناسه ملی: ۱۲۳۴۵۶۷۸۹۰\n"
                    msg += "کد اقتصادی: ۱۲۳۴۵۶۷۸۹۰"
                    self.send_message(chat_id, msg)
                return

            # تشخیص سلام و احوالپرسی
            greetings = ["سلام", "علیک", "درود", "خوبی", "hi", "hello", "سلا", "مرسی", "ممنون", "چطوری", "خوبم"]
            if any(g in text for g in greetings) and not any(k in text for k in ["خرید", "فروش", "پرداخت", "دریافت", "پول", "هزار", "میلیون", "تومان"]):
                self.send_message(
                    chat_id,
                    f"سلام! {BOT_NAME} هستم 🤖 حسابدار شخصی شما\n"
                    "هر کاری داری بگو. می‌تونم:\n\n"
                    "📝 ثبت سند حسابداری\n"
                    "💰 مانده حساب مشتریان\n"
                    "📊 گزارش بگیرم\n"
                    "🎤 ویس تو بفهمم\n\n"
                    "چطور می‌تونم کمکت کنم؟"
                )
                return

            # پردازش با LLM اول
            result = None
            try:
                result = self.llm.process(text)
            except Exception:
                pass

            if result and result.get("success"):
                amount = result.get("amount", 0)
                if amount < 1000:
                    self.send_message(chat_id, "مبلغ تشخیص داده نشد یا خیلی کمه.\nلطفاً مبلغ رو به تومان بگو:\nمثلاً: خرید ۱۰۰ خودکار ۵۰۰۰ تومان")
                    return
                lic = self.license_manager.can_create_voucher(user_id)
                if not lic.get("allowed", True):
                    self.send_message(chat_id, f"❌ {lic.get('message', 'محدودیت مجوز')}")
                    return
                entry_id = self.engine.create_voucher(
                    date=datetime.now(),
                    description=result["description"],
                    lines=[
                        (result["debit_account"], amount, 'debit'),
                        (result["credit_account"], amount, 'credit')
                    ]
                )
                self.send_message(
                    chat_id,
                    f"✅ سند شماره {entry_id} ثبت شد.\n"
                    f"💰 مبلغ: {amount:,} تومان\n"
                    f"📝 شرح: {result['description'][:100]}"
                )
            elif result and result.get("type") == "general":
                self.send_message(chat_id, result["message"])
            else:
                # Fallback به موتور هوشمند و rule-based
                response = self.smart_dialog.process_message(user_id, text)
                if "متوجه نشدم" in response:
                    fb = self.text_handler.parse_and_create_voucher(text, user_id=user_id)
                    if not fb.get("success"):
                        from core.ai_voucher_fallback import try_ai_voucher
                        ai_result = try_ai_voucher(self.engine, text, user_id)
                        if ai_result.get("success"):
                            fb = ai_result
                    self.send_message(chat_id, fb["message"])
                else:
                    self.send_message(chat_id, response)

            self.send_notification_if_needed(chat_id, user_id)
    
    def send_notification_if_needed(self, chat_id: int, user_id: int):
        msg = self.notifier.check_renewal_reminder(user_id)
        if msg:
            self.send_message(chat_id, msg)
        limit_msg = self.notifier.get_voucher_limit_warning(user_id)
        if limit_msg:
            self.send_message(chat_id, limit_msg)
        inventory_msg = self.notifier.get_inventory_deficit_reminder(user_id)
        if inventory_msg:
            self.send_message(chat_id, inventory_msg)

    def handle_status(self, chat_id: int, user_id: int):
        status = self.license_manager.check_license(user_id)
        if status["is_valid"]:
            msg = (
                f"وضعیت اشتراک:\n"
                f"پلن: {status.get('plan_type', 'آزمایشی')}\n"
                f"روزهای باقی مانده: {status.get('days_left', 0)}\n"
                f"اسناد: {status.get('used_vouchers', 0)}"
            )
            if status.get("max_vouchers", 0) > 0:
                msg += f" از {status['max_vouchers']}"
            self.send_message(chat_id, msg)
        else:
            self.send_message(chat_id, status.get("message", "اشتراک شما منقضی شده است."))

    def handle_pricing(self, chat_id: int):
        self.send_message(chat_id, self.license_manager.get_pricing_message())

    def get_updates(self) -> List[dict]:
        """دریافت پیام‌های جدید از سرور بله"""
        url = BASE_URL + "getUpdates"
        payload = {
            "offset": self.last_update_id + 1,
            "timeout": 30
        }
        try:
            response = requests.post(url, json=payload, timeout=35)
            return response.json().get('result', [])
        except Exception as e:
            print(f"خطا در دریافت آپدیت: {e}")
            return []
    
    def run(self) -> None:
        """حلقه اصلی ربات"""
        print("✅ ربات بله روشن شد...")
        print("ربات در حال اجراست. برای تست به ربات در بله پیام بدهید.")
        pool = ThreadPoolExecutor(max_workers=10)
        
        while True:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.last_update_id = update.get('update_id', self.last_update_id)
                    
                    message = update.get('message', {})
                    chat_id = message.get('chat', {}).get('id')
                    
                    if not chat_id:
                        continue
                    
                    if 'voice' in message:
                        file_id = message['voice'].get('file_id')
                        message_id = message.get('message_id')
                        pool.submit(self.handle_voice, chat_id, file_id, message_id)
                    elif 'text' in message:
                        text = message['text']
                        pool.submit(self.handle_text, chat_id, text)

                time.sleep(1)
            except KeyboardInterrupt:
                print("\n👋 ربات متوقف شد.")
                pool.shutdown(wait=False)
                break
            except Exception as e:
                print(f"خطا: {e}")
                time.sleep(5)


if __name__ == "__main__":
    bot = BaleBot()
    bot.run()