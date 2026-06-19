# reports/data_export.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import io
from typing import List, Dict
from sqlalchemy.orm import sessionmaker
from database.models import init_db, JournalEntry, JournalLine, Account, Customer, Vendor
from datetime import datetime

class DataExport:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)

    def export_vouchers_csv(self) -> str:
        session = self.Session()
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["شماره سند", "تاریخ", "شرح", "کد حساب", "نام حساب", "بدهکار", "بستانکار"])
            entries = session.query(JournalEntry).order_by(JournalEntry.id.desc()).limit(500).all()
            for entry in entries:
                lines = session.query(JournalLine).filter(
                    JournalLine.entry_id == entry.id
                ).all()
                for line in lines:
                    account = session.query(Account).filter(Account.id == line.account_id).first()
                    debit = line.amount if line.side == 'debit' else 0
                    credit = line.amount if line.side == 'credit' else 0
                    writer.writerow([
                        entry.id,
                        entry.date.strftime("%Y-%m-%d") if entry.date else "",
                        entry.description or "",
                        account.code if account else "",
                        account.name if account else "",
                        debit, credit
                    ])
            return output.getvalue()
        finally:
            session.close()

    def export_trial_balance_csv(self) -> str:
        session = self.Session()
        try:
            from sqlalchemy import func
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["کد حساب", "نام حساب", "بدهکار", "بستانکار"])
            results = session.query(
                Account.code, Account.name,
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'debit'), 0).label('total_debit'),
                func.coalesce(func.sum(JournalLine.amount).filter(JournalLine.side == 'credit'), 0).label('total_credit')
            ).outerjoin(JournalLine).group_by(Account.id, Account.code, Account.name).all()
            for row in results:
                writer.writerow([row.code, row.name, row.total_debit, row.total_credit])
            return output.getvalue()
        finally:
            session.close()

    def export_customers_csv(self) -> str:
        session = self.Session()
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["نام مشتری", "موبایل", "تلفن", "کد ملی", "کد اقتصادی", "آدرس"])
            for c in session.query(Customer).order_by(Customer.name).all():
                writer.writerow([c.name, c.mobile or "", c.phone or "", c.national_id or "", c.economic_code or "", c.address or ""])
            return output.getvalue()
        finally:
            session.close()
