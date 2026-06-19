# core/business_profile.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker
from database.models import init_db, BusinessProfile, Base
from datetime import datetime
from typing import Dict, Optional
import json

class BusinessProfileManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
    
    def get_or_create_profile(self, user_id: int) -> Dict:
        """دریافت یا ایجاد پروفایل کسب‌وکار کاربر"""
        session = self.Session()
        try:
            profile = session.query(BusinessProfile).filter(
                BusinessProfile.user_id == user_id
            ).first()
            
            if not profile:
                profile = BusinessProfile(user_id=user_id)
                session.add(profile)
                session.commit()
            
            return {
                "id": profile.id,
                "user_id": profile.user_id,
                "business_name": profile.business_name or "",
                "business_type": profile.business_type or "",
                "industry": profile.industry or "",
            }
        finally:
            session.close()
    
    def update_profile(self, user_id: int, data: Dict) -> Dict:
        """به‌روزرسانی پروفایل کسب‌وکار"""
        session = self.Session()
        try:
            profile = session.query(BusinessProfile).filter(
                BusinessProfile.user_id == user_id
            ).first()
            
            if not profile:
                profile = BusinessProfile(user_id=user_id)
                session.add(profile)
            
            if "business_name" in data:
                profile.business_name = data["business_name"]
            if "business_type" in data:
                profile.business_type = data["business_type"]
            if "industry" in data:
                profile.industry = data["industry"]
            
            session.commit()
            
            return {"success": True, "message": "پروفایل به‌روزرسانی شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()
    
    def setup_wizard(self, user_id: int) -> Dict:
        """راه‌اندازی اولیه کسب‌وکار با سوالات تعاملی"""
        print("\n" + "=" * 50)
        print("🏢 راه‌اندازی کسب‌وکار شما")
        print("=" * 50)
        print("برای دسته‌بندی بهتر کالاها و خدمات، لطفاً اطلاعات زیر را وارد کنید:\n")
        
        business_name = input("📛 نام کسب‌وکار خود را وارد کنید: ").strip()
        
        print("\n📋 نوع کسب‌وکار خود را انتخاب کنید:")
        print("   1. بازرگانی (خرید و فروش کالا)")
        print("   2. تولیدی (تولید محصولات)")
        print("   3. خدماتی (ارائه خدمات)")
        print("   4. پیمانکاری (پروژه‌های پیمانکاری)")
        
        biz_type_choice = input("\nانتخاب کنید (1-4): ").strip()
        biz_type_map = {"1": "بازرگانی", "2": "تولیدی", "3": "خدماتی", "4": "پیمانکاری"}
        business_type = biz_type_map.get(biz_type_choice, "بازرگانی")
        
        print("\n🏭 صنعت/حوزه فعالیت خود را انتخاب کنید:")
        industries = {
            "1": {"name": "آهن‌آلات", "desc": "فروش پروفیل، ورق، مفتول، لوله و اتصالات"},
            "2": {"name": "لوازم آرایشی و بهداشتی", "desc": "فروش کرم، لاک، شامپو، لوازم آرایشگاهی"},
            "3": {"name": "مواد غذایی", "desc": "فروش برنج، روغن، کنسرو، مواد خوراکی"},
            "4": {"name": "پوشاک و نساجی", "desc": "فروش البسه، پارچه، نخ"},
            "5": {"name": "صنایع چوب و مبلمان", "desc": "فروش مبلمان، MDF، روکش"},
            "6": {"name": "سایر", "desc": "سایر صنایع"}
        }
        
        for key, ind in industries.items():
            print(f"   {key}. {ind['name']} - {ind['desc']}")
        
        industry_choice = input("\nانتخاب کنید (1-6): ").strip()
        industry = industries.get(industry_choice, {"name": "سایر"})["name"]
        
        # به‌روزرسانی پروفایل
        result = self.update_profile(user_id, {
            "business_name": business_name,
            "business_type": business_type,
            "industry": industry
        })
        
        print(f"\n✅ پروفایل کسب‌وکار شما با موفقیت ثبت شد.")
        print(f"   نام: {business_name}")
        print(f"   نوع: {business_type}")
        print(f"   صنعت: {industry}")
        
        return result


if __name__ == "__main__":
    manager = BusinessProfileManager()
    
    # شبیه‌سازی یک کاربر جدید
    user_id = 1
    profile = manager.get_or_create_profile(user_id)
    
    if not profile.get("business_name"):
        manager.setup_wizard(user_id)
    
    print("\n📋 پروفایل فعلی:")
    print(f"   نام: {profile.get('business_name', '-')}")
    print(f"   نوع: {profile.get('business_type', '-')}")
    print(f"   صنعت: {profile.get('industry', '-')}")