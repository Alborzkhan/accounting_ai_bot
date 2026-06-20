import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from database.license_models import User, License
from config import FARAPAYAMAK_USERNAME, FARAPAYAMAK_PASSWORD

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
MOBILE_PATTERN = re.compile(r'^09\d{9}$')


class AuthManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)

    def request_otp(self, mobile: str) -> Dict:
        """تولید و ارسال کد تایید یک‌بارمصرف. اگر کاربر وجود نداشته باشد، در زمان تایید کد ثبت‌نام می‌شود."""
        if not MOBILE_PATTERN.match(mobile or ""):
            return {"success": False, "message": "شماره موبایل نامعتبر است."}
        session = self.Session()
        try:
            user = session.query(User).filter(User.mobile == mobile).first()
            now = datetime.now()
            if user and user.otp_requested_at:
                elapsed = (now - user.otp_requested_at).total_seconds()
                if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                    wait = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                    return {"success": False, "message": f"لطفاً {wait} ثانیه دیگر دوباره تلاش کنید."}

            code = f"{secrets.randbelow(1_000_000):06d}"
            code_hash = hashlib.sha256(code.encode()).hexdigest()

            if not user:
                user = User(mobile=mobile)
                session.add(user)
                session.flush()

            user.otp_hash = code_hash
            user.otp_expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
            user.otp_attempts = 0
            user.otp_requested_at = now
            session.commit()

            from core.sms_service import send_otp_sms
            send_otp_sms(mobile, code)
            result = {"success": True, "message": "کد تایید برای شما ارسال شد."}
            if not FARAPAYAMAK_USERNAME or not FARAPAYAMAK_PASSWORD:
                # حالت توسعه: چون پیامک واقعی ارسال نمی‌شود، کد برای تست مستقیم در پاسخ برگردانده می‌شود.
                result["dev_code"] = code
                result["message"] = "حالت توسعه: پیامک واقعی متصل نیست، کد تایید مستقیماً نمایش داده می‌شود."
            return result
        except Exception:
            session.rollback()
            logger.exception("request_otp failed for mobile=%s", mobile)
            return {"success": False, "message": "خطا در ارسال کد تایید. لطفاً دوباره تلاش کنید."}
        finally:
            session.close()

    def verify_otp(self, mobile: str, code: str, name: str = "") -> Dict:
        """تایید کد یک‌بارمصرف و صدور توکن نشست. اگر کاربر تازه ثبت‌نام کرده، is_new=True برمی‌گردد."""
        session = self.Session()
        try:
            user = session.query(User).filter(User.mobile == mobile).first()
            if not user or not user.otp_hash or not user.otp_expires_at:
                return {"success": False, "message": "ابتدا کد تایید را درخواست کنید."}

            if datetime.now() > user.otp_expires_at:
                return {"success": False, "message": "کد تایید منقضی شده است. دوباره درخواست دهید."}

            if user.otp_attempts >= OTP_MAX_ATTEMPTS:
                return {"success": False, "message": "تعداد تلاش‌های مجاز شما تمام شده. دوباره کد بگیرید."}

            if hashlib.sha256((code or "").encode()).hexdigest() != user.otp_hash:
                user.otp_attempts += 1
                session.commit()
                return {"success": False, "message": "کد تایید نادرست است."}

            is_new = not user.name and user.created_at and (datetime.now() - user.created_at).total_seconds() < 60
            if name and not user.name:
                user.name = name

            token = hashlib.sha256(f"{user.id}{secrets.token_hex(16)}".encode()).hexdigest()
            user.auth_token = token
            user.otp_hash = None
            user.otp_expires_at = None
            user.otp_attempts = 0
            user_id = user.id
            session.commit()

            if is_new:
                try:
                    from core.license_manager import LicenseManager
                    LicenseManager().generate_license_key(user_id, "free_trial")
                except Exception:
                    logger.exception("free_trial license issuance failed for user_id=%s", user_id)

            return {"success": True, "user_id": user_id, "token": token, "is_new": is_new, "message": "ورود موفق."}
        except Exception:
            session.rollback()
            logger.exception("verify_otp failed for mobile=%s", mobile)
            return {"success": False, "message": "خطا در تایید کد."}
        finally:
            session.close()

    def get_user_by_token(self, token: str) -> Optional[User]:
        session = self.Session()
        try:
            return session.query(User).filter(User.auth_token == token).first()
        finally:
            session.close()

    def validate_session(self, token: str) -> Optional[int]:
        user = self.get_user_by_token(token)
        return user.id if user else None

    def link_telegram(self, user_id: int, telegram_id: str) -> dict:
        session = self.Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"success": False, "message": "کاربر یافت نشد."}
            existing = session.query(User).filter(User.telegram_id == telegram_id).first()
            if existing and existing.id != user_id:
                return {"success": False, "message": "این حساب تلگرام قبلاً به کاربر دیگری متصل شده است."}
            user.telegram_id = telegram_id
            session.commit()
            return {"success": True, "message": "حساب تلگرام متصل شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def link_bale(self, user_id: int, bale_id: str) -> dict:
        session = self.Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"success": False, "message": "کاربر یافت نشد."}
            existing = session.query(User).filter(User.bale_id == bale_id).first()
            if existing and existing.id != user_id:
                return {"success": False, "message": "این حساب بله قبلاً به کاربر دیگری متصل شده است."}
            user.bale_id = bale_id
            session.commit()
            return {"success": True, "message": "حساب بله متصل شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def get_user_by_telegram(self, telegram_id: str) -> Optional[int]:
        session = self.Session()
        try:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            return user.id if user else None
        finally:
            session.close()

    def get_user_profile(self, user_id: int) -> Optional[dict]:
        session = self.Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            return {
                "id": user.id, "name": user.name or "",
                "mobile": user.mobile,
                "business_name": user.business_name or "",
                "business_type": user.business_type or "",
                "phone_office": user.phone_office or "",
                "phone_mobile": user.phone_mobile or "",
                "national_id": user.national_id or "",
                "economic_code": user.economic_code or "",
                "company_registration_number": user.company_registration_number or "",
                "address": user.address or "",
                "logo_path": user.logo_path or "",
                "is_admin": user.is_admin
            }
        finally:
            session.close()

    def get_user_by_bale(self, bale_id: str) -> Optional[int]:
        session = self.Session()
        try:
            user = session.query(User).filter(User.bale_id == bale_id).first()
            return user.id if user else None
        finally:
            session.close()

    def get_or_create_user(self, mobile: str, name: str = "") -> int:
        session = self.Session()
        try:
            user = session.query(User).filter(User.mobile == mobile).first()
            if not user:
                user = User(mobile=mobile, name=name)
                session.add(user)
                session.commit()
            return user.id
        finally:
            session.close()

    def get_all_users(self) -> list:
        session = self.Session()
        try:
            users = session.query(User).order_by(User.id.desc()).limit(100).all()
            result = []
            for u in users:
                result.append({
                    "id": u.id, "name": u.name or "", "mobile": u.mobile,
                    "business_name": u.business_name or "", "business_type": u.business_type or "",
                    "is_admin": u.is_admin, "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else ""
                })
            return result
        finally:
            session.close()

    def update_user_profile(self, user_id: int, **kwargs) -> Dict:
        session = self.Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"success": False, "message": "کاربر یافت نشد."}
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            session.commit()
            return {"success": True, "message": "پروفایل بروز شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def is_user_admin(self, user_id: int) -> bool:
        session = self.Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            return user.is_admin if user else False
        finally:
            session.close()
