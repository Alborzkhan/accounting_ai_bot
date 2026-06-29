# core/text_command_handler.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from datetime import datetime
from typing import Dict, Tuple, Optional
from core.accounting_engine import AccountingEngine
from core.auto_categorizer import AutoCategorizer

class TextCommandHandler:
    def __init__(self, engine: AccountingEngine) -> None:
        self.engine = engine
        self.categorizer = AutoCategorizer()
    
    def parse_and_create_voucher(self, text: str, user_id: Optional[int] = None) -> Dict:
        """
        تبدیل متن ساده به سند حسابداری و ثبت آن
        مثال: "خرید 100 عدد خودکار از احمدی 5000 تومان"
        """
        result = {
            "success": False,
            "message": "",
            "entry_id": None,
            "data": {}
        }
        
        # تشخیص نوع عملیات
        if "خرید" in text:
            result["data"]["type"] = "خرید"
            result["data"]["debit_account"] = "1201"  # موجودی کالا
            result["data"]["credit_account"] = "2001"  # بستانکاران تجاری
        elif "فروش" in text:
            result["data"]["type"] = "فروش"
            result["data"]["debit_account"] = "1101"  # بدهکاران تجاری
            result["data"]["credit_account"] = "4001"  # فروش کالا
        elif "پرداخت" in text:
            result["data"]["type"] = "پرداخت"
            result["data"]["debit_account"] = "2001"  # بستانکاران تجاری
            result["data"]["credit_account"] = "1001"  # صندوق
        elif "دریافت" in text:
            result["data"]["type"] = "دریافت"
            result["data"]["debit_account"] = "1001"  # صندوق
            result["data"]["credit_account"] = "1101"  # بدهکاران تجاری
        else:
            result["success"] = False
            result["message"] = "نوع عملیات تشخیص داده نشد (خرید/فروش/پرداخت/دریافت)"
            return result
        
        # استخراج مبلغ — فقط اگه کلمه‌ای مرتبط با قیمت توی متن باشه
        PRICE_KEYWORDS = ["تومان", "ریال", "میلیون", "میلیارد", "هزار"]
        if not any(k in text for k in PRICE_KEYWORDS):
            result["success"] = False
            result["message"] = "مبلغ رو مشخص نکردی. مثال:\nخرید ۵ تن مفتول گالوانیزه ۸۰,۰۰۰,۰۰۰ تومان"
            return result

        numbers = re.findall(r'\d+', text)
        if numbers:
            result["data"]["amount"] = int(numbers[-1])
            if "هزار" in text and "میلیون" not in text:
                result["data"]["amount"] *= 1000
            elif "میلیون" in text:
                result["data"]["amount"] *= 1_000_000
            elif "میلیارد" in text:
                result["data"]["amount"] *= 1_000_000_000
        else:
            result["success"] = False
            result["message"] = "مبلغ تشخیص داده نشد. مثال: ۵۰۰۰ تومان"
            return result
        
        # اعتبارسنجی مبلغ (مقادیر خیلی کم احتمالاً خطای تشخیص هستند)
        if result["data"]["amount"] <= 1000:
            result["success"] = False
            result["message"] = "مبلغ تشخیص داده نشد یا خیلی کمه. لطفاً مبلغ رو به تومان بنویس (مثلاً ۵۰۰۰ تومان)."
            return result
        
        # دسته‌بندی خودکار و پیشنهاد محصول
        try:
            auto_result = self.categorizer.auto_categorize_voucher(text)
            result["data"]["suggested_product"] = auto_result.get("suggested_product", "")
            result["data"]["suggested_category"] = auto_result.get("suggested_category", "")
            
            # اگر حساب‌ها تشخیص داده نشد، از دسته‌بندی خودکار استفاده کن
            if result["data"]["debit_account"] == "1201" and "خرید" in text:
                # پیشنهاد به کاربر
                print(f"\n💡 پیشنهاد: محصول '{auto_result['suggested_product']}' در دسته '{auto_result['suggested_category']}' قرار گرفت.")
        except Exception as e:
            print(f"⚠️ خطا در دسته‌بندی خودکار: {e}")
        
        try:
            entry_id = self.engine.create_voucher(
                date=datetime.now(),
                description=text[:200],
                lines=[
                    (result["data"]["debit_account"], result["data"]["amount"], 'debit'),
                    (result["data"]["credit_account"], result["data"]["amount"], 'credit')
                ],
                user_id=user_id
            )
            result["success"] = True
            result["entry_id"] = entry_id
            result["message"] = f"✅ سند شماره {entry_id} با موفقیت ثبت شد."
            result["data"]["description"] = text
        except Exception as e:
            result["success"] = False
            result["message"] = f"❌ خطا در ثبت سند: {e}"
        
        return result
    
    def get_help(self) -> str:
        return """
📋 راهنمای ثبت سند با متن:

مثال‌ها:
• خرید 100 عدد خودکار 5000 تومان
• فروش 50 عدد کتاب 20000 تومان
• پرداخت به شرکت آذر 1000000 تومان
• دریافت از علی کریمی 500000 تومان

دستورات دیگر:
• تراز - نمایش تراز آزمایشی
• مشتری: علی کریمی 09121112222 - ثبت مشتری جدید
• خروج - خروج از برنامه
        """

if __name__ == "__main__":
    engine = AccountingEngine()
    handler = TextCommandHandler(engine)
    
    print("🤖 سیستم ثبت سند با فرمان متنی")
    print(handler.get_help())
    print("-" * 50)
    
    while True:
        cmd = input("\n>> ").strip()
        if cmd == "خروج":
            break
        elif cmd == "تراز":
            balances = engine.get_trial_balance()
            print("\n📊 تراز آزمایشی:")
            for row in balances:
                if row.total_debit != 0 or row.total_credit != 0:
                    print(f"{row.code} - {row.name}: بدهکار {row.total_debit:,.0f} | بستانکار {row.total_credit:,.0f}")
        elif cmd.startswith("مشتری:"):
            parts = cmd[6:].strip().split()
            if len(parts) >= 2:
                name = parts[0] + " " + parts[1] if len(parts) > 2 else parts[0]
                phone = parts[-1] if len(parts) > 1 else ""
                cust_id = engine.add_customer(name, phone)
                print(f"✅ مشتری {name} با کد {cust_id} ثبت شد.")
            else:
                print("❌ فرمت صحیح: مشتری: نام فامیل 0912xxxxxx")
        else:
            result = handler.parse_and_create_voucher(cmd)
            print(result["message"])
            if result["success"]:
                print(f"💰 مبلغ: {result['data']['amount']:,.0f} تومان")
                print(f"📝 شرح: {result['data']['description'][:100]}")
                if result['data'].get('suggested_product'):
                    print(f"🏷️ محصول: {result['data']['suggested_product']}")
                    print(f"📁 دسته: {result['data']['suggested_category']}")