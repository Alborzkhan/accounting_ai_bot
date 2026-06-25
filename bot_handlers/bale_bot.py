# bot_handlers/bale_bot.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_config import setup_logging
setup_logging()

import re
import threading
import time
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
from config import BALE_TOKEN, get_public_app_url
BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}/"

class BaleBot:
    def __init__(self) -> None:
        self.engine = AccountingEngine()
        self.text_handler = TextCommandHandler(self.engine)
        self.smart_dialog = SmartDialogEngine(self.engine)
        self.voice_handler = VoiceToAccounting(model_size="base")
        self.auth_manager = AuthManager()
        self.notifier = NotificationService()
        self.license_manager = LicenseManager()
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
        self.user_states[chat_id] = {"state": "onboarding_name"}
        self.send_message(
            chat_id,
            "سلام! 👋 من نارین هستم 🤖\n"
            "حسابدار شخصی و هوشمند شما\n\n"
            "به نظر میاد اولین باره که با من کار می‌کنی.\n"
            "بیا اول ثبت نامت رو تکمیل کنیم.\n\n"
            "❓ لطفاً نام و نام خانوادگی خودت رو بگو:"
        )

    def handle_onboarding(self, chat_id: int, text: str) -> None:
        st = self.user_states.get(chat_id, {})
        state = st.get("state")

        if state == "onboarding_name":
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
            st["reg_business_name"] = text.strip()
            st["state"] = "onboarding_mobile"
            self.send_message(
                chat_id,
                "تقریباً تمومه! یه چیز مهم بمونه:\n\n"
                "📱 شماره موبایل واقعیت رو بگو (مثلاً 09121234567).\n"
                "اینجوری اگه از تلگرام، بله یا وب‌اپ هم وارد بشی، حساب کاریت همینه و اطلاعاتت یکیه."
            )

        elif state == "onboarding_mobile":
            mobile = self._normalize_mobile(text)
            if not re.match(r'^09\d{9}$', mobile):
                self.send_message(chat_id, "شماره موبایل معتبر نیست. لطفاً به شکل 09121234567 وارد کن:")
                return
            otp_result = self.auth_manager.request_otp(mobile)
            if not otp_result.get("success"):
                self.send_message(chat_id, f"❌ {otp_result.get('message')}")
                return
            st["reg_mobile"] = mobile
            st["state"] = "onboarding_otp"
            dev_code = otp_result.get("dev_code")
            msg = f"یک کد تایید ۶ رقمی به شماره {mobile} پیامک شد. لطفاً همون کد رو بفرست:"
            if dev_code:
                msg += f"\n\n(حالت تست، چون پیامک واقعی وصل نیست: {dev_code})"
            self.send_message(chat_id, msg)

        elif state == "onboarding_otp":
            code = "".join(ch for ch in text if ch.isdigit())
            mobile = st.get("reg_mobile", "")
            name = st.get("reg_name", "کاربر")
            biz_type = st.get("reg_business_type", "بازرگانی عمومی")
            biz_name = st.get("reg_business_name", "")
            verify_result = self.auth_manager.verify_otp(mobile, code, name)
            if not verify_result.get("success"):
                self.send_message(chat_id, f"❌ {verify_result.get('message')}\nدوباره کد رو بفرست، یا با /start از اول شروع کن.")
                return
            user_id = verify_result["user_id"]
            link_result = self.auth_manager.link_bale(user_id, str(chat_id))
            if not link_result.get("success"):
                self.send_message(chat_id, f"❌ {link_result.get('message')}")
                self.user_states.pop(chat_id, None)
                return
            self.auth_manager.update_user_profile(user_id, business_type=biz_type, business_name=biz_name)
            self.license_manager.generate_license_key(user_id, "free_trial")
            self.user_states.pop(chat_id, None)
            self.send_message(
                chat_id,
                f"✅ ثبت نام با موفقیت انجام شد!\n\n"
                f"📋 خلاصه اطلاعات:\n"
                f"نام: {name}\n"
                f"موبایل: {mobile}\n"
                f"کسب و کار: {biz_name} ({biz_type})\n\n"
                f"یک لایسنس آزمایشی ۵۰ سندی برات فعال کردم.\n"
                f"حالا می‌تونیم شروع کنیم!\n\n"
                "💡 نکته: همین شماره موبایل رو می‌تونی برای ورود به وب‌اپ یا تلگرام هم استفاده کنی، حساب همینه."
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
                file_url = f"https://tapi.bale.ai/file/bot{TOKEN}/{file_path}"
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

                if data["type"] and data["amount"] > 0:
                    entry_id = self.engine.create_voucher(
                        date=datetime.now(),
                        description=data["description"],
                        lines=[
                            (data["debit_account"], data["amount"], 'debit'),
                            (data["credit_account"], data["amount"], 'credit')
                        ],
                        user_id=user_id
                    )
                    self.send_message(
                        chat_id,
                        f"✅ سند شماره {entry_id} با موفقیت ثبت شد.\n\n"
                        f"💰 مبلغ: {data['amount']:,} تومان\n"
                        f"📝 شرح: {data['description'][:100]}\n"
                        f"📊 بدهکار: {data['debit_account']}\n"
                        f"📊 بستانکار: {data['credit_account']}"
                    )
                else:
                    from core.ai_voucher_fallback import try_ai_voucher
                    ai_result = try_ai_voucher(self.engine, transcript, user_id)
                    if ai_result.get("success"):
                        self.send_message(
                            chat_id,
                            f"✅ سند شماره {ai_result['entry_id']} با موفقیت ثبت شد. (تشخیص با هوش مصنوعی)\n\n"
                            f"💰 مبلغ: {ai_result['amount']:,.0f} تومان\n"
                            f"📝 شرح: {ai_result['description'][:100]}\n"
                            f"📊 بدهکار: {ai_result['debit_account']}\n"
                            f"📊 بستانکار: {ai_result['credit_account']}"
                        )
                    else:
                        self.send_message(
                            chat_id,
                            "⚠️ اطلاعات ناقص است. لطفاً واضح‌تر صحبت کنید.\n\n"
                            "مثال: 'خرید 100 عدد خودکار 5000 تومان'"
                        )
            except Exception as e:
                self.send_message(chat_id, f"❌ خطا در پردازش ویس: {str(e)}")
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
                    "🤖 به نارین، حسابدار هوشمند خوش آمدید!\n\n"
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
                "/help - نمایش این راهنما\n\n"
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
                self.send_message(chat_id, f"❌ خطا در تولید گزارش: {str(e)}")
        else:
            user_id = self.auth_manager.get_user_by_bale(str(chat_id))
            if not user_id:
                self.send_message(chat_id, "به نظر میاد هنوز ثبت نام نکردی.\nبرای شروع /start رو بزن.")
                return
            # ابتدا سعی می‌کنیم با موتور هوشمند پردازش کنیم
            response = self.smart_dialog.process_message(user_id, text)
            if "متوجه نشدم" in response:
                # اگر موتور هوشمند نفهمید، از موتور متنی استفاده کن
                result = self.text_handler.parse_and_create_voucher(text, user_id=user_id)
                if not result["success"]:
                    from core.ai_voucher_fallback import try_ai_voucher
                    ai_result = try_ai_voucher(self.engine, text, user_id)
                    if ai_result.get("success"):
                        result = ai_result
                self.send_message(chat_id, result["message"])
            else:
                self.send_message(chat_id, response)
            if user_id:
                self.send_notification_if_needed(chat_id, user_id)
    
    def send_notification_if_needed(self, chat_id: int, user_id: int):
        msg = self.notifier.check_renewal_reminder(user_id)
        if msg:
            self.send_message(chat_id, msg)
        limit_msg = self.notifier.get_voucher_limit_warning(user_id)
        if limit_msg:
            self.send_message(chat_id, limit_msg)

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
        
        while True:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.last_update_id = update.get('update_id', self.last_update_id)
                    
                    message = update.get('message', {})
                    chat_id = message.get('chat', {}).get('id')
                    
                    if not chat_id:
                        continue
                    
                    # بررسی نوع پیام - هرکدام در ترد جدا، تا پردازش ویس (که چند ثانیه طول می‌کشد)
                    # بقیه‌ی کاربران را پشت صف نگه ندارد
                    if 'voice' in message:
                        file_id = message['voice'].get('file_id')
                        message_id = message.get('message_id')
                        threading.Thread(target=self.handle_voice, args=(chat_id, file_id, message_id), daemon=True).start()
                    elif 'text' in message:
                        text = message['text']
                        threading.Thread(target=self.handle_text, args=(chat_id, text), daemon=True).start()

                time.sleep(1)
            except KeyboardInterrupt:
                print("\n👋 ربات متوقف شد.")
                break
            except Exception as e:
                print(f"خطا: {e}")
                time.sleep(5)


if __name__ == "__main__":
    bot = BaleBot()
    bot.run()