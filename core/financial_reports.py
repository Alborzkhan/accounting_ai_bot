# core/financial_reports.py
"""گزارش‌های مالی پیشرفته: سود و زیان، ترازنامه، گردش حساب"""

import sys, os

from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from database.models import init_db, Account, JournalEntry, JournalLine
from core.iran_accounting_codes import ACCOUNT_CODES


class FinancialReports:
    """تولید گزارش‌های مالی استاندارد."""

    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)

    def _get_account_ids_by_type(self, session, codes: set) -> List[int]:
        rows = session.query(Account.id).filter(Account.code.in_(codes)).all()
        return [r[0] for r in rows]

    def profit_loss(self, user_id: int, date_from: Optional[datetime] = None,
                    date_to: Optional[datetime] = None) -> Dict:
        """گزارش سود و زیان برای یک بازه زمانی."""
        session = self.Session()
        try:
            income_codes = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "income"}
            expense_codes = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "expense"}

            income_ids = self._get_account_ids_by_type(session, income_codes)
            expense_ids = self._get_account_ids_by_type(session, expense_codes)

            q = session.query(
                Account.code, Account.name,
                func.sum(JournalLine.amount).label("total")
            ).join(JournalLine, JournalLine.account_id == Account.id
            ).join(JournalEntry, JournalEntry.id == JournalLine.entry_id
            ).filter(JournalEntry.user_id == user_id)

            if date_from:
                q = q.filter(JournalEntry.date >= date_from)
            if date_to:
                q = q.filter(JournalEntry.date <= date_to)

            rows = q.group_by(Account.id).order_by(Account.code).all()

            incomes = []
            expenses = []
            total_income = 0.0
            total_expense = 0.0

            for r in rows:
                amt = float(r.total or 0)
                if r.account_id in income_ids:
                    incomes.append({"code": r.code, "name": r.name, "amount": amt})
                    total_income += amt
                elif r.account_id in expense_ids:
                    expenses.append({"code": r.code, "name": r.name, "amount": amt})
                    total_expense += amt

            net_profit = total_income - total_expense

            return {
                "incomes": incomes,
                "expenses": expenses,
                "total_income": total_income,
                "total_expense": total_expense,
                "net_profit": net_profit,
                "is_profit": net_profit >= 0,
            }
        finally:
            session.close()

    def balance_sheet(self, user_id: int) -> Dict:
        """ترازنامه: دارایی‌ها، بدهی‌ها و حقوق صاحبان سهام."""
        session = self.Session()
        try:
            asset_codes = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "asset"}
            liability_codes = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "liability"}
            equity_codes = {k for k, v in ACCOUNT_CODES.items() if v["type"] == "equity"}

            asset_ids = self._get_account_ids_by_type(session, asset_codes)
            liability_ids = self._get_account_ids_by_type(session, liability_codes)
            equity_ids = self._get_account_ids_by_type(session, equity_codes)

            rows = session.query(
                Account.code, Account.name,
                func.sum(JournalLine.amount).label("total"),
                JournalLine.side,
            ).join(JournalLine, JournalLine.account_id == Account.id
            ).join(JournalEntry, JournalEntry.id == JournalLine.entry_id
            ).filter(JournalEntry.user_id == user_id
            ).group_by(Account.id, JournalLine.side).all()

            def calc_balance(acc_ids: List[int], side: str = "debit") -> List[Dict]:
                items = []
                for r in rows:
                    if r.account_id in acc_ids:
                        amt = float(r.total or 0)
                        items.append({"code": r.code, "name": r.name, "amount": amt})
                # deduplicate by summing
                merged = {}
                for item in items:
                    code = item["code"]
                    if code in merged:
                        merged[code]["amount"] += item["amount"]
                    else:
                        merged[code] = item.copy()
                return list(merged.values())

            assets = calc_balance(asset_ids, "debit")
            liabilities = calc_balance(liability_ids, "credit")
            equities = calc_balance(equity_ids)

            total_assets = sum(a["amount"] for a in assets)
            total_liabilities = sum(l["amount"] for l in liabilities)
            total_equity = sum(e["amount"] for e in equities)

            return {
                "assets": assets,
                "liabilities": liabilities,
                "equities": equities,
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "total_equity": total_equity,
            }
        finally:
            session.close()

    def account_statement(self, user_id: int, account_code: str,
                          date_from: Optional[datetime] = None,
                          date_to: Optional[datetime] = None) -> Dict:
        """گردش یک حساب خاص با مانده در گردش."""
        session = self.Session()
        try:
            account = session.query(Account).filter_by(code=account_code).first()
            if not account:
                return {"success": False, "message": "حساب یافت نشد."}

            q = session.query(
                JournalEntry.date,
                JournalEntry.description,
                JournalLine.side,
                JournalLine.amount,
                JournalEntry.id,
            ).join(JournalLine, JournalLine.entry_id == JournalEntry.id
            ).filter(
                JournalLine.account_id == account.id,
                JournalEntry.user_id == user_id,
            )

            if date_from:
                q = q.filter(JournalEntry.date >= date_from)
            if date_to:
                q = q.filter(JournalEntry.date <= date_to)

            rows = q.order_by(JournalEntry.date.asc(), JournalEntry.id.asc()).all()

            items = []
            balance = 0.0
            for r in rows:
                debit = r.amount if r.side == "debit" else 0
                credit = r.amount if r.side == "credit" else 0
                balance += debit - credit
                items.append({
                    "date": r.date.isoformat() if r.date else "",
                    "description": r.description or "",
                    "debit": float(debit),
                    "credit": float(credit),
                    "balance": round(balance, 0),
                })

            return {
                "success": True,
                "account_code": account_code,
                "account_name": account.name,
                "items": items,
                "closing_balance": round(balance, 0),
            }
        finally:
            session.close()

    def vat_report(self, user_id: int, date_from: Optional[datetime] = None,
                   date_to: Optional[datetime] = None) -> Dict:
        """گزارش مالیات بر ارزش افزوده (خرید و فروش مشمول VAT)."""
        from database.models import ProformaInvoice, PurchaseInvoice

        session = self.Session()
        try:
            vat_rate = 0.09  # 9% VAT

            # فروش‌های مشمول VAT
            sales_q = session.query(
                func.count(ProformaInvoice.id).label("count"),
                func.coalesce(func.sum(ProformaInvoice.subtotal), 0).label("subtotal"),
                func.coalesce(func.sum(ProformaInvoice.vat_amount), 0).label("vat"),
                func.coalesce(func.sum(ProformaInvoice.total), 0).label("total"),
            ).filter(
                ProformaInvoice.user_id == user_id,
                ProformaInvoice.is_vat_applied == True,
            )
            if date_from:
                sales_q = sales_q.filter(ProformaInvoice.date >= date_from)
            if date_to:
                sales_q = sales_q.filter(ProformaInvoice.date <= date_to)
            sales = sales_q.first()

            # خریدهای مشمول VAT
            purchases_q = session.query(
                func.count(PurchaseInvoice.id).label("count"),
                func.coalesce(func.sum(PurchaseInvoice.subtotal), 0).label("subtotal"),
                func.coalesce(func.sum(PurchaseInvoice.vat_amount), 0).label("vat"),
                func.coalesce(func.sum(PurchaseInvoice.total), 0).label("total"),
            ).filter(
                PurchaseInvoice.user_id == user_id,
                PurchaseInvoice.is_vat_applied == True,
            )
            if date_from:
                purchases_q = purchases_q.filter(PurchaseInvoice.date >= date_from)
            if date_to:
                purchases_q = purchases_q.filter(PurchaseInvoice.date <= date_to)
            purchases = purchases_q.first()

            sales_vat = float(sales.vat or 0)
            purchase_vat = float(purchases.vat or 0)
            vat_payable = sales_vat - purchase_vat

            return {
                "sales": {
                    "count": sales.count or 0,
                    "subtotal": float(sales.subtotal or 0),
                    "vat": sales_vat,
                    "total": float(sales.total or 0),
                },
                "purchases": {
                    "count": purchases.count or 0,
                    "subtotal": float(purchases.subtotal or 0),
                    "vat": purchase_vat,
                    "total": float(purchases.total or 0),
                },
                "vat_payable": max(vat_payable, 0),
                "vat_creditable": max(-vat_payable, 0),
                "net_vat": vat_payable,
                "vat_rate": vat_rate,
            }
        finally:
            session.close()
