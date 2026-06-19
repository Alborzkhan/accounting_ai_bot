# database/license_models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    mobile = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    total_vouchers = Column(Integer, default=0)
    business_name = Column(String(100))
    business_type = Column(String(50))
    industry = Column(String(50))
    auth_token = Column(String(64), unique=True, nullable=True)
    is_admin = Column(Boolean, default=False)
    device_count = Column(Integer, default=0)
    telegram_id = Column(String(50), nullable=True, unique=True)
    bale_id = Column(String(50), nullable=True, unique=True)
    phone_office = Column(String(30), nullable=True)
    phone_mobile = Column(String(30), nullable=True)
    national_id = Column(String(30), nullable=True)
    economic_code = Column(String(30), nullable=True)
    address = Column(String(300), nullable=True)
    logo_path = Column(String(200), nullable=True)
    otp_hash = Column(String(64), nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    otp_attempts = Column(Integer, default=0)
    otp_requested_at = Column(DateTime, nullable=True)

class License(Base):
    __tablename__ = 'licenses'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    license_key = Column(String(100), unique=True)
    plan_type = Column(String(20))  # monthly, quarterly, semi_annual, annual, free_trial
    start_date = Column(DateTime, default=datetime.now)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    max_vouchers = Column(Integer, default=50)  # 0 = نامحدود

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Integer)  # مبلغ به تومان
    plan_type = Column(String(50))  # monthly, quarterly, semi_annual, annual
    authority = Column(String(100), unique=True, nullable=True)  # کد مرجع زرین‌پال
    ref_id = Column(String(100), nullable=True)  # کد پیگیری نهایی زرین‌پال
    payment_receipt = Column(String(200), nullable=True)  # مسیر فایل رسید (برای پرداخت دستی)
    payment_method = Column(String(20), default="manual")  # manual, zarinpal
    is_confirmed = Column(Boolean, default=False)
    confirmed_by = Column(String(100), nullable=True)  # نام ادمین تأییدکننده (برای پرداخت دستی)
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)