# core/auto_categorizer.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from typing import Dict, List, Tuple
from sqlalchemy.orm import sessionmaker
from database.models import init_db, Account, Product
from core.iran_accounting_codes import suggest_accounts, get_account_name, ACCOUNT_CODES
from core.dynamic_categories import DynamicCategoryManager

class AutoCategorizer:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self.cat_manager = DynamicCategoryManager(db_path)
    
    def clean_product_name(self, raw_name: str) -> str:
        """حذف کلمات اضافی و اعداد از نام محصول"""
        if not raw_name:
            return ""
        
        stop_words = ["از", "به", "با", "و", "برای", "یک", "تومان", "ریال", 
                      "خرید", "فروش", "شرکت", "آقای", "خانم", "مبلغ", "عدد", "کیلو"]
        
        cleaned = raw_name
        for word in stop_words:
            pattern = r'\b' + re.escape(word) + r'\b'
            cleaned = re.sub(pattern, ' ', cleaned)
        
        cleaned = re.sub(r'[0-9]', '', cleaned)
        cleaned = re.sub(r'[!@#$%^&*()_+=\[\]{};:.,<>/?\\|]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()
        
        if not cleaned and len(raw_name) > 2:
            cleaned = raw_name.split()[-1]
        
        return cleaned
    
    def extract_product_name(self, description: str) -> str:
        """استخراج نام محصول از شرح سند"""
        # اگر خرید یا فروش نیست، محصولی وجود ندارد
        if not ("خرید" in description or "فروش" in description):
            return ""
        
        # حذف اعداد و ابعاد (مانند 40*80) از ابتدا
        cleaned_desc = re.sub(r'\d+\s*(?:عدد|کیلو|متر|تن|دستگاه|بسته)?', '', description)
        cleaned_desc = re.sub(r'\d+\*\d+', '', cleaned_desc)  # حذف ابعاد مثل 40*80
        cleaned_desc = re.sub(r'\d+', '', cleaned_desc)  # حذف اعداد باقیمانده
        
        # الگوی استاندارد: "خرید [نام محصول] از"
        pattern1 = r'(?:خرید|فروش)\s+([^،،\d]+?)(?:\s*از\s*[^\s]+|\s*به\s*[^\s]+|$)'
        match = re.search(pattern1, cleaned_desc)
        if match:
            raw_product = match.group(1).strip()
            cleaned = self.clean_product_name(raw_product)
            if cleaned and len(cleaned) > 2:
                return cleaned[:50]
        
        # الگوی ساده‌تر: کلمه بعد از خرید/فروش
        match = re.search(r'(?:خرید|فروش)\s+([^\s]+(?:\s+[^\s]+){0,2})', cleaned_desc)
        if match:
            raw_product = match.group(1).strip()
            cleaned = self.clean_product_name(raw_product)
            if cleaned:
                return cleaned[:50]
        
        return ""
    
    def categorize_product(self, product_name: str, business_type: str = "بازرگانی عمومی") -> str:
        """دسته‌بندی خودکار کالا با استفاده از سیستم پویا"""
        if not product_name:
            return "غیر قابل دسته‌بندی (خدمات/حقوق)"
        
        try:
            result = self.cat_manager.categorize_product(product_name, business_type)
            if result:
                return result
        except Exception as e:
            print(f"⚠️ خطا در دسته‌بندی پویا: {e}")
        
        return "متفرقه"
    
    def auto_categorize_voucher(self, description: str, industry: str = "بازرگانی عمومی") -> Dict:
        """دسته‌بندی خودکار یک سند بر اساس صنعت کاربر"""
        debit, credit = suggest_accounts(description)
        
        if "خرید" in description or "فروش" in description:
            product_name = self.extract_product_name(description)
            # استفاده از صنعت کاربر برای دسته‌بندی
            category = self.categorize_product(product_name, industry)
        else:
            product_name = ""
            category = "خدمات / هزینه"
        
        from core.iran_accounting_codes import get_account_name
        
        return {
            "debit_account": debit,
            "debit_account_name": get_account_name(debit),
            "credit_account": credit,
            "credit_account_name": get_account_name(credit),
            "suggested_category": category,
            "suggested_product": product_name if product_name else description[:30],
            "description": description
        }


if __name__ == "__main__":
    categorizer = AutoCategorizer()
    
    test_descriptions = [
        ("خرید 100 کیلو مفتول از شرکت آذر", "آهن‌آلات"),
        ("فروش 50 عدد خودکار به علی کریمی", "بازرگانی عمومی"),
        ("پرداخت حقوق کارکنان", "بازرگانی عمومی"),
        ("فروش قیچی سشوار", "آرایشگاهی"),
        ("خرید 100 کیلو برنج", "بازرگانی عمومی"),
        ("خرید پروفیل 40*80", "آهن‌آلات"),
        ("پرداخت اجاره مغازه", "بازرگانی عمومی"),
        ("دریافت از مشتری", "بازرگانی عمومی"),
    ]
    
    print("🔍 تست دسته‌بندی خودکار (نسخه اصلاح شده - حذف خطای حقوق)")
    print("=" * 70)
    
    for desc, biz_type in test_descriptions:
        result = categorizer.auto_categorize_voucher(desc, biz_type)
        print(f"\n📝 شرح: {desc}")
        print(f"   🏷️ محصول/خدمت: {result['suggested_product']}")
        print(f"   📁 دسته: {result['suggested_category']}")
        print(f"   💳 بدهکار: {result['debit_account']} - {result['debit_account_name']}")
        print(f"   💳 بستانکار: {result['credit_account']} - {result['credit_account_name']}")
        print("-" * 55)