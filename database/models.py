# database/models.py
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import os

logger = logging.getLogger(__name__)

Base = declarative_base()

class BusinessType(Base):
    __tablename__ = 'business_types'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(20))
    parent_id = Column(Integer, ForeignKey('accounts.id'))
    business_type_id = Column(Integer, ForeignKey('business_types.id'))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

class Customer(Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))  # تلفن ثابت
    mobile = Column(String(20))  # موبایل
    national_id = Column(String(20))
    economic_code = Column(String(20))
    address = Column(String(300))
    business_type_id = Column(Integer, ForeignKey('business_types.id'))
    created_at = Column(DateTime, default=datetime.now)

class Vendor(Base):
    __tablename__ = 'vendors'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    economic_code = Column(String(20))
    created_at = Column(DateTime, default=datetime.now)

class PurchaseInvoice(Base):
    __tablename__ = 'purchase_invoices'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    # عمداً unique=True ندارد، دلیل مشابه ProformaInvoice.invoice_number
    invoice_number = Column(String(50), nullable=False)
    date = Column(DateTime, default=datetime.now)
    vendor_id = Column(Integer, ForeignKey('vendors.id'))
    subtotal = Column(Float, default=0)
    vat_rate = Column(Float, default=0)
    vat_amount = Column(Float, default=0)
    total = Column(Float, default=0)
    is_vat_applied = Column(Boolean, default=False)
    is_official = Column(Boolean, default=False)
    vendor_national_id = Column(String(30), nullable=True)
    vendor_economic_code = Column(String(30), nullable=True)
    description = Column(String(200))
    pdf_path = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)

class PurchaseItem(Base):
    __tablename__ = 'purchase_items'
    id = Column(Integer, primary_key=True)
    purchase_invoice_id = Column(Integer, ForeignKey('purchase_invoices.id'))
    description = Column(String(200), nullable=False)
    quantity = Column(Float, default=1)
    unit = Column(String(20), default="عدد")
    unit_price = Column(Float, default=0)
    total = Column(Float, default=0)

class JournalEntry(Base):
    __tablename__ = 'journal_entries'
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.now)
    description = Column(String(200))
    reference_no = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    user_id = Column(Integer, default=1)

class JournalLine(Base):
    __tablename__ = 'journal_lines'
    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey('journal_entries.id'))
    account_id = Column(Integer, ForeignKey('accounts.id'))
    side = Column(String(10))
    amount = Column(Float)
    description = Column(String(200))


class FiscalYearClosing(Base):
    """ثبت بستن سال مالی برای هر کاربر/کسب‌وکار - دوره‌های بسته‌شده دیگر قابل ثبت سند نیستند."""
    __tablename__ = 'fiscal_year_closings'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    fiscal_year_label = Column(String(20))  # مثلاً "1403"
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    closing_entry_id = Column(Integer, ForeignKey('journal_entries.id'), nullable=True)
    net_result = Column(Float, default=0)  # سود (مثبت) یا زیان (منفی) شناسایی‌شده
    closed_at = Column(DateTime, default=datetime.now)

class SellerProfile(Base):
    __tablename__ = 'seller_profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    company_name = Column(String(100), nullable=False)
    address = Column(String(300))
    phone = Column(String(20))
    mobile = Column(String(20))
    logo_path = Column(String(200))
    tax_id = Column(String(50))
    economic_code = Column(String(30), nullable=True)
    national_id = Column(String(30), nullable=True)
    company_registration_number = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class ProformaInvoice(Base):
    __tablename__ = 'proforma_invoices'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    # توجه: invoice_number عمداً unique=True ندارد چون شماره‌گذاری به‌ازای هر کاربر/کسب‌وکار جداگانه است
    # (مثلاً دو کاربر مختلف می‌توانند هرکدام شماره INV-202406-0001 داشته باشند).
    invoice_number = Column(String(50), nullable=False)
    date = Column(DateTime, default=datetime.now)
    customer_id = Column(Integer, ForeignKey('customers.id'))
    seller_id = Column(Integer, ForeignKey('seller_profiles.id'))
    subtotal = Column(Float, default=0)
    vat_rate = Column(Float, default=0)
    vat_amount = Column(Float, default=0)
    total = Column(Float, default=0)
    is_vat_applied = Column(Boolean, default=True)
    is_official = Column(Boolean, default=False)
    buyer_national_id = Column(String(30), nullable=True)
    buyer_economic_code = Column(String(30), nullable=True)
    description = Column(String(200))
    pdf_path = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)

