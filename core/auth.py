import sys, os

import re
import secrets
import hashlib
import logging
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from database.license_models import User, License

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
MOBILE_PATTERN = re.compile(r'^09\d{9}$')

# ========== JWT Configuration ==========
try:
    from config import JWT_SECRET_KEY, JWT_EXPIRY_HOURS
except ImportError:
    JWT_SECRET_KEY = ""
    JWT_EXPIRY_HOURS = 168


def _get_jwt_secret() -> str:
    """برمی‌گرداند JWT_SECRET_KEY، اگر خالی بود با یک مقدار پیش‌فرض اخطار می‌دهد."""
    key = JWT_SECRET_KEY.strip()
    if not key:
        logger.warning("⚠️ JWT_SECRET_KEY تنظیم نشده! از کلید پیش‌فرض ناایمن استفاده می‌شود. لطفاً در .env مقداردهی کنید.")
        key = "insecure-default-key-change-me-in-production"
    return key


def _get_jwt_expiry() -> timedelta:
    return timedelta(hours=int(JWT_EXPIRY_HOURS))


def create_jwt_token(user_id: int) -> str:
    """ایجاد توکن JWT با user_id و تاریخ انقضا."""
    payload = {
        "user_id": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + _get_jwt_expiry(),
        "type": "access",
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def verify_jwt_token(token: str) -> Optional[Dict]:
    """بررسی و دیکد کردن توکن JWT. در صورت انقضا یا نامعتبر بودن None برمی‌گرداند."""
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid JWT token")
        return None


class AuthManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.db_path = db_path
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)

    def request_otp(self, mobile: str) -> Dict:
        """تولید و ارسال کد تایید یک‌بارمصرف. اگر کاربر وجود نداشته باشد، در زمان تایید کد ثبت‌نام می‌شود."""
        if not MOBILE_PATTERN.match(mobile or ""):
            return {"success": False, "message": "شماره موبایل نامعتبر است."}

        # محدودیت نرخ OTP: حداکثر ۵ درخواست در ۱۰ دقیقه به ازای هر شماره
        from core.rate_limiter import check_rate_limit
        if not check_rate_limit(f"otp:{mobile}", max_requests=5, window_seconds=600):
            return {"success": False, "message": "تعداد درخواست‌های کد تایید بیش از حد مجاز است. ۱۰ دقیقه صبر کنید."}

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

            from core.sms_service import send_otp_sms, has_sms_credentials
            send_otp_sms(mobile, code)
            result = {"success": True, "message": "کد تایید برای شما ارسال شد."}
            if not has_sms_credentials():
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

            user_id = user.id
            # ایجاد توکن JWT به جای SHA-256
            token = create_jwt_token(user_id)
            # ذخیره توکن در دیتابیس برای سازگاری با کدهای قدیمی (botها)
            user.auth_token = token
            user.otp_hash = None
            user.otp_expires_at = None
            user.otp_attempts = 0
            session.commit()

            try:
                from database.license_models import License
                has_any_license = session.query(License).filter_by(user_id=user_id).first() is not None
                if not has_any_license:
                    from core.license_manager import LicenseManager
                    LicenseManager(self.db_path).generate_license_key(user_id, "free_trial")
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
        """بررسی توکن JWT و برگرداندن کاربر مربوطه.
        ابتدا JWT را بررسی می‌کند، در صورت失败 به جستجوی دیتابیس (سازگاری با عقب) fallback می‌کند."""
        payload = verify_jwt_token(token)
        if payload and "user_id" in payload:
            session = self.Session()
            try:
                return session.query(User).filter(User.id == payload["user_id"]).first()
            finally:
                session.close()
        # Fallback: جستجوی مستقیم در دیتابیس برای توکن‌های قدیمی (SHA-256)
        session = self.Session()
        try:
            return session.query(User).filter(User.auth_token == token).first()
        finally:
            session.close()

    def validate_session(self, token: str) -> Optional[int]:
        """تأیید اعتبار توکن JWT و برگرداندن user_id. بدون کوئری دیتابیس (سریع‌تر)."""
        payload = verify_jwt_token(token)
        if payload and "user_id" in payload:
            return payload["user_id"]
        # Fallback: بررسی در دیتابیس برای توکن‌های قدیمی
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

    def set_user_admin(self, user_id: int, is_admin: bool) -> Dict:
        session = self.Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"success": False, "message": "کاربر یافت نشد."}
            user.is_admin = is_admin
            session.commit()
            return {"success": True, "message": "دسترسی ادمین بروز شد."}
        finally:
            session.close()
