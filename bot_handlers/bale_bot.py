# bot_handlers/bale_bot.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_config import setup_logging
setup_logging()

import asyncio
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
from config import BALE_TOKEN
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
    
    def send_message(self, chat_id: int, text: str) -> Optional[dict]:
        """ارسال پیام به کاربر"""
        url = BASE_URL + "sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload)
            return response.json()
        except Exception as e:
            print(f"خطا در ارسال پیام: {e}")
            return None
    
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
                        ]
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
        # بررسی دستورات خاص
        if text == "/start":
            self.send_message(
                chat_id,
                "🤖 به ربات حسابداری هوشمند خوش آمدید!\n\n"
                "🎤 قابلیت‌ها:\n"
                "• ارسال ویس برای ثبت خودکار سند\n"
                "• تایپ متن ساده\n"
                "• برنامه اختصاصی (دستور /app)\n"
                "• دریافت گزارش PDF\n\n"
                "📝 مثال ویس: 'خرید 100 عدد خودکار 5000 تومان'\n"
                "📝 مثال متن: 'فروش 50 عدد کتاب 20000 تومان'\n"
                "📊 دستور /report برای دریافت گزارش\n"
                "📋 دستور /help برای راهنما"
            )
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
            self.send_message(chat_id, "برنامه حسابدار هوشمند:\nhttps://localhost:8000/app")
        elif text == "/report":
            self.send_message(chat_id, "📊 در حال تولید گزارش...")
            try:
                from reports.pdf_generator import PDFReportGenerator
                reporter = PDFReportGenerator(self.engine)
                pdf_file = reporter.create_trial_balance_pdf("temp_report.pdf")
                self.send_document(chat_id, pdf_file)
            except Exception as e:
                self.send_message(chat_id, f"❌ خطا در تولید گزارش: {str(e)}")
        else:
            # ابتدا سعی می‌کنیم با موتور هوشمند پردازش کنیم
            response = self.smart_dialog.process_message(chat_id, text)
            if "متوجه نشدم" in response:
                # اگر موتور هوشمند نفهمید، از موتور متنی استفاده کن
                result = self.text_handler.parse_and_create_voucher(text)
                self.send_message(chat_id, result["message"])
            else:
                self.send_message(chat_id, response)
            user_id = self.auth_manager.get_user_by_bale(str(chat_id))
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
                    
                    # بررسی نوع پیام
                    if 'voice' in message:
                        file_id = message['voice'].get('file_id')
                        message_id = message.get('message_id')
                        self.handle_voice(chat_id, file_id, message_id)
                    elif 'text' in message:
                        text = message['text']
                        self.handle_text(chat_id, text)
                
                asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n👋 ربات متوقف شد.")
                break
            except Exception as e:
                print(f"خطا: {e}")
                asyncio.sleep(5)


if __name__ == "__main__":
    bot = BaleBot()
    bot.run()