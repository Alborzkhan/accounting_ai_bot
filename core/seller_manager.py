# core/seller_manager.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import sessionmaker
from database.models import SellerProfile, init_db

class SellerManager:
    def __init__(self, user_id: int, db_path: str = "accounting.db") -> None:
        self.user_id = user_id
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
    
    def save_logo(self, logo_path: str, company_name: str) -> str:
        """ذخیره لوگو در پوشه static و برگرداندن مسیر"""
        static_dir = Path("static/logos")
        static_dir.mkdir(parents=True, exist_ok=True)
        
        # ایجاد نام فایل بر اساس نام شرکت
        safe_name = company_name.replace(" ", "_")
        ext = Path(logo_path).suffix
        dest_path = static_dir / f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        
        shutil.copy2(logo_path, dest_path)
        return str(dest_path)
    
    def create_or_update_profile(self, data: Dict) -> Dict:
        """ایجاد یا به روز رسانی پروفایل فروشنده"""
        session = self.Session()
        try:
            profile = session.query(SellerProfile).filter_by(user_id=self.user_id).first()

            if profile:
                # به روز رسانی
                for key, value in data.items():
                    if hasattr(profile, key) and value is not None:
                        setattr(profile, key, value)
                message = "پروفایل فروشنده با موفقیت به روز شد."
            else:
                # ایجاد جدید
                profile = SellerProfile(user_id=self.user_id, **data)
                session.add(profile)
                message = "پروفایل فروشنده با موفقیت ایجاد شد."
            
            session.commit()
            return {"success": True, "message": message, "data": profile}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {str(e)}"}
        finally:
            session.close()
    
    def get_profile(self) -> Optional[SellerProfile]:
        """دریافت پروفایل فروشنده"""
        session = self.Session()
        try:
            return session.query(SellerProfile).filter_by(user_id=self.user_id).first()
        finally:
            session.close()
    
    def setup_wizard(self) -> Dict:
        """راه‌اندازی اولیه پروفایل فروشنده با سوالات تعاملی"""
        print("\n" + "=" * 50)
        print("🏢 راه‌اندازی پروفایل فروشنده")
        print("=" * 50)
        print("این اطلاعات در پیش‌فاکتورها نمایش داده می‌شود.\n")
        
        data = {}
        data['company_name'] = input("📛 نام شرکت/فروشگاه: ").strip()
        data['address'] = input("📍 آدرس کامل: ").strip()
        data['phone'] = input("📞 تلفن ثابت: ").strip() or None
        data['mobile'] = input("📱 موبایل: ").strip()
        data['tax_id'] = input("🏷️ شناسه ملی/اقتصادی (اختیاری): ").strip() or None
        
        # سوال لوگو
        has_logo = input("آیا لوگو دارید؟ (y/n): ").strip().lower()
        if has_logo == 'y':
            logo_path = input("مسیر فایل لوگو را وارد کنید: ").strip()
            if os.path.exists(logo_path):
                data['logo_path'] = self.save_logo(logo_path, data['company_name'])
                print("✅ لوگو با موفقیت ذخیره شد.")
            else:
                print("⚠️ فایل لوگو یافت نشد. بعداً می‌توانید اضافه کنید.")
        
        result = self.create_or_update_profile(data)
        if result['success']:
            print(f"\n✅ {result['message']}")
        else:
            print(f"\n❌ {result['message']}")
        
        return result


if __name__ == "__main__":
    from database.models import User

    mobile = input("📱 موبایل کاربری که این پروفایل فروشنده برایش است: ").strip()
    _session = sessionmaker(bind=init_db("accounting.db"))()
    try:
        _user = _session.query(User).filter_by(mobile=mobile).first()
    finally:
        _session.close()
    if not _user:
        print(f"❌ کاربری با موبایل {mobile} یافت نشد.")
        sys.exit(1)

    manager = SellerManager(user_id=_user.id)

    # اگر پروفایل وجود نداشت، راه‌اندازی کن
    if not manager.get_profile():
        print("⚠️ پروفایل فروشنده یافت نشد. لطفاً اطلاعات را وارد کنید.")
        manager.setup_wizard()
    else:
        print("✅ پروفایل فروشنده قبلاً تنظیم شده است.")
        profile = manager.get_profile()
        print(f"\n🏢 نام شرکت: {profile.company_name}")
        print(f"📍 آدرس: {profile.address}")
        print(f"📞 تلفن: {profile.phone}")