# core/accounting_engine.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, case
from database.models import init_db, Account, JournalEntry, JournalLine, Customer, Vendor, BusinessType, FiscalYearClosing
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
            return vendor.id
        finally:
            session.close()
    
    def _assert_period_open(self, user_id: int, date: datetime) -> None:
        session = self.Session()
        try:
            latest_closing = session.query(FiscalYearClosing).filter(
                FiscalYearClosing.user_id == user_id
            ).order_by(FiscalYearClosing.period_end.desc()).first()
            if latest_closing and date <= latest_closing.period_end:
                raise ValueError(
                    f"❌ این تاریخ در دوره مالی بسته‌شده ({latest_closing.fiscal_year_label}) قرار دارد. "
                    "امکان ثبت سند در دوره بسته وجود ندارد."
                )
        finally:
            session.close()

    def create_voucher(
        self, date: datetime, description: str, lines: List[Tuple[str, float, str]],
        reference_no: Optional[str] = None, user_id: Optional[int] = None,
        customer_id: Optional[int] = None, vendor_id: Optional[int] = None,
    ) -> int:
        total_debit = sum(amt for _, amt, side in lines if side == 'debit')
        total_credit = sum(amt for _, amt, side in lines if side == 'credit')

        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(f"❌ خطا: جمع بدهکار ({total_debit:,.0f}) با بستانکار ({total_credit:,.0f}) برابر نیست.")

        if user_id is not None:
            self._assert_period_open(user_id, date)

        session = self.Session()
        try:
            entry = JournalEntry(
                date=date,
                description=description,
                reference_no=reference_no,
                created_at=datetime.now(),
                user_id=user_id if user_id is not None else 1,
                customer_id=customer_id,
                vendor_id=vendor_id,
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
            return entry.id

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def _get_or_create_retained_earnings_account(self, session) -> Account:
        """پیدا کردن یا ساخت حساب «سود (زیان) انباشته» — کدهای حساب در این پروژه بین چارت پیش‌فرض
        و راهنمای دسته‌بندی هوش مصنوعی یکسان نیستند، پس به کد ثابت تکیه نمی‌کنیم."""
        account = session.query(Account).filter(
            Account.type == 'equity', Account.name.like('%انباشته%')
        ).first()
        if account:
            return account
        code = "3900"
        n = 0
        while session.query(Account).filter_by(code=code).first():
            n += 1
            code = f"3900{n}"
        account = Account(code=code, name="سود (زیان) انباشته", type="equity")
        session.add(account)
        session.flush()
        return account

    def get_open_fiscal_years(self, user_id: int) -> List[Dict]:
        """آخرین دوره بسته‌شده و اولین تاریخ سند ثبت‌شده برای این کاربر (برای انتخاب بازه بستن سال بعدی)."""
        session = self.Session()
        try:
            last_closing = session.query(FiscalYearClosing).filter(
                FiscalYearClosing.user_id == user_id
            ).order_by(FiscalYearClosing.period_end.desc()).first()
            first_entry = session.query(JournalEntry).filter(
                JournalEntry.user_id == user_id
            ).order_by(JournalEntry.date.asc()).first()
            return {
                "last_closed_until": last_closing.period_end if last_closing else None,
                "last_fiscal_year_label": last_closing.fiscal_year_label if last_closing else None,
                "first_entry_date": first_entry.date if first_entry else None,
            }
        finally:
            session.close()

    def close_fiscal_year(self, user_id: int, period_start: datetime, period_end: datetime, fiscal_year_label: str) -> Dict:
        """بستن حساب‌های موقت (درآمد/هزینه) یک دوره مالی و انتقال نتیجه به سود/زیان انباشته.
        بعد از بستن، ثبت سند با تاریخ داخل این دوره یا قبل از آن دیگر ممکن نیست."""
        session = self.Session()
        try:
            overlapping = session.query(FiscalYearClosing).filter(
                FiscalYearClosing.user_id == user_id,
                FiscalYearClosing.period_end >= period_start
            ).first()
            if overlapping:
                return {"success": False, "message": f"این بازه با دوره بسته‌شده قبلی ({overlapping.fiscal_year_label}) تداخل دارد."}
            if period_end <= period_start:
                return {"success": False, "message": "تاریخ پایان دوره باید بعد از تاریخ شروع باشد."}

            rows = session.query(
                Account.code, Account.type,
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'debit'), 0).label('total_debit'),
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'credit'), 0).label('total_credit'),
            ).join(JournalLine, JournalLine.account_id == Account.id
            ).join(JournalEntry, JournalEntry.id == JournalLine.entry_id
            ).filter(
                Account.type.in_(['income', 'expense']),
                JournalEntry.user_id == user_id,
                JournalEntry.date >= period_start,
                JournalEntry.date <= period_end,
            ).group_by(Account.id, Account.code, Account.type).all()

            lines_to_post: List[Tuple[str, float, str]] = []
            net_result = 0.0
            for r in rows:
                if r.type == 'income':
                    balance = r.total_credit - r.total_debit
                    if abs(balance) > 0.01:
                        lines_to_post.append((r.code, abs(balance), 'debit' if balance > 0 else 'credit'))
                        net_result += balance
                else:
                    balance = r.total_debit - r.total_credit
                    if abs(balance) > 0.01:
                        lines_to_post.append((r.code, abs(balance), 'credit' if balance > 0 else 'debit'))
                        net_result -= balance

            if not lines_to_post:
                return {"success": False, "message": "هیچ مانده‌ای در حساب‌های درآمد/هزینه این بازه برای بستن یافت نشد."}

            retained_account = self._get_or_create_retained_earnings_account(session)
            session.commit()
            if abs(net_result) > 0.01:
                lines_to_post.append((retained_account.code, abs(net_result), 'credit' if net_result > 0 else 'debit'))

            entry_id = self.create_voucher(
                date=period_end,
                description=f"بستن حساب‌های موقت سال مالی {fiscal_year_label}",
                lines=lines_to_post,
                user_id=user_id,
            )

            closing = FiscalYearClosing(
                user_id=user_id,
                fiscal_year_label=fiscal_year_label,
                period_start=period_start,
                period_end=period_end,
                closing_entry_id=entry_id,
                net_result=net_result,
            )
            session.add(closing)
            session.commit()

            result_word = "سود" if net_result >= 0 else "زیان"
            return {
                "success": True,
                "message": f"✅ سال مالی {fiscal_year_label} بسته شد. {result_word} شناسایی‌شده: {abs(net_result):,.0f} تومان.",
                "net_result": net_result,
                "closing_entry_id": entry_id,
            }
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا در بستن سال مالی: {str(e)}"}
        finally:
            session.close()

    def get_trial_balance(self, business_type: Optional[str] = None, user_id: Optional[int] = None,
                           date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> List[Any]:
        session = self.Session()
        try:
            debit_conditions = [JournalLine.side == 'debit']
            credit_conditions = [JournalLine.side == 'credit']
            if user_id is not None:
                debit_conditions.append(JournalEntry.user_id == user_id)
                credit_conditions.append(JournalEntry.user_id == user_id)
            if date_from is not None:
                debit_conditions.append(JournalEntry.date >= date_from)
                credit_conditions.append(JournalEntry.date >= date_from)
            if date_to is not None:
                debit_conditions.append(JournalEntry.date <= date_to)
                credit_conditions.append(JournalEntry.date <= date_to)

            query = session.query(
                Account.code,
                Account.name,
                Account.type,
                func.coalesce(func.sum(JournalLine.amount).filter(*debit_conditions), 0).label('total_debit'),
                func.coalesce(func.sum(JournalLine.amount).filter(*credit_conditions), 0).label('total_credit')
            ).outerjoin(JournalLine, JournalLine.account_id == Account.id
            ).outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id)

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

    def get_monthly_summary(self, user_id: int, months: int = 6) -> List[Dict]:
        """روند درآمد/هزینه ماهانه برای N ماه اخیر - برای نمایش نموداری در گزارش‌ها."""
        from sqlalchemy import func as sa_func
        session = self.Session()
        try:
            month_expr = sa_func.strftime('%Y-%m', JournalEntry.date)
            rows = session.query(
                month_expr.label('month'),
                Account.type,
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'credit'), 0).label('total_credit'),
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'debit'), 0).label('total_debit'),
            ).select_from(JournalLine).join(
                JournalEntry, JournalEntry.id == JournalLine.entry_id
            ).join(
                Account, Account.id == JournalLine.account_id
            ).filter(
                JournalEntry.user_id == user_id,
                Account.type.in_(['income', 'expense']),
            ).group_by('month', Account.type).order_by('month').all()

            summary: Dict[str, Dict[str, float]] = {}
            for r in rows:
                bucket = summary.setdefault(r.month, {"income": 0.0, "expense": 0.0})
                if r.type == 'income':
                    bucket["income"] += (r.total_credit - r.total_debit)
                else:
                    bucket["expense"] += (r.total_debit - r.total_credit)

            sorted_months = sorted(summary.keys())[-months:]
            return [{"month": m, "income": summary[m]["income"], "expense": summary[m]["expense"]} for m in sorted_months]
        finally:
            session.close()

    def get_profit_loss(self, business_type: Optional[str] = None, user_id: Optional[int] = None,
                         date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> List[Any]:
        """گزارش سود و زیان - برگشت حساب‌های درآمد و هزینه با مانده"""
        session = self.Session()
        try:
            credit_conditions = [JournalLine.side == 'credit']
            debit_conditions = [JournalLine.side == 'debit']
            if user_id is not None:
                credit_conditions.append(JournalEntry.user_id == user_id)
                debit_conditions.append(JournalEntry.user_id == user_id)
            if date_from is not None:
                credit_conditions.append(JournalEntry.date >= date_from)
                debit_conditions.append(JournalEntry.date >= date_from)
            if date_to is not None:
                credit_conditions.append(JournalEntry.date <= date_to)
                debit_conditions.append(JournalEntry.date <= date_to)

            credit_sum = func.coalesce(func.sum(JournalLine.amount).filter(*credit_conditions), 0)
            debit_sum = func.coalesce(func.sum(JournalLine.amount).filter(*debit_conditions), 0)
            # درآمد: مانده طبیعی بستانکار (بستانکار-بدهکار) | هزینه: مانده طبیعی بدهکار (بدهکار-بستانکار)
            balance_expr = case(
                (Account.type == 'income', credit_sum - debit_sum),
                else_=(debit_sum - credit_sum)
            ).label('balance')

            query = session.query(
                Account.code,
                Account.name,
                Account.type,
                balance_expr
            ).outerjoin(JournalLine, JournalLine.account_id == Account.id
            ).outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id
            ).filter(Account.type.in_(['income', 'expense'])
            )

            if business_type:
                query = query.join(BusinessType).filter(BusinessType.name == business_type)

            results = query.group_by(Account.id, Account.code, Account.name, Account.type).all()
            return results
        finally:
            session.close()

    def get_balance_sheet(self, business_type: Optional[str] = None, user_id: Optional[int] = None) -> Dict:
        """گزارش ترازنامه - برگشت دارایی‌ها، بدهی‌ها و سرمایه"""
        session = self.Session()
        try:
            account_types = {'asset': 'debit', 'liability': 'credit', 'equity': 'credit'}
            result: Dict = {"assets": [], "liabilities": [], "equity": []}

            for acct_type, balance_side in account_types.items():
                primary_side, other_side = ('debit', 'credit') if balance_side == 'debit' else ('credit', 'debit')
                primary_conditions = [JournalLine.side == primary_side]
                other_conditions = [JournalLine.side == other_side]
                if user_id is not None:
                    primary_conditions.append(JournalEntry.user_id == user_id)
                    other_conditions.append(JournalEntry.user_id == user_id)
                balance_expr = (
                    func.coalesce(func.sum(JournalLine.amount).filter(*primary_conditions), 0) -
                    func.coalesce(func.sum(JournalLine.amount).filter(*other_conditions), 0)
                ).label('balance')

                query = session.query(
                    Account.code,
                    Account.name,
                    balance_expr
                ).outerjoin(JournalLine, JournalLine.account_id == Account.id
                ).outerjoin(JournalEntry, JournalEntry.id == JournalLine.entry_id
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

    def get_journal(self, limit: int = 50, offset: int = 0, user_id: Optional[int] = None) -> List[Dict]:
        """گزارش دفتر روزنامه - برگشت سندهای حسابداری به همراه ردیف‌ها"""
        session = self.Session()
        try:
            query = session.query(JournalEntry)
            if user_id is not None:
                query = query.filter(JournalEntry.user_id == user_id)
            entries = query.order_by(JournalEntry.id.desc()).limit(limit).offset(offset).all()
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