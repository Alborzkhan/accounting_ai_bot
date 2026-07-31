# core/dashboard_service.py
"""سرویس داشبورد تحلیلی - محاسبه KPIها و داده‌های نمودار"""

import sys, os

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import func, and_
from sqlalchemy.orm import sessionmaker
from database.models import (
    init_db, JournalEntry, JournalLine, Account,
    Customer, Vendor, ProformaInvoice, PurchaseInvoice
)
from database.license_models import User, License, Transaction
from core.iran_accounting_codes import ACCOUNT_CODES
from sqlalchemy import text as sa_text


INCOME_CODES = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "income"}
EXPENSE_CODES = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "expense"}
ASSET_CODES = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "asset"}
LIABILITY_CODES = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "liability"}
EQUITY_CODES = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "equity"}


class DashboardService:
    """محاسبه شاخص‌های کلیدی عملکرد (KPI) و داده‌های نمودار برای داشبورد."""

    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self._is_postgres = "postgresql" in str(self.engine.url)

    def _month_col(self, date_col):
        """ستون استخراج ماه - سازگار با SQLite و PostgreSQL."""
        if self._is_postgres:
            return func.to_char(date_col, "YYYY-MM").label("month")
        return func.strftime("%Y-%m", date_col).label("month")

    def _month_group(self, date_col):
        """عبارت GROUP BY برای ماه - سازگار با SQLite و PostgreSQL."""
        if self._is_postgres:
            return func.to_char(date_col, "YYYY-MM")
        return func.strftime("%Y-%m", date_col)

    def _get_account_ids(self, codes: set) -> List[int]:
        session = self.Session()
        try:
            rows = session.query(Account.id).filter(Account.code.in_(codes)).all()
            return [r[0] for r in rows]
        finally:
            session.close()

    def get_monthly_income_expense(self, user_id: int, months: int = 12) -> Dict:
        """درآمد و هزینه ماهانه برای نمودار خطی."""
        session = self.Session()
        try:
            today = datetime.now()
            start_date = today - timedelta(days=30 * months)

            income_ids = self._get_account_ids(INCOME_CODES)
            expense_ids = self._get_account_ids(EXPENSE_CODES)

            rows = (
                session.query(
                    self._month_col(JournalEntry.date),
                    func.sum(JournalLine.amount).label("total"),
                    JournalLine.account_id,
                )
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .filter(
                    JournalEntry.user_id == user_id,
                    JournalEntry.date >= start_date,
                )
                .group_by(
                    self._month_group(JournalEntry.date),
                    JournalLine.account_id,
                )
                .all()
            )

            monthly: Dict[str, dict] = {}
            for r in rows:
                month = r.month
                if month not in monthly:
                    monthly[month] = {"income": 0, "expense": 0}
                if r.account_id in income_ids:
                    monthly[month]["income"] += float(r.total or 0)
                elif r.account_id in expense_ids:
                    monthly[month]["expense"] += float(r.total or 0)

            labels = sorted(monthly.keys())
            income_data = [monthly[m]["income"] for m in labels]
            expense_data = [monthly[m]["expense"] for m in labels]
            profit_data = [income_data[i] - expense_data[i] for i in range(len(labels))]

            return {
                "labels": labels,
                "income": income_data,
                "expense": expense_data,
                "profit": profit_data,
            }
        finally:
            session.close()

    def get_expense_breakdown(self, user_id: int, months: int = 3) -> List[Dict]:
        """توزیع هزینه‌ها بر اساس حساب برای نمودار دایره‌ای."""
        session = self.Session()
        try:
            today = datetime.now()
            start_date = today - timedelta(days=30 * months)

            expense_ids = self._get_account_ids(EXPENSE_CODES)

            rows = (
                session.query(
                    Account.code,
                    Account.name,
                    func.sum(JournalLine.amount).label("total"),
                )
                .join(JournalLine, JournalLine.account_id == Account.id)
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .filter(
                    JournalEntry.user_id == user_id,
                    JournalEntry.date >= start_date,
                    Account.id.in_(expense_ids),
                )
                .group_by(Account.id)
                .order_by(func.sum(JournalLine.amount).desc())
                .all()
            )

            return [
                {"code": r.code, "name": r.name, "amount": float(r.total or 0)}
                for r in rows
            ]
        finally:
            session.close()

    def get_top_customers(self, user_id: int, limit: int = 5) -> List[Dict]:
        """مشتریان برتر از نظر گردش مالی."""
        session = self.Session()
        try:
            rows = (
                session.query(
                    Customer.name,
                    func.sum(JournalLine.amount).label("total"),
                )
                .join(JournalEntry, JournalEntry.customer_id == Customer.id)
                .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
                .filter(JournalEntry.user_id == user_id)
                .group_by(Customer.id)
                .order_by(func.sum(JournalLine.amount).desc())
                .limit(limit)
                .all()
            )
            return [
                {"name": r.name, "total": float(r.total or 0)} for r in rows
            ]
        finally:
            session.close()

    def get_top_vendors(self, user_id: int, limit: int = 5) -> List[Dict]:
        """فروشندگان برتر از نظر گردش مالی."""
        session = self.Session()
        try:
            rows = (
                session.query(
                    Vendor.name,
                    func.sum(JournalLine.amount).label("total"),
                )
                .join(JournalEntry, JournalEntry.vendor_id == Vendor.id)
                .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
                .filter(JournalEntry.user_id == user_id)
                .group_by(Vendor.id)
                .order_by(func.sum(JournalLine.amount).desc())
                .limit(limit)
                .all()
            )
            return [
                {"name": r.name, "total": float(r.total or 0)} for r in rows
            ]
        finally:
            session.close()

    def get_kpi_summary(self, user_id: int) -> Dict:
        """خلاصه KPIها برای کارت بالای داشبورد."""
        session = self.Session()
        try:
            income_ids = self._get_account_ids(INCOME_CODES)
            expense_ids = self._get_account_ids(EXPENSE_CODES)
            asset_ids = self._get_account_ids(ASSET_CODES)
            liability_ids = self._get_account_ids(LIABILITY_CODES)

            result = {"total_income": 0, "total_expense": 0, "net_profit": 0,
                      "total_assets": 0, "total_liabilities": 0, "voucher_count": 0}

            # درآمد و هزینه
            rows = session.query(JournalLine.account_id, func.sum(JournalLine.amount)).join(
                JournalEntry, JournalEntry.id == JournalLine.entry_id
            ).filter(JournalEntry.user_id == user_id).group_by(JournalLine.account_id).all()

            for acc_id, total in rows:
                total = float(total or 0)
                if acc_id in income_ids:
                    result["total_income"] += total
                elif acc_id in expense_ids:
                    result["total_expense"] += total
                elif acc_id in asset_ids:
                    result["total_assets"] += total
                elif acc_id in liability_ids:
                    result["total_liabilities"] += total

            result["net_profit"] = result["total_income"] - result["total_expense"]
            result["voucher_count"] = session.query(JournalEntry).filter(
                JournalEntry.user_id == user_id
            ).count()

            return result
        finally:
            session.close()

    def _date_col(self, date_col):
        """ستون تاریخ (بدون time) - سازگار با SQLite و PostgreSQL."""
        if self._is_postgres:
            return func.date_trunc('day', date_col).label("day")
        return func.date(date_col).label("day")

    def _date_group(self, date_col):
        if self._is_postgres:
            return func.date_trunc('day', date_col)
        return func.date(date_col)

    def get_cashflow(self, user_id: int, days: int = 30) -> Dict:
        """گردش نقدی روزانه برای نمودار."""
        session = self.Session()
        try:
            today = datetime.now()
            start_date = today - timedelta(days=days)
            cash_codes = {"1001", "1002", "1003"}
            cash_ids = self._get_account_ids(cash_codes)

            rows = (
                session.query(
                    self._date_col(JournalEntry.date),
                    func.sum(JournalLine.amount).label("total"),
                    JournalLine.side,
                )
                .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
                .filter(
                    JournalEntry.user_id == user_id,
                    JournalEntry.date >= start_date,
                    JournalLine.account_id.in_(cash_ids),
                )
                .group_by(self._date_group(JournalEntry.date), JournalLine.side)
                .order_by(self._date_group(JournalEntry.date))
                .all()
            )

            daily: Dict[str, dict] = {}
            for r in rows:
                day = str(r.day)
                if day not in daily:
                    daily[day] = {"inflow": 0, "outflow": 0}
                amt = float(r.total or 0)
                if r.side == "debit":
                    daily[day]["inflow"] += amt
                else:
                    daily[day]["outflow"] += amt

            labels = sorted(daily.keys())
            inflow = [daily[d]["inflow"] for d in labels]
            outflow = [daily[d]["outflow"] for d in labels]
            balance = []
            bal = 0
            for i in range(len(labels)):
                bal += inflow[i] - outflow[i]
                balance.append(bal)

            return {"labels": labels, "inflow": inflow, "outflow": outflow, "balance": balance}
        finally:
            session.close()