class InvoiceItem(Base):
    __tablename__ = 'invoice_items'
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('proforma_invoices.id'))
    description = Column(String(200), nullable=False)
    quantity = Column(Float, default=1)
    unit = Column(String(20), default="عدد")
    unit_price = Column(Float, default=0)
    total = Column(Float, default=0)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True)
    unit = Column(String(20), default="عدد")
    price = Column(Float, default=0)
    category = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)

class BusinessProfile(Base):
    __tablename__ = 'business_profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    business_name = Column(String(100))
    business_type = Column(String(50))
    industry = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class ProductCategory(Base):
    __tablename__ = 'product_categories'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey('product_categories.id'))
    business_type = Column(String(50))
    keywords = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)

class Business(Base):
    __tablename__ = 'businesses'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50))
    user_id = Column(Integer)
    currency = Column(String(10), default='IRT')
    vat_rate = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    license_key = Column(String(100), unique=True)
    is_active = Column(Boolean, default=True)


def _ensure_columns(engine, table_name, column_defs):
    """افزودن ستون‌های جدید به جدول موجود (بدون نیاز به ابزار migration)"""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for col_name, col_ddl in column_defs:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_ddl}"))


def _drop_unique_constraint_on_invoice_number(engine, table_name):
    """جدول‌های قدیمی (نسخه تک‌کاربره) محدودیت UNIQUE سراسری روی invoice_number داشتند که با
    شماره‌گذاری مستقل به‌ازای هر کاربر ناسازگار است. این تابع جدول را بدون آن محدودیت بازسازی می‌کند،
    با حفظ کامل داده‌های موجود."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    with engine.connect() as conn:
        row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:t"), {"t": table_name}).fetchone()
    if not row or not row[0] or "UNIQUE" not in row[0].upper():
        return

    columns = inspector.get_columns(table_name)
    col_names = [c["name"] for c in columns]
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} RENAME TO {table_name}_old"))
        Base.metadata.tables[table_name].create(conn)
        cols_csv = ", ".join(col_names)
        conn.execute(text(f"INSERT INTO {table_name} ({cols_csv}) SELECT {cols_csv} FROM {table_name}_old"))
        conn.execute(text(f"DROP TABLE {table_name}_old"))
    logger.info("محدودیت UNIQUE سراسری از ستون invoice_number جدول %s حذف شد.", table_name)


def init_db(db_path="accounting.db"):
    """ایجاد دیتابیس و جداول"""
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    _drop_unique_constraint_on_invoice_number(engine, "proforma_invoices")
    _drop_unique_constraint_on_invoice_number(engine, "purchase_invoices")
    # ایجاد جداول لایسنس و کاربران
    from database.license_models import Base as LicenseBase
    LicenseBase.metadata.create_all(engine)

    # افزودن ستون‌های جدید به جدول users در صورت ارتقا از نسخه قبلی (بدون Alembic)
    _ensure_columns(engine, "users", [
        ("otp_hash", "VARCHAR(64)"),
        ("otp_expires_at", "DATETIME"),
        ("otp_attempts", "INTEGER DEFAULT 0"),
        ("otp_requested_at", "DATETIME"),
        ("company_registration_number", "VARCHAR(50)"),
    ])
    _ensure_columns(engine, "seller_profiles", [
        ("user_id", "INTEGER"),
        ("economic_code", "VARCHAR(30)"),
        ("national_id", "VARCHAR(30)"),
        ("company_registration_number", "VARCHAR(50)"),
    ])
    _ensure_columns(engine, "proforma_invoices", [
        ("user_id", "INTEGER"),
        ("is_official", "BOOLEAN DEFAULT 0"),
        ("buyer_national_id", "VARCHAR(30)"),
        ("buyer_economic_code", "VARCHAR(30)"),
    ])
    _ensure_columns(engine, "transactions", [
        ("discount_code", "VARCHAR(30)"),
    ])

    Session = sessionmaker(bind=engine)
    session = Session()

    # اضافه کردن پلن‌های پیش‌فرض قیمت‌گذاری (فقط اگر قبلاً ایجاد نشده باشند)
    from database.license_models import PricingPlan
    default_plans = [
        ("free_trial", "آزمایشی", 0, 1, 50, "۵۰ سند اول رایگان"),
        ("monthly", "ماهانه", 5000000, 1, 0, "نامحدود - ماهانه"),
        ("quarterly", "سه ماهه", 13500000, 3, 0, "نامحدود - سه ماهه (۱۰٪ تخفیف)"),
        ("semi_annual", "شش ماهه", 24000000, 6, 0, "نامحدود - شش ماهه (۲۰٪ تخفیف)"),
        ("annual", "سالانه", 42000000, 12, 0, "نامحدود - سالانه (۳۰٪ تخفیف)"),
    ]
    for plan_key, name, price, months, max_vouchers, description in default_plans:
        if not session.query(PricingPlan).filter_by(plan_key=plan_key).first():
            session.add(PricingPlan(
                plan_key=plan_key, name=name, price=price, months=months,
                max_vouchers=max_vouchers, description=description
            ))
    session.commit()

    # اضافه کردن نوع‌های کسب‌وکار
    business_types = [
        ('بازرگانی', 'خرید و فروش کالا'),
        ('تولیدی', 'تولید محصولات'),
        ('خدماتی', 'ارائه خدمات'),
        ('پیمانکاری', 'پروژه‌های پیمانکاری')
    ]
    
    for bt_name, bt_desc in business_types:
        if not session.query(BusinessType).filter_by(name=bt_name).first():
            session.add(BusinessType(name=bt_name, description=bt_desc))
    
    session.commit()
    
    # اضافه کردن حساب‌های پیش‌فرض
    biz_types = {bt.name: bt for bt in session.query(BusinessType).all()}
    
    default_accounts = {
        'بازرگانی': [
            ('1001', 'صندوق', 'asset'),
            ('1002', 'بانک', 'asset'),
            ('1101', 'بدهکاران تجاری', 'asset'),
            ('1201', 'موجودی کالا', 'asset'),
            ('2001', 'بستانکاران تجاری', 'liability'),
            ('3001', 'سرمایه', 'equity'),
            ('4001', 'فروش کالا', 'income'),
            ('5001', 'بهای تمام شده کالای فروش رفته', 'expense'),
            ('5002', 'هزینه حمل', 'expense'),
        ],
        'تولیدی': [
            ('1001', 'صندوق', 'asset'),
            ('1002', 'بانک', 'asset'),
            ('1101', 'بدهکاران تجاری', 'asset'),
            ('1202', 'مواد اولیه', 'asset'),
            ('1203', 'کالای در جریان تولید', 'asset'),
            ('1301', 'ماشین‌آلات', 'asset'),
            ('2001', 'بستانکاران تجاری', 'liability'),
            ('3001', 'سرمایه', 'equity'),
            ('4001', 'فروش محصولات', 'income'),
            ('5001', 'بهای تمام شده تولید', 'expense'),
        ],
        'خدماتی': [
            ('1001', 'صندوق', 'asset'),
            ('1002', 'بانک', 'asset'),
            ('1101', 'بدهکاران خدمات', 'asset'),
            ('2001', 'بستانکاران', 'liability'),
            ('3001', 'سرمایه', 'equity'),
            ('4001', 'درآمد خدمات', 'income'),
            ('5001', 'هزینه حقوق', 'expense'),
            ('5002', 'هزینه اجاره', 'expense'),
        ],
        'پیمانکاری': [
            ('1001', 'صندوق', 'asset'),
            ('1002', 'بانک', 'asset'),
            ('1101', 'بدهکاران پروژه', 'asset'),
            ('1204', 'پروژه‌های در دست اجرا', 'asset'),
            ('2001', 'بستانکاران پیمانکاری', 'liability'),
            ('3001', 'سرمایه', 'equity'),
            ('4001', 'درآمد پیمانکاری', 'income'),
            ('5001', 'هزینه مستقیم پیمان', 'expense'),
        ]
    }
    
    for biz_name, accounts in default_accounts.items():
        biz = biz_types.get(biz_name)
        if biz:
            for code, name, acc_type in accounts:
                if not session.query(Account).filter_by(code=code).first():
                    session.add(Account(
                        code=code,
                        name=name,
                        type=acc_type,
                        business_type_id=biz.id
                    ))
    
    session.commit()
    session.close()
    logger.info("دیتابیس و جداول با موفقیت ایجاد شدند.")
    return engine


if __name__ == "__main__":
    init_db()