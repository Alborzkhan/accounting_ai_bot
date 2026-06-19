# core/iran_accounting_codes.py
"""
کدینگ استاندارد حسابداری ایران - بر اساس طرح جدید کدینگ حساب‌ها
"""

from typing import Tuple

# ساختار اصلی کدینگ (6 رقمی)
# سطح 1: 2 رقم (گروه اصلی)
# سطح 2: 2 رقم (زیرگروه)
# سطح 3: 2 رقم (حساب تفصیلی)

ACCOUNT_CODES = {
    # دارایی‌های جاری (10-19)
    "1001": {"name": "صندوق", "type": "asset", "group": "دارایی‌های جاری"},
    "1002": {"name": "بانک", "type": "asset", "group": "دارایی‌های جاری"},
    "1101": {"name": "بدهکاران تجاری", "type": "asset", "group": "دارایی‌های جاری"},
    "1102": {"name": "اسناد دریافتنی", "type": "asset", "group": "دارایی‌های جاری"},
    "1201": {"name": "موجودی کالا", "type": "asset", "group": "دارایی‌های جاری"},
    "1202": {"name": "مواد اولیه", "type": "asset", "group": "دارایی‌های جاری"},
    "1203": {"name": "کالای در جریان ساخت", "type": "asset", "group": "دارایی‌های جاری"},
    "1301": {"name": "پیش‌پرداخت", "type": "asset", "group": "دارایی‌های جاری"},
    
    # دارایی‌های ثابت (20-29)
    "2001": {"name": "زمین", "type": "asset", "group": "دارایی‌های ثابت"},
    "2002": {"name": "ساختمان", "type": "asset", "group": "دارایی‌های ثابت"},
    "2003": {"name": "ماشین‌آلات", "type": "asset", "group": "دارایی‌های ثابت"},
    "2004": {"name": "وسایط نقلیه", "type": "asset", "group": "دارایی‌های ثابت"},
    "2005": {"name": "تجهیزات کامپیوتری", "type": "asset", "group": "دارایی‌های ثابت"},
    "2101": {"name": "استهلاک انباشته", "type": "contra_asset", "group": "دارایی‌های ثابت"},
    
    # بدهی‌های جاری (30-39)
    "3001": {"name": "بستانکاران تجاری", "type": "liability", "group": "بدهی‌های جاری"},
    "3002": {"name": "اسناد پرداختنی", "type": "liability", "group": "بدهی‌های جاری"},
    "3003": {"name": "پیش‌دریافت", "type": "liability", "group": "بدهی‌های جاری"},
    "3004": {"name": "مالیات بر ارزش افزوده پرداختنی", "type": "liability", "group": "بدهی‌های جاری"},
    
    # بدهی‌های بلندمدت (40-49)
    "4001": {"name": "تسهیلات بانکی بلندمدت", "type": "liability", "group": "بدهی‌های بلندمدت"},
    
    # حقوق صاحبان سهام (50-59)
    "5001": {"name": "سرمایه", "type": "equity", "group": "حقوق صاحبان سهام"},
    "5002": {"name": "سود (زیان) انباشته", "type": "equity", "group": "حقوق صاحبان سهام"},
    
    # درآمدها (60-69)
    "6001": {"name": "فروش کالا", "type": "income", "group": "درآمدها"},
    "6002": {"name": "درآمد خدمات", "type": "income", "group": "درآمدها"},
    
    # هزینه‌ها (70-89)
    "7001": {"name": "بهای تمام شده کالای فروش رفته", "type": "expense", "group": "هزینه‌ها"},
    "7002": {"name": "هزینه حقوق و دستمزد", "type": "expense", "group": "هزینه‌ها"},
    "7003": {"name": "هزینه اجاره", "type": "expense", "group": "هزینه‌ها"},
    "7004": {"name": "هزینه حمل و نقل", "type": "expense", "group": "هزینه‌ها"},
    "7005": {"name": "هزینه تعمیر و نگهداری", "type": "expense", "group": "هزینه‌ها"},
    "7006": {"name": "هزینه کارمزد", "type": "expense", "group": "هزینه‌ها"},
    "7007": {"name": "هزینه بیمه", "type": "expense", "group": "هزینه‌ها"},
    "7008": {"name": "هزینه تبلیغات", "type": "expense", "group": "هزینه‌ها"},
    "7009": {"name": "هزینه استهلاک", "type": "expense", "group": "هزینه‌ها"},
    "7010": {"name": "هزینه مالیاتی", "type": "expense", "group": "هزینه‌ها"},
}

# کلمات کلیدی برای تشخیص خودکار حساب
KEYWORD_MAPPING = {
    "6001": ["فروش", "فروخت", "فروشنده"],  # فروش کالا
    "7001": ["بهای تمام شده", "بهای کالا"],  # بهای تمام شده
    "7002": ["حقوق", "دستمزد", "پرسنل"],  # هزینه حقوق
    "7003": ["اجاره"],  # هزینه اجاره
    "7004": ["حمل", "کرایه", "باربری", "ارسال"],  # هزینه حمل
    "7005": ["تعمیر", "نگهداری", "سرویس"],  # هزینه تعمیرات
    "7006": ["کارمزد", "کمیسیون", "کارمزد بانکی"],  # هزینه کارمزد
    "3001": ["پرداخت", "بستانکار"],  # بستانکاران تجاری
    "1101": ["دریافت", "بدهکار", "مشتری"],  # بدهکاران تجاری
    "1201": ["خرید", "کالا", "موجودی"],  # موجودی کالا
    "1001": ["صندوق", "نقد", "پول نقد"],  # صندوق
}


def get_account_name(code: str) -> str:
    """دریافت نام حساب بر اساس کد"""
    return ACCOUNT_CODES.get(code, {}).get("name", "نامشخص")


def get_account_type(code: str) -> str:
    """دریافت نوع حساب بر اساس کد"""
    return ACCOUNT_CODES.get(code, {}).get("type", "unknown")


def suggest_accounts(description: str) -> Tuple[str, str]:
    """پیشنهاد حساب بدهکار و بستانکار بر اساس شرح"""
    debit = "1201"  # پیش‌فرض موجودی کالا
    credit = "3001"  # پیش‌فرض بستانکاران تجاری
    
    description_lower = description.lower()
    
    for code, keywords in KEYWORD_MAPPING.items():
        for kw in keywords:
            if kw in description_lower:
                code_info = ACCOUNT_CODES.get(code, {})
                if code_info.get("type") in ["income"]:
                    credit = code
                elif code_info.get("type") in ["expense", "asset"]:
                    debit = code
                else:
                    credit = code
    
    return debit, credit


if __name__ == "__main__":
    print("🏦 کدینگ استاندارد حسابداری ایران")
    print("=" * 40)
    
    test_descriptions = [
        "خرید 100 کیلو مفتول",
        "فروش 50 عدد خودکار",
        "پرداخت حقوق کارکنان",
        "پرداخت کارمزد بانکی",
        "پرداخت اجاره مغازه",
        "تعمیر دستگاه تولید",
    ]
    
    for desc in test_descriptions:
        debit, credit = suggest_accounts(desc)
        print(f"\n📝 {desc}")
        print(f"   بدهکار: {debit} - {get_account_name(debit)}")
        print(f"   بستانکار: {credit} - {get_account_name(credit)}")