# core/smart_business_setup.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from typing import Dict, Tuple, Optional
from core.business_profile import BusinessProfileManager

class SmartBusinessSetup:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.profile_manager = BusinessProfileManager(db_path)
    
    # کلمات کلیدی برای تشخیص نوع کسب‌وکار
    business_type_keywords = {
        "بازرگانی": ["خرید و فروش", "بازرگانی", "عمده فروشی", "خرده فروشی", "فروشگاه", "سوپرمارکت", "هایپرمارکت", "بازار", "تجارت", "واردات", "صادرات", "پخش", "اغذیه فروشی", "کالا", "فروشندگی"],
        "تولیدی": ["تولید", "کارخانه", "صنعتی", "خط تولید", "تولید کننده", "ساخت", "تولیدی", "کارگاه تولید", "بسته بندی"],
        "خدماتی": ["خدمات", "تعمیرات", "مشاوره", "آموزش", "نظافت", "نگهداری", "خدماتی", "پشتیبانی", "رستوران", "کافه", "فست فود", "کافی شاپ", "نانوایی", "کبابی", "آرایشگاه", "سالن زیبایی", "مهدکودک", "کلینیک", "مجتمع", "آپارتمان", "ساختمان", "مدیریت ساختمان", "برج"],
        "پیمانکاری": ["پیمانکاری", "پروژه", "ساخت و ساز", "عمرانی", "پیمان", "اجرای پروژه"]
    }
    
    # کلمات کلیدی برای تشخیص صنعت/حوزه فعالیت
    industry_keywords = {
        "آهن‌آلات": ["آهن", "فولاد", "پروفیل", "ورق", "مفتول", "تیرآهن", "نبشی", "قوطی", "صنایع فلزی"],
        "لوازم آرایشی و بهداشتی": ["آرایشی", "بهداشتی", "کرم", "لاک", "شامپو", "عطر", "ادکلن", "ماسک", "لوازم آرایشگاهی", "سشوار", "قیچی آرایشگاهی"],
        "مواد غذایی": ["غذایی", "برنج", "روغن", "کنسرو", "خوراکی", "آجیل", "خشکبار", "لبنیات", "نوشیدنی"],
        "پوشاک و نساجی": ["پوشاک", "لباس", "پارچه", "نساجی", "پرده", "البسه", "مد و پوشاک"],
        "صنایع چوب و مبلمان": ["مبلمان", "چوب", "ام دی اف", "کابینت", "میز", "صندلی", "صنایع چوبی"],
        "کافه و رستوران": ["کافه", "رستوران", "فست فود", "کافی شاپ", "چایخانه", "غذاخوری", "تالار", "کترینگ"],
        "خدمات نظافتی": ["نظافت", "پاکیزه", "خدمات نظافتی", "جلوگیری", "دستمالی"],
        "مدیریت مجتمع و ساختمان": ["مجتمع", "آپارتمان", "ساختمان", "مدیریت ساختمان", "برج", "مسکونی", "تجاری", "ساختمون", "شارژ", "واحد", "مالک"]
    }
    
    def detect_business_type(self, description: str) -> str:
        """تشخیص نوع کسب‌وکار از روی توضیحات کاربر"""
        description_lower = description.lower()
        
        # تشخیص کافه و رستوران به عنوان خدماتی (اولویت بالاتر)
        restaurant_keywords = ["کافه", "رستوران", "فست فود", "کافی شاپ", "نانوایی", "کبابی"]
        for kw in restaurant_keywords:
            if kw in description_lower:
                return "خدماتی"
        
        # تشخیص مجتمع و ساختمان
        building_keywords = ["مجتمع", "آپارتمان", "ساختمان", "مدیریت ساختمان", "برج"]
        for kw in building_keywords:
            if kw in description_lower:
                return "خدماتی"
        
        for biz_type, keywords in self.business_type_keywords.items():
            for kw in keywords:
                if kw in description_lower:
                    return biz_type
        
        return "بازرگانی"
    
    def detect_industry(self, description: str) -> str:
        """تشخیص صنعت/حوزه فعالیت از روی توضیحات کاربر"""
        description_lower = description.lower()
        
        # اولویت با کلمات کلیدی تخصصی
        for industry, keywords in self.industry_keywords.items():
            for kw in keywords:
                if kw in description_lower:
                    return industry
        
        # تشخیص‌های خاص
        if "آرایشگاه" in description_lower or "سالن زیبایی" in description_lower:
            return "لوازم آرایشی و بهداشتی"
        
        if "انبار" in description_lower or "عمده" in description_lower:
            return "بازرگانی عمومی"
        
        return "سایر"
    
    def extract_business_name(self, description: str) -> str:
        """استخراج نام کسب‌وکار از توضیحات کاربر"""
        patterns = [
            r'فروشگاه\s+([^\s]+(?:\s+[^\s]+){0,3})',
            r'شرکت\s+([^\s]+(?:\s+[^\s]+){0,3})',
            r'مجتمع\s+([^\s]+(?:\s+[^\s]+){0,3})',
            r'(\S+)\s+(?:دارم|هستم|داریم|هستیم)',
            r'نام\s*:\s*([^\n]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                return match.group(1).strip()
        
        words = description.split()
        if len(words) >= 2:
            return " ".join(words[:2])
        
        return description[:30]
    
    def smart_setup(self, user_id: int, user_input: str) -> Dict:
        """تنظیم هوشمند پروفایل کسب‌وکار بدون سوال اضافی"""
        business_name = self.extract_business_name(user_input)
        business_type = self.detect_business_type(user_input)
        industry = self.detect_industry(user_input)
        
        result = self.profile_manager.update_profile(user_id, {
            "business_name": business_name,
            "business_type": business_type,
            "industry": industry
        })
        
        return {
            "success": result["success"],
            "business_name": business_name,
            "business_type": business_type,
            "industry": industry,
            "message": f"✅ پروفایل کسب‌وکار شما ثبت شد:\n   نام: {business_name}\n   نوع: {business_type}\n   صنعت: {industry}"
        }
    
    def interactive_smart_setup(self, user_id: int) -> Optional[Dict]:
        """راه‌اندازی تعاملی هوشمند (فقط یک سوال)"""
        print("\n" + "=" * 50)
        print("🏢 راه‌اندازی هوشمند کسب‌وکار")
        print("=" * 50)
        print("\nلطفاً در یک جمله درباره کسب‌وکار خود توضیح دهید.")
        print("مثال: 'فروشگاه لوازم آرایشی دارم'")
        print("مثال: 'شرکت آهن‌آلات پروفیل'")
        print("مثال: 'مدیریت مجتمع مسکونی'")
        print("مثال: 'کافی شاپ و اغذیه فروشی'\n")
        
        user_input = input("📝 توضیحات: ").strip()
        
        if not user_input:
            print("❌ لطفاً توضیحاتی وارد کنید.")
            return
        
        result = self.smart_setup(user_id, user_input)
        print(f"\n{result['message']}")
        
        return result


if __name__ == "__main__":
    setup = SmartBusinessSetup()
    user_id = 1
    
    test_inputs = [
        "فروشگاه لوازم آرایشی گل‌نار",
        "شرکت آهن‌آلات البرز",
        "کافی شاپ و اغذیه فروشی پارس",
        "تولیدی پروفیل و لوله",
        "خدمات نظافتی پاکیزه",
        "مدیریت مجتمع برج نگین",
        "ساختمان مسکونی 12 واحدی"
    ]
    
    print("🔍 تست هوشمندسازی ثبت کسب‌وکار")
    print("=" * 50)
    
    for inp in test_inputs:
        result = setup.smart_setup(1, inp)
        print(f"\n📝 ورودی: {inp}")
        print(f"   نام: {result['business_name']}")
        print(f"   نوع: {result['business_type']}")
        print(f"   صنعت: {result['industry']}")
        print("-" * 40)