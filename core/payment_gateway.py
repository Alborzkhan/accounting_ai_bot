# core/payment_gateway.py
import requests
import json
import hashlib
import secrets
from typing import Dict, Optional
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from database.license_models import Transaction

from config import ZARINPAL_MERCHANT_ID, ZARINPAL_CALLBACK_URL

ZARINPAL_REQUEST_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
ZARINPAL_VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
ZARINPAL_START_PAY = "https://www.zarinpal.com/pg/StartPay/"

class PaymentGateway:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self._load_config()

    def _load_config(self) -> None:
        """تنظیمات پنل ادمین (دیتابیس) را تازه می‌خواند تا تغییرات بدون ری‌استارت سرور اعمال شوند؛
        متغیرهای .env فقط fallback برای توسعه/سازگاری قدیمی‌اند."""
        settings = {}
        try:
            from core.platform_settings import PlatformSettingsManager
            settings = PlatformSettingsManager().get_all()
        except Exception:
            settings = {}
        self.merchant_id = settings.get("zarinpal_merchant_id") or ZARINPAL_MERCHANT_ID
        self.callback_url = settings.get("zarinpal_callback_url") or ZARINPAL_CALLBACK_URL

    def create_payment_request(self, user_id: int, amount: int, plan_type: str, description: str = "اشتراک حسابدار هوشمند", discount_code: str = "") -> Dict:
        """ایجاد درخواست پرداخت و دریافت لینک زرین‌پال"""
        self._load_config()

        # مبلغ به تومان (زرین‌پال به ریال نیاز داره)
        amount_rial = amount * 10

        data = {
            "merchant_id": self.merchant_id,
            "amount": amount_rial,
            "callback_url": self.callback_url,
            "description": f"{description} - پلن {plan_type}",
            "metadata": {
                "user_id": str(user_id),
                "plan_type": plan_type,
                "mobile": "",
                "email": ""
            }
        }
        
        try:
            response = requests.post(ZARINPAL_REQUEST_URL, json=data, timeout=10)
            response_data = response.json()
            
            if response_data.get("data", {}).get("code") == 100:
                authority = response_data["data"]["authority"]
                payment_url = ZARINPAL_START_PAY + authority
                
                # ذخیره تراکنش در دیتابیس
                self._save_transaction(user_id, amount, plan_type, authority, discount_code)
                
                return {
                    "success": True,
                    "payment_url": payment_url,
                    "authority": authority,
                    "message": "لینک پرداخت ساخته شد."
                }
            else:
                return {
                    "success": False,
                    "message": f"خطا در ساخت لینک پرداخت: {response_data.get('errors', {}).get('message', 'خطای ناشناخته')}"
                }
        except Exception as e:
            return {"success": False, "message": f"خطا در اتصال به زرین‌پال: {str(e)}"}
    
    def verify_payment(self, authority: str, status: str, user_id: Optional[int] = None, plan_type: Optional[str] = None) -> Dict:
        """تأیید نهایی پرداخت بعد از بازگشت کاربر"""
        self._load_config()

        if status != "OK":
            return {"success": False, "message": "پرداخت لغو شد یا ناموفق بود."}

        # پیدا کردن تراکنش در دیتابیس
        transaction = self._get_transaction_by_authority(authority)
        if not transaction:
            return {"success": False, "message": "تراکنش یافت نشد."}

        amount_rial = transaction.amount * 10

        data = {
            "merchant_id": self.merchant_id,
            "authority": authority,
            "amount": amount_rial
        }
        
        try:
            response = requests.post(ZARINPAL_VERIFY_URL, json=data, timeout=10)
            response_data = response.json()
            
            if response_data.get("data", {}).get("code") == 100:
                ref_id = response_data["data"]["ref_id"]
                
                # به‌روزرسانی تراکنش
                self._update_transaction(transaction.id, ref_id, True)
                
                # صدور لایسنس
                from core.license_manager import LicenseManager
                lm = LicenseManager()
                license_result = lm.confirm_transaction(transaction.id, ref_id)
                
                if license_result["success"]:
                    return {
                        "success": True,
                        "ref_id": ref_id,
                        "license_key": license_result["license_key"],
                        "message": f"✅ پرداخت موفق! لایسنس شما با موفقیت صادر شد.\nکد پیگیری: {ref_id}\nکلید لایسنس: {license_result['license_key']}"
                    }
                else:
                    return {
                        "success": False,
                        "ref_id": ref_id,
                        "message": f"پرداخت موفق بود ولی خطا در صدور لایسنس: {license_result.get('message', 'خطای ناشناخته')}"
                    }
            else:
                return {
                    "success": False,
                    "message": f"پرداخت ناموفق: {response_data.get('errors', {}).get('message', 'خطای ناشناخته')}"
                }
        except Exception as e:
            return {"success": False, "message": f"خطا در تأیید پرداخت: {str(e)}"}
    
    def _save_transaction(self, user_id: int, amount: int, plan_type: str, authority: str, discount_code: str = "") -> int:
        """ذخیره تراکنش در دیتابیس"""
        session = self.Session()
        try:
            # اصل: از مدل Transaction استفاده کن
            from database.license_models import Transaction
            transaction = Transaction(
                user_id=user_id,
                amount=amount,
                plan_type=plan_type,
                authority=authority,
                discount_code=discount_code or None,
                is_confirmed=False
            )
            session.add(transaction)
            session.commit()
            return transaction.id
        finally:
            session.close()
    
    def _get_transaction_by_authority(self, authority: str) -> Optional[Transaction]:
        session = self.Session()
        try:
            from database.license_models import Transaction
            return session.query(Transaction).filter(Transaction.authority == authority).first()
        finally:
            session.close()
    
    def _update_transaction(self, transaction_id: int, ref_id: str, is_confirmed: bool) -> None:
        session = self.Session()
        try:
            from database.license_models import Transaction
            transaction = session.query(Transaction).filter(Transaction.id == transaction_id).first()
            if transaction:
                transaction.ref_id = ref_id
                transaction.is_confirmed = is_confirmed
                transaction.paid_at = datetime.now()
                session.commit()
        finally:
            session.close()
    
    def test_connection(self) -> Dict:
        """برای دکمه «تست اتصال» در پنل ادمین: یک درخواست پرداخت آزمایشی (بدون ذخیره تراکنش) می‌سازد.
        این فقط یک authority/توکن می‌گیرد؛ تا کاربر واقعاً وارد صفحه پرداخت زرین‌پال نشود و تکمیلش نکند، هیچ مبلغی کسر نمی‌شود."""
        self._load_config()
        if not self.merchant_id:
            return {"success": False, "message": "Merchant ID زرین‌پال تنظیم نشده است."}
        try:
            response = requests.post(ZARINPAL_REQUEST_URL, json={
                "merchant_id": self.merchant_id,
                "amount": 1000,
                "callback_url": self.callback_url or "https://example.com/callback",
                "description": "تست اتصال زرین‌پال",
            }, timeout=10)
            data = response.json()
            if data.get("data", {}).get("code") == 100:
                return {"success": True, "message": "✅ اتصال به زرین‌پال با موفقیت برقرار شد."}
            return {"success": False, "message": f"❌ اتصال ناموفق: {data.get('errors', {}).get('message', 'نامشخص')}"}
        except Exception as e:
            return {"success": False, "message": f"❌ خطا در اتصال به زرین‌پال: {str(e)}"}

    def get_pricing_plans(self) -> Dict:
        """دریافت لیست پلن‌های قیمتی"""
        return {
            "monthly": {"name": "ماهانه", "price": 5000000, "months": 1, "discount": 0},
            "quarterly": {"name": "سه ماهه", "price": 13500000, "months": 3, "discount": 10},
            "semi_annual": {"name": "شش ماهه", "price": 24000000, "months": 6, "discount": 20},
            "annual": {"name": "سالانه", "price": 42000000, "months": 12, "discount": 30}
        }


if __name__ == "__main__":
    pg = PaymentGateway()
    plans = pg.get_pricing_plans()
    print("💰 پلن‌های اشتراک")
    for key, plan in plans.items():
        print(f"{plan['name']}: {plan['price']:,} تومان")