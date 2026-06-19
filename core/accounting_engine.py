# core/accounting_engine.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func
from database.models import init_db, Account, JournalEntry, JournalLine, Customer, Vendor, BusinessType
from datetime import datetime
from typing import Any, List, Tuple, Dict, Optional

class AccountingEngine:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
    
    def validate_phone(self, phone: str) -> bool:
        """اعتبارسنجی شماره موبایل ایران"""
        mobile_pattern = r'^09[0-9]{9}$'
        return bool(re.match(mobile_pattern, phone))
    
    def validate_landline(self, phone: str) -> bool:
        """اعتبارسنجی شماره تلفن ثابت (پیش‌شماره + 8 رقم)"""
        landline_pattern = r'^0[0-9]{2,3}[0-9]{8}$'
        return bool(re.match(landline_pattern, phone))
    
    def validate_customer_name(self, name: str) -> bool:
        """اعتبارسنجی نام مشتری (نباید فقط عدد باشد)"""
        if not name or len(name.strip()) < 2:
            return False
        if name.strip().isdigit():
            return False
        return True
    
    def add_customer(self, name: str, mobile: str = "", phone: str = "") -> int:
        """ثبت مشتری جدید با اعتبارسنجی"""
        if not self.validate_customer_name(name):
            raise ValueError("❌ نام مشتری معتبر نیست. نام نباید فقط عدد باشد و حداقل ۲ کاراکتر باید داشته باشد.")
        
        is_mobile_valid = self.validate_phone(mobile) if mobile else False
        is_landline_valid = self.validate_landline(phone) if phone else False
        
        if not is_mobile_valid and not is_landline_valid:
            raise ValueError("❌ شماره تماس معتبر نیست.\nموبایل باید با 09 شروع شود و 11 رقم باشد.\nتلفن ثابت باید شامل پیش‌شماره و 8 رقم باشد (مثال: 02112345678).")
        
        session = self.Session()
        try:
            customer = Customer(
                name=name.strip(),
                phone=phone if is_landline_valid else "",
                mobile=mobile if is_mobile_valid else ""
            )
            session.add(customer)
            session.commit()
            print(f"✅ مشتری {name} با کد {customer.id} ثبت شد.")
            return customer.id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def add_vendor(self, name: str, phone: str = "", economic_code: str = "") -> int:
        session = self.Session()
        try:
            vendor = Vendor(name=name, phone=phone, economic_code=economic_code)
            session.add(vendor)
            session.commit()
            print(f"✅ فروشنده {name} با کد {vendor.id} ثبت شد.")
            return vendor.id
        finally:
            session.close()
    
    def create_voucher(self, date: datetime, description: str, lines: List[Tuple[str, float, str]], reference_no: Optional[str] = None) -> int:
        total_debit = sum(amt for _, amt, side in lines if side == 'debit')
        total_credit = sum(amt for _, amt, side in lines if side == 'credit')
        
        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(f"❌ خطا: جمع بدهکار ({total_debit:,.0f}) با بستانکار ({total_credit:,.0f}) برابر نیست.")
        
        session = self.Session()
        try:
            entry = JournalEntry(
                date=date,
                description=description,
                reference_no=reference_no,
                created_at=datetime.now()
            )
            session.add(entry)
            session.flush()
            
            for account_code, amount, side in lines:
                account = session.query(Account).filter_by(code=account_code).first()
                if not account:
                    raise ValueError(f"حساب با کد {account_code} یافت نشد.")
                
                line = JournalLine(
                    entry_id=entry.id,
                    account_id=account.id,
                    side=side,
                    amount=amount,
                    description=description[:200]
                )
                session.add(line)
            
            session.commit()
            print(f"✅ سند شماره {entry.id} با موفقیت ثبت شد.")
            return entry.id
            
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def get_trial_balance(self, business_type: Optional[str] = None) -> List[Any]:
        session = self.Session()
        try:
            query = session.query(
                Account.code,
                Account.name,
                Account.type,
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'debit'), 0).label('total_debit'),
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'credit'), 0).label('total_credit')
            ).outerjoin(JournalLine)
            
            if business_type:
                query = query.join(BusinessType).filter(BusinessType.name == business_type)
            
            results = query.group_by(Account.id, Account.code, Account.name, Account.type).all()
            return results
        finally:
            session.close()
    
    def get_all_customers(self) -> List[Any]:
        session = self.Session()
        try:
            return session.query(Customer).all()
        finally:
            session.close()

    def get_profit_loss(self, business_type: Optional[str] = None) -> List[Any]:
        """گزارش سود و زیان - برگشت حساب‌های درآمد و هزینه با مانده"""
        session = self.Session()
        try:
            query = session.query(
                Account.code,
                Account.name,
                Account.type,
                (
                    func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'credit'), 0) -
                    func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'debit'), 0)
                ).label('balance')
            ).outerjoin(JournalLine, JournalLine.account_id == Account.id
            ).filter(Account.type.in_(['income', 'expense'])
            )

            if business_type:
                query = query.join(BusinessType).filter(BusinessType.name == business_type)

            results = query.group_by(Account.id, Account.code, Account.name, Account.type).all()
            return results
        finally:
            session.close()

    def get_balance_sheet(self, business_type: Optional[str] = None) -> Dict:
        """گزارش ترازنامه - برگشت دارایی‌ها، بدهی‌ها و سرمایه"""
        session = self.Session()
        try:
            account_types = {'asset': 'debit', 'liability': 'credit', 'equity': 'credit'}
            result: Dict = {"assets": [], "liabilities": [], "equity": []}

            for acct_type, balance_side in account_types.items():
                if balance_side == 'debit':
                    balance_expr = (
                        func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'debit'), 0) -
                        func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'credit'), 0)
                    ).label('balance')
                else:
                    balance_expr = (
                        func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'credit'), 0) -
                        func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'debit'), 0)
                    ).label('balance')

                query = session.query(
                    Account.code,
                    Account.name,
                    balance_expr
                ).outerjoin(JournalLine, JournalLine.account_id == Account.id
                ).filter(Account.type == acct_type)

                if business_type:
                    query = query.join(BusinessType).filter(BusinessType.name == business_type)

                rows = query.group_by(Account.id, Account.code, Account.name).all()

                key = acct_type + 's' if acct_type != 'equity' else 'equity'
                result[key] = [
                    {"code": r.code, "name": r.name, "balance": r.balance}
                    for r in rows
                ]

            result["total_assets"] = sum(item["balance"] for item in result["assets"])
            result["total_liabilities"] = sum(item["balance"] for item in result["liabilities"])
            result["total_equity"] = sum(item["balance"] for item in result["equity"])
            return result
        finally:
            session.close()

    def get_journal(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """گزارش دفتر روزنامه - برگشت سندهای حسابداری به همراه ردیف‌ها"""
        session = self.Session()
        try:
            entries = session.query(JournalEntry).order_by(JournalEntry.id.desc()).limit(limit).offset(offset).all()
            result = []
            for entry in entries:
                lines = session.query(
                    JournalLine.id,
                    JournalLine.side,
                    JournalLine.amount,
                    JournalLine.description,
                    Account.code,
                    Account.name
                ).join(Account, Account.id == JournalLine.account_id
                ).filter(JournalLine.entry_id == entry.id).all()

                result.append({
                    "id": entry.id,
                    "date": entry.date,
                    "description": entry.description,
                    "reference_no": entry.reference_no,
                    "created_at": entry.created_at,
                    "lines": [
                        {
                            "id": l.id,
                            "side": l.side,
                            "amount": l.amount,
                            "description": l.description,
                            "account_code": l.code,
                            "account_name": l.name
                        }
                        for l in lines
                    ]
                })
            return result
        finally:
            session.close()


if __name__ == "__main__":
    engine = AccountingEngine()
    print("✅ موتور حسابداری آماده است.")