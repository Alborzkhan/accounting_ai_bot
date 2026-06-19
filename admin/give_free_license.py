# admin/give_free_license.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.license_manager import LicenseManager
from database.license_models import User
from database.models import init_db
from sqlalchemy.orm import sessionmaker

def give_free_license() -> None:
    print("=" * 50)
    print("🎁 اعطای لایسنس رایگان")
    print("=" * 50)
    
    lm = LicenseManager()
    session = lm.Session()
    
    try:
        # جستجوی کاربر
        mobile = input("📱 شماره موبایل کاربر: ").strip()
        user = session.query(User).filter(User.mobile == mobile).first()
        
        if not user:
            print("❌ کاربر یافت نشد. ابتدا ثبت نام کنید.")
            create = input("آیا ثبت نام کنم؟ (y/n): ").strip()
            if create.lower() == 'y':
                name = input("نام کاربر: ").strip()
                user_id = lm.register_user(mobile, name)
                user = session.query(User).filter(User.id == user_id).first()
            else:
                return
        
        print(f"\n✅ کاربر: {user.name} - {user.mobile}")
        print("\n📋 انتخاب پلن:")
        print("  1. آزمایشی (50 سند - 1 ماه)")
        print("  2. ماهانه (نامحدود)")
        print("  3. سه ماهه (نامحدود)")
        print("  4. شش ماهه (نامحدود)")
        print("  5. سالانه (نامحدود)")
        
        choice = input("\nانتخاب کنید (1-5): ").strip()
        plan_map = {
            "1": "free_trial",
            "2": "monthly",
            "3": "quarterly",
            "4": "semi_annual",
            "5": "annual"
        }
        plan_type = plan_map.get(choice, "free_trial")
        
        # صدور لایسنس
        license_key = lm.generate_license_key(user.id, plan_type)
        
        print(f"\n✅ لایسنس با موفقیت صادر شد!")
        print(f"   کلید لایسنس: {license_key}")
        print(f"   کاربر: {user.name}")
        print(f"   پلن: {plan_type}")
        
    finally:
        session.close()

if __name__ == "__main__":
    give_free_license()