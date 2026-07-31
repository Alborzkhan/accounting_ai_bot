import os
import re
import re

from core.logging_config import setup_logging
setup_logging()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from core.accounting_engine import AccountingEngine
from core.text_command_handler import TextCommandHandler
from core.smart_dialog_engine import SmartDialogEngine
from ai_handlers.voice_to_accounting import VoiceToAccounting
from datetime import datetime
import asyncio

from core.auth import AuthManager
from core.notifications import NotificationService
from core.license_manager import LicenseManager
from ai_handlers.llm_processor import LLMProcessor
from config import TELEGRAM_TOKEN, get_public_app_url
from bot_handlers.base_bot import BaseBot

BOT_NAME = "نارین"

class TelegramBot(BaseBot):
    def __init__(self) -> None:
        super().__init__()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = str(update.effective_user.id)
        user_id = self.auth_manager.get_user_by_telegram(telegram_id)
        context.user_data["state"] = None

        if user_id:
            user = update.effective_user
            name = user.full_name or "کاربر"
            await update.message.reply_text(
                f"سلام {name} جان! 👋\n\n"
                f"من {BOT_NAME} هستم 🤖 حسابدار شخصی شما\n"
                "هر وقت نیاز به ثبت سند داری، بهم بگو.\n\n"
                "📝 مثال:\n"
                "• خرید ۱۰۰ عدد خودکار ۵۰۰۰ تومان از شرکت آذر\n"
                "• علی کریمی ۵۰۰ هزار تومان پول زد\n"
                "• پرداخت به شرکت آذر ۲۰۰ هزار تومان\n"
                "• مانده حساب علی کریمی\n\n"
                "🎤 می‌تونی ویس هم بفرستی!\n"
                "📊 /report برای گزارش\n"
                "📋 /help برای راهنما\n"
                "📱 /app برای برنامه"
            )
        else:
            await update.message.reply_text(
                f"سلام! 👋 من {BOT_NAME} هستم 🤖\n"
                "حسابدار شخصی و هوشمند شما\n\n"
                "هنوز حساب تلگرامت رو به نارین وصل نکردی. اگه قبلاً از وب‌اپ یا بله ثبت‌نام کرده باشی،\n"
                "با وارد کردن همون شماره موبایل، مستقیم به همون حساب وصل می‌شی - نیازی به ثبت‌نام دوباره نیست.\n\n"
                "📱 شماره موبایلت رو بگو (مثلاً 09121234567):"
            )
            context.user_data["state"] = "onboarding_mobile_link"

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"📋 راهنمای {BOT_NAME}\n\n"
            "/start - شروع مجدد\n"
            "/report - دریافت گزارش PDF\n"
            "/status - وضعیت اشتراک\n"
            "/pricing - قیمت پلن‌ها\n"
            "/help - این راهنما\n"
            "/app - برنامه اختصاصی\n\n"
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

    def _clean_name(self, raw: str) -> str:
        words_to_remove = ["هستم", "من", "اسم", "نام", "بنده", "حقیر"]
        for w in words_to_remove:
            raw = raw.replace(w, "")
        return raw.strip()

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
            "پیمانکاری": "پیمانکاری", "پیمانکاری": "پیمانکاری",
            "غذا": "مواد غذایی", "مواد غذایی": "مواد غذایی",
            "لباس": "پوشاک", "پوشاک": "پوشاک",
            "آرایش": "آرایشگاهی", "آرایشگاهی": "آرایشگاهی",
        }
        return mapping.get(raw.strip(), raw.strip())

    async def handle_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        state = context.user_data.get("state")
        telegram_id = str(update.effective_user.id)
        user_id = self.auth_manager.get_user_by_telegram(telegram_id)

        if state == "onboarding_mobile_link":
            mobile = self._normalize_mobile(text)
            if not re.match(r'^09\d{9}$', mobile):
                await update.message.reply_text(
                    "شماره موبایل معتبر نیست. لطفاً به شکل 09121234567 وارد کن:"
                )
                return
            otp_result = self.auth_manager.request_otp(mobile)
            if not otp_result.get("success"):
                await update.message.reply_text(f"❌ {otp_result.get('message')}")
                return
            context.user_data["reg_mobile"] = mobile
            context.user_data["state"] = "onboarding_otp_link"
            dev_code = otp_result.get("dev_code")
            msg = f"یک کد تایید ۶ رقمی به شماره {mobile} پیامک شد. لطفاً همون کد رو بفرست:"
            if dev_code:
                msg += f"\n\n(حالت تست، چون پیامک واقعی وصل نیست: {dev_code})"
            await update.message.reply_text(msg)

        elif state == "onboarding_otp_link":
            code = "".join(ch for ch in text if ch.isdigit())
            mobile = context.user_data.get("reg_mobile", "")
            verify_result = self.auth_manager.verify_otp(mobile, code)
            if not verify_result.get("success"):
                await update.message.reply_text(
                    f"❌ {verify_result.get('message')}\nدوباره کد رو بفرست، یا با /start از اول شروع کن."
                )
                return
            linked_user_id = verify_result["user_id"]
            link_result = self.auth_manager.link_telegram(linked_user_id, telegram_id)
            if not link_result.get("success"):
                await update.message.reply_text(f"❌ {link_result.get('message')}")
                context.user_data["state"] = None
                return
            if not verify_result.get("is_new"):
                profile = self.auth_manager.get_user_profile(linked_user_id) or {}
                context.user_data["state"] = None
                await update.message.reply_text(
                    f"✅ وصل شد! خوش اومدی {profile.get('name') or ''} جان 👋\n\n"
                    f"کسب و کار: {profile.get('business_name') or '-'}\n\n"
                    "حساب تلگرامت به همون حساب قبلیت وصل شد. هر سندی داری بگو!"
                )
                return
            context.user_data["reg_mobile"] = mobile
            context.user_data["state"] = "onboarding_name"
            await update.message.reply_text(
                "خب، حساب جدیدی برات می‌سازم!\n\n"
                "❓ لطفاً نام و نام خانوادگی خودت رو بگو:"
            )

        elif state == "onboarding_name":
            cleaned = self._clean_name(text)
            context.user_data["reg_name"] = cleaned
            context.user_data["state"] = "onboarding_business_type"
            await update.message.reply_text(
                f"خوشحالم {cleaned} جان! 😊\n\n"
                "کسب و کارت تو چه زمینه‌ایه؟\n"
                "مثلاً: بازرگانی عمومی، آهن‌آلات، آرایشگاهی، مواد غذایی، پوشاک، خدمات"
            )

        elif state == "onboarding_business_type":
            normalized = self._normalize_business_type(text)
            context.user_data["reg_business_type"] = normalized
            if not context.user_data.get("reg_name"):
                # وارد این مرحله شده بدون عبور از "onboarding_name" (مثلاً تکمیل پروفایل کاربر قبلاً لینک‌شده)
                profile = self.auth_manager.get_user_profile(user_id) if user_id else None
                context.user_data["reg_name"] = (profile or {}).get("name") or "کاربر"
            name = context.user_data["reg_name"]
            context.user_data["state"] = "onboarding_business_name"
            await update.message.reply_text(
                f"{name} جان، اسم کسب و کارت چیه؟\n"
                "مثلاً: البرز فلز، شرکت آذر، فروشگاه بهار"
            )

        elif state == "invoice_customer":
            context.user_data["invoice_customer_name"] = text
            context.user_data["state"] = "invoice_items"
            await update.message.reply_text(
                "چی براش فاکتور شد؟ مبلغ و توضیحات رو بگو:\n"
                "مثلاً: فروش ۵ تن مفتول گالوانیزه ۱۲۰,۰۰۰,۰۰۰ تومان"
            )

        elif state == "invoice_items":
            invoice_type = context.user_data.get("invoice_type", "invoice")
            customer = context.user_data.get("invoice_customer_name", "مشتری")
            description = text
            numbers = re.findall(r'[\d,]+', text.replace(",", ""))
            if numbers:
                amount = int(numbers[-1])
            else:
                amount = 0

            context.user_data["state"] = None
            if amount < 1000:
                await update.message.reply_text(
                    "مبلغ تشخیص داده نشد یا خیلی کمه.\n"
                    "لطفاً مبلغ رو به تومان بگو:\n"
                    "مثلاً: فروش ۵۰ عدد کتاب ۲,۰۰۰,۰۰۰ تومان"
                )
                return

            msg_type = "پیش‌فاکتور" if invoice_type == "proforma" else "فاکتور"

            if invoice_type == "proforma":
                await update.message.reply_text(
                    f"📋 پیش‌فاکتور برای {customer} ثبت شد.\n"
                    f"💰 مبلغ: {amount:,} تومان\n"
                    f"📝 شرح: {description[:100]}\n\n"
                    "💡 پیش‌فاکتور در سیستم ثبت شد. برای تبدیل به فاکتور و ثبت سند حسابداری، "
                    "از دستور «فاکتور میخوام» استفاده کن."
                )
                return

            lic = self.license_manager.can_create_voucher(user_id)
            if not lic.get("allowed", True):
                await update.message.reply_text(f"❌ {lic.get('message', 'محدودیت مجوز')}")
                return

            entry_id = self.engine.create_voucher(
                date=datetime.now(),
                description=f"فاکتور برای {customer}: {description}",
                lines=[
                    ("1201", amount, 'debit'),
                    ("4001", amount, 'credit')
                ]
            )
            await update.message.reply_text(
                f"✅ فاکتور برای {customer} ثبت شد.\n"
                f"📋 شماره سند: {entry_id}\n"
                f"💰 مبلغ: {amount:,} تومان\n"
                f"📝 شرح: {description[:100]}"
            )

        elif state == "onboarding_business_name":
            biz_type = context.user_data.get("reg_business_type", "بازرگانی عمومی")
            biz_name = text
            self.auth_manager.update_user_profile(
                user_id, business_type=biz_type, business_name=biz_name
            )
            context.user_data["state"] = None
            await update.message.reply_text(
                f"✅ اطلاعات کسب و کارت ذخیره شد!\n"
                f"نوع: {biz_type}\n"
                f"نام: {biz_name}\n\n"
                "حالا می‌تونیم شروع کنیم. هر سندی داری بگو!"
            )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        if text.startswith("/"):
            return

        telegram_id = str(update.effective_user.id)
        user_id = self.auth_manager.get_user_by_telegram(telegram_id)

        if context.user_data.get("state"):
            await self.handle_onboarding(update, context)
            return

        if not user_id:
            await update.message.reply_text(
                f"سلام! من {BOT_NAME} هستم 🤖\n"
                "به نظر میاد هنوز ثبت نام نکردی.\n"
                "برای شروع /start رو بزن."
            )
            return

        # بررسی کامل بودن پروفایل کاربر
        profile = self.auth_manager.get_user_profile(user_id)
        if profile and (not profile["business_type"] or not profile["business_name"]):
            context.user_data["state"] = "onboarding_business_type"
            await update.message.reply_text(
                f"{profile['name']} جان، اطلاعات کسب و کارت هنوز کامل نیست!\n\n"
                "کسب و کارت تو چه زمینه‌ایه؟\n"
                "مثلاً: بازرگانی عمومی، آهن‌آلات، آرایشگاهی، مواد غذایی، پوشاک، خدمات"
            )
            return

        # تشخیص درخواست فاکتور/پیش‌فاکتور
        invoice_keywords = ["فاکتور میخوام", "فاکتور کن", "فاکتور بزن", "فاکتور بده", "فاکتور برام", "برام فاکتور",
                           "پیش فاکتور", "پیش‌فاکتور", "پیشفاکتور",
                           "proforma", "invoice"]
        if any(k in text for k in invoice_keywords):
            is_proforma = "پیش" in text or "proforma" in text.lower()
            context.user_data["invoice_type"] = "proforma" if is_proforma else "invoice"
            context.user_data["state"] = "invoice_customer"
            await update.message.reply_text(
                "نام مشتری رو بگو:\n"
                "مثلاً: علی کریمی"
            )
            return

        # تشخیص درخواست تصحیح/ویرایش اطلاعات
        correction_words = ["اشتباه", "اصلاح", "ویرایش", "تصحیح", "ببخشید", "غلط", "edit", "correct"]
        if any(c in text for c in correction_words):
            context.user_data["state"] = "onboarding_business_type"
            await update.message.reply_text(
                "باشه اطلاعات قبلی رو تصحیح می‌کنیم.\n"
                "کسب و کارت تو چه زمینه‌ایه؟\n"
                "مثلاً: آهن‌آلات، بازرگانی عمومی، خدمات، تولیدی"
            )
            return

        # تشخیص سلام و احوالپرسی
        greetings = ["سلام", "علیک", "درود", "خوبی", "hi", "hello", "slm", "سلا", "مرسی", "ممنون", "چطوری", "خوبم"]
        if any(g in text for g in greetings) and not any(k in text for k in ["خرید", "فروش", "پرداخت", "دریافت", "پول", "هزار", "میلیون", "تومان"]):
            await update.message.reply_text(
                f"سلام! {BOT_NAME} هستم 🤖 حسابدار شخصی شما\n"
                "هر کاری داری بگو. می‌تونم:\n\n"
                "📝 ثبت سند حسابداری\n"
                "💰 مانده حساب مشتریان\n"
                "📊 گزارش بگیرم\n"
                "🎤 ویس تو بفهمم\n\n"
                "چطور می‌تونم کمکت کنم؟"
            )
            return

        # سوال درباره کسب و کار یا پروفایل (کلمات کلیدی گسترده)
        profile_keywords = ["کسب", "کارم", "شغل", "پروفایل", "اطلاعات", "لوگو", "شماره",
                           "تلفن", "شناسه", "اقتصادی", "کد ملی", "کد اقتصادی", "آدرس", "ثبت",
                           "دفتر", "همراه", "logo", "address", "phone",
                           "اطلاعات من", "پروفایل من"]
        if any(k in text for k in profile_keywords):
            profile = self.auth_manager.get_user_profile(user_id)
            if not profile:
                await update.message.reply_text("اول /start رو بزن.")
                return
            has_info = profile["business_type"] or profile["business_name"]
            if has_info:
                await update.message.reply_text(
                    f"📋 اطلاعات ثبت شده شما:\n"
                    f"نام: {profile['name']}\n"
                    f"کسب و کار: {profile['business_name'] or '-'}\n"
                    f"نوع فعالیت: {profile['business_type'] or '-'}\n"
                    f"تلفن دفتر: {profile['phone_office'] or '-'}\n"
                    f"تلفن همراه: {profile['phone_mobile'] or '-'}\n"
                    f"شناسه ملی: {profile['national_id'] or '-'}\n"
                    f"کد اقتصادی: {profile['economic_code'] or '-'}\n"
                    f"آدرس: {profile['address'] or '-'}\n\n"
                    "برای ویرایش هرکدوم، دقیقاً بنویس:\n"
                    "مثلاً:\n"
                    "تلفن دفتر: ۰۲۱۱۲۳۴۵۶۷۸\n"
                    "شناسه ملی: ۱۲۳۴۵۶۷۸۹۰\n"
                    "کد اقتصادی: ۱۲۳۴۵۶۷۸۹۰"
                )
            else:
                context.user_data["state"] = "onboarding_business_type"
                await update.message.reply_text(
                    "هنوز اطلاعات کسب و کارت رو ثبت نکردی!\n"
                    "کسب و کارت تو چه زمینه‌ایه؟\n"
                    "مثلاً: بازرگانی عمومی، آهن‌آلات، آرایشگاهی، مواد غذایی، پوشاک، خدمات"
                )
            return

        # تشخیص تغییر اسم کسب و کار (مثلاً "اسم مغازم البرز فلزه")
        if "اسم" in text and ("کسب" in text or "مغازه" in text or "فروشگاه" in text or "business" in text):
            for prefix in ["اسم کسب و کارم", "اسم کسب و کار", "اسم مغازهم", "اسم مغازم", "اسم مغازه", "اسم فروشگاهم", "اسم فروشگاه"]:
                if prefix in text:
                    new_name = text.split(prefix)[-1].strip()
                    new_name = re.sub(r'[هست]=|[هست]|ه$', '', new_name).strip()
                    if new_name:
                        self.auth_manager.update_user_profile(user_id, business_name=new_name)
                        await update.message.reply_text(f"✅ اسم کسب و کار به «{new_name}» تغییر یافت.")
                        return

        # تشخیص درخواست ویرایش پروفایل (چند خطی)
        field_map = {
            "تلفن دفتر": "phone_office", "phone": "phone_office", "تلفن": "phone_office",
            "تلفن همراه": "phone_mobile", "mobile": "phone_mobile", "موبایل": "phone_mobile",
            "شناسه ملی": "national_id", "شناسه": "national_id", "ملی": "national_id",
            "کد اقتصادی": "economic_code", "اقتصادی": "economic_code",
            "آدرس": "address", "ادرس": "address", "address": "address",
        }
        updated_fields = []
        for line in text.split("\n"):
            line = line.strip()
            match = re.match(r'(تلفن دفتر|تلفن همراه|شناسه ملی|کد اقتصادی|آدرس|ادرس|شناسه|ملی|اقتصادی|تلفن|موبایل|phone|mobile|address)\s*[:=]?\s*(.+)', line, re.I)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                field = field_map.get(key, "")
                if field and value:
                    self.auth_manager.update_user_profile(user_id, **{field: value})
                    updated_fields.append(key)
        if updated_fields:
            await update.message.reply_text(f"✅ {', '.join(updated_fields)} با موفقیت ذخیره شد.")
            return

        # ===== پردازش با LLM =====
        result = await asyncio.to_thread(self.llm.process, text)

        if result.get("error") in ("no_api_key", "ollama_offline"):
            await self._process_rule_based(update, context, user_id, text)
            return
        elif result.get("error") == "timeout":
            await self._process_rule_based(update, context, user_id, text)
            return

        if result.get("success"):
            amount = result.get("amount", 0)
            if amount <= 1000:
                await update.message.reply_text(
                    f"🤔 مبلغ {amount:,} تومان تشخیص داده شد که خیلی کم به نظر میرسه.\n"
                    "لطفاً مبلغ رو با عدد به تومان بگو:\n"
                    "مثلاً: خرید ۱۰۰ خودکار ۵۰۰۰ تومان\n"
                    "یا: مبلغ ۵۰۰۰۰۰ تومان"
                )
                return
            lic = self.license_manager.can_create_voucher(user_id)
            if not lic.get("allowed", True):
                await update.message.reply_text(f"❌ {lic.get('message', 'محدودیت مجوز')}")
                return
            entry_id = self.engine.create_voucher(
                date=datetime.now(),
                description=result["description"],
                lines=[
                    (result["debit_account"], amount, 'debit'),
                    (result["credit_account"], amount, 'credit')
                ]
            )
            await update.message.reply_text(
                f"✅ سند شماره {entry_id} ثبت شد.\n"
                f"💰 مبلغ: {amount:,} تومان\n"
                f"📝 شرح: {result['description'][:100]}\n"
                f"📊 بدهکار: {self.get_account_name(result['debit_account'])}\n"
                f"📊 بستانکار: {self.get_account_name(result['credit_account'])}"
            )
            await self.send_notification_if_needed(update, user_id)
        elif result.get("type") in ("general", "greeting"):
            await update.message.reply_text(result["message"])
        else:
            await self._process_rule_based(update, context, user_id, text)

    async def _process_rule_based(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  user_id: int, text: str) -> None:
        account_keywords = ["خرید", "فروش", "پرداخت", "دریافت", "پول", "تومان", "ریال",
                           "هزار", "میلیون", "میلیارد", "سند", "حساب", "مشتری", "فروشنده",
                           "بدهکار", "بستانکار", "مانده", "قرض", "حواله", "چک", "سفته",
                           "اجاره", "حقوق", "قبض", "صورتحساب", "فاکتور", "پیش فاکتور"]
        has_ak = any(k in text for k in account_keywords)
        has_num = bool(re.search(r'\d+', text))
        if not has_ak and not has_num:
            await update.message.reply_text(
                f"😊 سلام! من {BOT_NAME} هستم.\n"
                "اگر سوال حسابداری داری، بپرس.\n"
                "مثال:\n"
                "• خرید ۱۰۰ عدد خودکار ۵۰۰۰ تومان\n"
                "• علی کریمی ۵۰۰ هزار تومان پول زد\n"
                "• پرداخت اجاره ۱۰ میلیون\n"
                "• اطلاعات من\n\n"
                "یا /help"
            )
            return
        response = self.dialog.process_message(user_id, text)
        if "متوجه نشدم" in response:
            fallback = self.text_handler.parse_and_create_voucher(text, user_id=user_id)
            if fallback.get("success"):
                await update.message.reply_text(fallback["message"])
                await self.send_notification_if_needed(update, user_id)
                return
            await update.message.reply_text(
                f"🤔 متوجه منظورت نشدم.\n\n"
                "مثل اینا بهم بگو:\n"
                "• خرید ۱۰۰ عدد خودکار ۵۰۰۰ تومان\n"
                "• علی کریمی ۵۰۰ هزار تومان پول زد\n"
                "• پرداخت به شرکت آذر ۲۰۰ هزار تومان\n"
                "• مانده حساب علی کریمی\n"
                "• پرداخت اجاره ۱۰ میلیون تومان\n\n"
                "یا /help برای راهنما"
            )
        else:
            await update.message.reply_text(response)
            await self.send_notification_if_needed(update, user_id)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = str(update.effective_user.id)
            user_id = self.auth_manager.get_user_by_telegram(telegram_id)
            if not user_id:
                await update.message.reply_text("اول /start رو بزن تا ثبت نام کنی.")
                return

            await update.message.reply_text(f"🎤 {BOT_NAME} داره ویس تو گوش می‌کنه...")

            voice_file = await update.message.voice.get_file()
            file_path = f"voice_files/{update.message.message_id}.ogg"
            await voice_file.download_to_drive(file_path)

            data, transcript = await asyncio.to_thread(self.voice_handler.voice_to_voucher, file_path)

            amount = data.get("amount", 0)
            if data["type"] and amount >= 1000:
                lic = self.license_manager.can_create_voucher(user_id)
                if not lic.get("allowed", True):
                    await update.message.reply_text(f"❌ {lic.get('message', 'محدودیت مجوز')}")
                    return
                entry_id = self.engine.create_voucher(
                    date=datetime.now(),
                    description=data["description"],
                    lines=[
                        (data["debit_account"], amount, 'debit'),
                        (data["credit_account"], amount, 'credit')
                    ]
                )
                await update.message.reply_text(
                    f"✅ سند شماره {entry_id} ثبت شد.\n\n"
                    f"💰 مبلغ: {amount:,} تومان\n"
                    f"📝 شرح: {data['description'][:100]}\n"
                    f"📊 بدهکار: {self.get_account_name(data['debit_account'])}\n"
                    f"📊 بستانکار: {self.get_account_name(data['credit_account'])}"
                )
                await self.send_notification_if_needed(update, user_id)
                return

            from core.ai_voucher_fallback import try_ai_voucher
            ai_result = await asyncio.to_thread(try_ai_voucher, self.engine, transcript, user_id)
            if ai_result.get("success"):
                await update.message.reply_text(
                    f"✅ سند شماره {ai_result['entry_id']} ثبت شد. (تشخیص با هوش مصنوعی)\n\n"
                    f"💰 مبلغ: {ai_result['amount']:,.0f} تومان\n"
                    f"📝 شرح: {ai_result['description'][:100]}\n"
                    f"📊 بدهکار: {self.get_account_name(ai_result['debit_account'])}\n"
                    f"📊 بستانکار: {self.get_account_name(ai_result['credit_account'])}"
                )
                await self.send_notification_if_needed(update, user_id)
            else:
                await update.message.reply_text(
                    "⚠️ متوجه ویس تو نشدم. لطفاً واضح‌تر بگو.\n"
                    "مثال: خرید ۱۰۰ عدد خودکار ۵۰۰۰ تومان"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ خطا: {str(e)}")

    def get_account_name(self, code: str) -> str:
        from core.iran_accounting_codes import get_account_name
        return get_account_name(code)

    async def report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = str(update.effective_user.id)
        user_id = self.auth_manager.get_user_by_telegram(telegram_id)
        if not user_id:
            await update.message.reply_text("اول /start رو بزن تا ثبت نام کنی.")
            return
        try:
            await update.message.reply_text("📊 در حال تولید گزارش...")
            from reports.pdf_generator import PDFReportGenerator
            reporter = PDFReportGenerator(self.engine)
            pdf_file = await asyncio.to_thread(
                reporter.create_trial_balance_pdf, f"temp_report_{user_id}.pdf", user_id
            )
            await update.message.reply_document(document=open(pdf_file, 'rb'))
            os.remove(pdf_file)
        except Exception as e:
            await update.message.reply_text(f"❌ خطا: {str(e)}")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_id = str(update.effective_user.id)
        user_id = self.auth_manager.get_user_by_telegram(telegram_id)
        if not user_id:
            await update.message.reply_text("اول /start رو بزن تا ثبت نام کنی.")
            return
        status = self.license_manager.check_license(user_id)
        if status["is_valid"]:
            days = status.get("days_left", 0)
            plan = status.get("plan_type", "آزمایشی")
            used = status.get("used_vouchers", 0)
            max_v = status.get("max_vouchers", 0)
            msg = f"📋 وضعیت اشتراک:\nپلن: {plan}\nروزهای باقی مانده: {days}\n"
            if max_v > 0:
                msg += f"اسناد استفاده شده: {used} از {max_v}"
            else:
                msg += f"تعداد اسناد: {used} (نامحدود)"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(status.get("message", "اشتراک شما منقضی شده."))

    async def pricing_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        plans = self.license_manager.get_pricing_message()
        await update.message.reply_text(plans)

    async def app_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📱 برنامه نارین", web_app=WebAppInfo(url=f"{get_public_app_url()}/app"))
        ]])
        await update.message.reply_text(
            f"برای باز کردن برنامه {BOT_NAME}، روی دکمه پایین بزن:",
            reply_markup=keyboard,
        )

    async def send_notification_if_needed(self, update: Update, user_id: int):
        msg = self.notifier.check_renewal_reminder(user_id)
        if msg:
            await update.message.reply_text(msg)
        limit_msg = self.notifier.get_voucher_limit_warning(user_id)
        if limit_msg:
            await update.message.reply_text(limit_msg)
        inventory_msg = self.notifier.get_inventory_deficit_reminder(user_id)
        if inventory_msg:
            await update.message.reply_text(inventory_msg)

    def run(self) -> None:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("report", self.report))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CommandHandler("pricing", self.pricing_command))
        app.add_handler(CommandHandler("app", self.app_command))
        app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        print(f"🤖 {BOT_NAME} روشن شد...")
        app.run_polling()

if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()