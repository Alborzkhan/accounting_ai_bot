# core/license_manager.py

from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from database.license_models import User, License, Transaction, PricingPlan, DiscountCode
from database.models import JournalEntry
import hashlib
import secrets
import jdatetime
from typing import Optional

class LicenseManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
    
    def generate_license_key(self, user_id: int, plan_type: str) -> str:
        """تولید لایسنس یکتا برای کاربر (مدت و سقف سند از جدول پلن‌های قیمت‌گذاری خوانده می‌شود)"""
        end_date = datetime.now()

        plan_session = self.Session()
        try:
            plan = plan_session.query(PricingPlan).filter_by(plan_key=plan_type).first()
            months = plan.months if plan else 1
            max_vouchers = plan.max_vouchers if plan else 0
        finally:
            plan_session.close()

        end_date += timedelta(days=30 * months)

        random_part = secrets.token_hex(8)
        license_key = hashlib.sha256(
            f"{user_id}{plan_type}{random_part}{datetime.now()}".encode()
        ).hexdigest()[:16].upper()
        
        session = self.Session()
        try:
            session.query(License).filter(
                License.user_id == user_id,
                License.is_active == True
            ).update({"is_active": False})
            
            license = License(
                user_id=user_id,
                license_key=license_key,
                plan_type=plan_type,
                end_date=end_date,
                is_active=True,
                max_vouchers=max_vouchers
            )
            session.add(license)
            session.commit()
            
            return license_key
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def count_user_vouchers(self, user_id: int) -> int:
        session = self.Session()
        try:
            return session.query(JournalEntry).filter(
                JournalEntry.user_id == user_id
            ).count()
        finally:
            session.close()

    def check_license(self, user_id: int) -> dict:
        """بررسی اعتبار لایسنس کاربر"""
        session = self.Session()
        try:
            license = session.query(License).filter(
                License.user_id == user_id,
                License.is_active == True
            ).first()
            
            if not license:
                return {"is_valid": False, "message": "لایسنس فعالی یافت نشد."}
            
            today = datetime.now()
            if license.end_date is None:
                return {"is_valid": False, "message": "لایسنس نامعتبر است (تاریخ پایان ندارد)."}
            days_left = (license.end_date - today).days
            
            if days_left < 0:
                license.is_active = False
                session.commit()
                return {"is_valid": False, "message": "لایسنس شما منقضی شده است."}
            
            shamsi_end = jdatetime.date.fromgregorian(date=license.end_date)
            used = self.count_user_vouchers(user_id)
            
            return {
                "is_valid": True,
                "license_key": license.license_key,
                "plan_type": license.plan_type,
                "end_date": shamsi_end.strftime('%Y/%m/%d'),
                "days_left": days_left,
                "max_vouchers": license.max_vouchers,
                "used_vouchers": used,
                "message": f"لایسنس شما تا {shamsi_end.strftime('%Y/%m/%d')} اعتبار دارد."
            }
        finally:
            session.close()
    
    def register_user(self, mobile: str, name: str = "", business_name: str = "", business_type: str = "", industry: str = "") -> int:
        """ثبت نام کاربر جدید"""
        session = self.Session()
        try:
            user = session.query(User).filter(User.mobile == mobile).first()
            if user:
                return user.id
            
            user = User(
                mobile=mobile,
                name=name,
                business_name=business_name,
                business_type=business_type,
                industry=industry
            )
            session.add(user)
            session.commit()
            
            # لایسنس آزمایشی (50 سند رایگان)
            self.generate_license_key(user.id, "free_trial")
            
            return user.id
        finally:
            session.close()
    
    def record_transaction(self, user_id: int, amount: int, plan_type: str, authority: Optional[str] = None, payment_method: str = "manual") -> dict:
        """ثبت تراکنش پرداخت (زرین‌پال یا دستی)"""
        session = self.Session()
        try:
            transaction = Transaction(
                user_id=user_id,
                amount=amount,
                plan_type=plan_type,
                authority=authority,
                payment_method=payment_method,
                is_confirmed=False
            )
            session.add(transaction)
            session.commit()
            
            return {"success": True, "transaction_id": transaction.id, "authority": authority}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()
    
    def confirm_transaction(self, transaction_id: int, ref_id: str = "", confirmed_by: str = "system") -> dict:
        """تأیید تراکنش و صدور لایسنس"""
        session = self.Session()
        try:
            transaction = session.query(Transaction).filter(
                Transaction.id == transaction_id
            ).first()
            
            if not transaction:
                return {"success": False, "message": "تراکنش یافت نشد."}
            
            if transaction.is_confirmed:
                return {"success": False, "message": "این تراکنش قبلاً تأیید شده است."}
            
            transaction.is_confirmed = True
            transaction.ref_id = ref_id
            transaction.confirmed_by = confirmed_by
            transaction.paid_at = datetime.now()
            
            # صدور لایسنس
            license_key = self.generate_license_key(transaction.user_id, transaction.plan_type)
            
            session.commit()
            
            return {
                "success": True,
                "user_id": transaction.user_id,
                "license_key": license_key,
                "plan_type": transaction.plan_type,
                "message": f"✅ لایسنس {transaction.plan_type} با موفقیت صادر شد."
            }
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()
    
    def can_create_voucher(self, user_id: int) -> dict:
        status = self.check_license(user_id)
        if not status["is_valid"]:
            return {"allowed": False, "message": status["message"]}
        if status["max_vouchers"] > 0 and status["used_vouchers"] >= status["max_vouchers"]:
            return {"allowed": False, "message": f"تعداد سندهای مجاز شما ({status['max_vouchers']} سند) به پایان رسیده. لطفاً اشتراک خود را تمدید کنید."}
        return {"allowed": True, "message": ""}

    def get_pricing_plans(self, include_inactive: bool = False) -> dict:
        """دریافت لیست پلن‌های قیمتی از دیتابیس (قابل ویرایش توسط ادمین)"""
        session = self.Session()
        try:
            query = session.query(PricingPlan)
            if not include_inactive:
                query = query.filter(PricingPlan.is_active == True)
            plans = query.order_by(PricingPlan.months).all()
            return {
                p.plan_key: {
                    "name": p.name, "price": p.price, "months": p.months,
                    "vouchers": p.max_vouchers, "description": p.description or "",
                    "is_active": p.is_active,
                }
                for p in plans
            }
        finally:
            session.close()

    def update_pricing_plan(self, plan_key: str, **fields) -> dict:
        """ویرایش یک پلن قیمتی توسط ادمین"""
        session = self.Session()
        try:
            plan = session.query(PricingPlan).filter_by(plan_key=plan_key).first()
            if not plan:
                return {"success": False, "message": "پلن یافت نشد."}
            for key, value in fields.items():
                if hasattr(plan, key) and value is not None:
                    setattr(plan, key, value)
            session.commit()
            return {"success": True, "message": "پلن بروزرسانی شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def list_discount_codes(self) -> list:
        session = self.Session()
        try:
            codes = session.query(DiscountCode).order_by(DiscountCode.id.desc()).all()
            return [{
                "id": c.id, "code": c.code or "", "title": c.title or "",
                "discount_type": c.discount_type, "discount_value": c.discount_value,
                "applicable_plan": c.applicable_plan or "", "is_active": c.is_active,
                "used_count": c.used_count, "max_uses": c.max_uses,
                "start_date": jdatetime.date.fromgregorian(date=c.start_date).strftime("%Y/%m/%d") if c.start_date else "",
                "end_date": jdatetime.date.fromgregorian(date=c.end_date).strftime("%Y/%m/%d") if c.end_date else "",
            } for c in codes]
        finally:
            session.close()

    def create_discount_code(self, code: str, title: str, discount_type: str, discount_value: float,
                              applicable_plan: str = "", start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None, max_uses: int = 0) -> dict:
        session = self.Session()
        try:
            if code and session.query(DiscountCode).filter_by(code=code).first():
                return {"success": False, "message": "این کد تخفیف از قبل وجود دارد."}
            entry = DiscountCode(
                code=code or None, title=title, discount_type=discount_type,
                discount_value=discount_value, applicable_plan=applicable_plan or None,
                start_date=start_date, end_date=end_date, max_uses=max_uses,
            )
            session.add(entry)
            session.commit()
            return {"success": True, "message": "کد تخفیف ایجاد شد.", "id": entry.id}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def toggle_discount_code(self, code_id: int) -> dict:
        session = self.Session()
        try:
            entry = session.query(DiscountCode).filter_by(id=code_id).first()
            if not entry:
                return {"success": False, "message": "کد یافت نشد."}
            entry.is_active = not entry.is_active
            session.commit()
            return {"success": True, "is_active": entry.is_active}
        finally:
            session.close()

    def validate_and_apply_discount(self, code: str, plan_key: str, base_price: int) -> dict:
        """اعتبارسنجی کد تخفیف برای یک پلن مشخص و محاسبه قیمت نهایی"""
        session = self.Session()
        try:
            entry = session.query(DiscountCode).filter_by(code=code, is_active=True).first()
            if not entry:
                return {"success": False, "message": "کد تخفیف نامعتبر است."}
            now = datetime.now()
            if entry.start_date and now < entry.start_date:
                return {"success": False, "message": "این کد تخفیف هنوز فعال نشده است."}
            if entry.end_date and now > entry.end_date:
                return {"success": False, "message": "این کد تخفیف منقضی شده است."}
            if entry.max_uses and entry.used_count >= entry.max_uses:
                return {"success": False, "message": "ظرفیت استفاده از این کد تخفیف تمام شده است."}
            if entry.applicable_plan and entry.applicable_plan != plan_key:
                return {"success": False, "message": "این کد تخفیف برای این پلن قابل استفاده نیست."}

            if entry.discount_type == "percent":
                discount_amount = base_price * (entry.discount_value / 100)
            else:
                discount_amount = entry.discount_value
            final_price = max(int(base_price - discount_amount), 0)

            entry.used_count += 1
            session.commit()

            return {"success": True, "final_price": final_price, "discount_amount": int(discount_amount)}
        finally:
            session.close()


    def get_pricing_message(self) -> str:
        """دریافت متن قیمت‌گذاری برای نمایش به کاربر"""
        plans = self.get_pricing_plans()
        return f"""
💰 **پلن‌های اشتراک حسابدار هوشمند**

🎁 **پلن آزمایشی رایگان:** {plans['free_trial']['description']}

📋 **پلن ماهانه:** {plans['monthly']['price']:,} تومان
📋 **پلن سه‌ماهه:** {plans['quarterly']['price']:,} تومان (معادل {plans['quarterly']['price']//3:,} تومان در ماه)
📋 **پلن شش‌ماهه:** {plans['semi_annual']['price']:,} تومان (معادل {plans['semi_annual']['price']//6:,} تومان در ماه)
📋 **پلن سالانه:** {plans['annual']['price']:,} تومان (معادل {plans['annual']['price']//12:,} تومان در ماه)

💳 **پرداخت آنلاین از طریق زرین‌پال**
🔐 پس از پرداخت، لایسنس شما بلافاصله صادر می‌شود.
        """
    
    def get_user_transactions(self, user_id: int, limit: int = 20) -> list:
        """دریافت تاریخچه تراکنش‌های کاربر"""
        session = self.Session()
        try:
            transactions = session.query(Transaction).filter(
                Transaction.user_id == user_id
            ).order_by(Transaction.id.desc()).limit(limit).all()
            
            result = []
            for t in transactions:
                result.append({
                    "id": t.id,
                    "amount": t.amount,
                    "plan_type": t.plan_type,
                    "payment_method": t.payment_method,
                    "is_confirmed": t.is_confirmed,
                    "ref_id": t.ref_id,
                    "paid_at": t.paid_at.strftime("%Y-%m-%d %H:%M:%S") if t.paid_at else None,
                    "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })
            return result
        finally:
            session.close()


if __name__ == "__main__":
    lm = LicenseManager()
    
    print("🔐 سیستم مدیریت لایسنس")
    print("=" * 40)
    
    # نمایش پلن‌ها
    print(lm.get_pricing_message())
    
    # ثبت نام کاربر جدید
    user_id = lm.register_user("09121112233", "کاربر تست", "فروشگاه گل‌نار", "بازرگانی", "لوازم آرایشی")
    print(f"✅ کاربر با کد {user_id} ثبت شد.")
    
    # بررسی لایسنس
    status = lm.check_license(user_id)
    print(f"\n📋 وضعیت لایسنس: {status['message']}")
    if status.get('max_vouchers', 0) > 0:
        print(f"   سقف اسناد رایگان: {status['max_vouchers']} سند")
    
    # ثبت تراکنش تست
    result = lm.record_transaction(user_id, 5000000, "monthly", authority="TEST_AUTHORITY")
    print(f"\n💳 ثبت تراکنش: {result}")