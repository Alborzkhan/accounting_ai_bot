# test_core.py
from core.accounting_engine import AccountingEngine
from datetime import datetime

print("🚀 شروع تست هسته حسابداری دوبل...")
print("-" * 50)

engine = AccountingEngine()

# ثبت سند خرید
try:
    entry_id = engine.create_voucher(
        date=datetime.now(),
        description="خرید کالا از شرکت آذر به مبلغ 5,000,000 ریال",
        lines=[
            ('1201', 5000000, 'debit'),   # موجودی کالا بدهکار
            ('2001', 5000000, 'credit')   # بستانکاران تجاری بستانکار
        ]
    )
    print(f"✅ سند خرید ثبت شد - شماره: {entry_id}")
    
    # ثبت سند فروش
    entry_id2 = engine.create_voucher(
        date=datetime.now(),
        description="فروش کالا به آقای کریمی",
        lines=[
            ('1101', 5000000, 'debit'),   # بدهکاران تجاری بدهکار
            ('4001', 5000000, 'credit')   # فروش کالا بستانکار
        ]
    )
    print(f"✅ سند فروش ثبت شد - شماره: {entry_id2}")
    
    # ثبت مشتری جدید
    cust_id = engine.add_customer("علی کریمی", "09127778888", "1234567890", "تهران - خیابان آزادی")
    print(f"✅ مشتری ثبت شد - کد: {cust_id}")
    
    # ثبت فروشنده
    vendor_id = engine.add_vendor("شرکت آذر", "02112345678", "1234567890")
    print(f"✅ فروشنده ثبت شد - کد: {vendor_id}")
    
except Exception as e:
    print(f"❌ خطا: {e}")

# نمایش تراز آزمایشی
print("\n" + "=" * 60)
print("📊 تراز آزمایشی:")
print("=" * 60)
print(f"{'کد':<10} {'نام حساب':<30} {'بدهکار':<15} {'بستانکار':<15}")
print("-" * 70)

for row in engine.get_trial_balance():
    if row.total_debit != 0 or row.total_credit != 0:
        print(f"{row.code:<10} {row.name:<30} {row.total_debit:<15,.0f} {row.total_credit:<15,.0f}")

print("\n✅ تست کامل شد.")