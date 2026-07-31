# core/budget_manager.py
"""مدیریت بودجه - تعریف، پیگیری و هشدار بودجه"""

import sys, os

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import func, and_, text
from sqlalchemy.orm import sessionmaker
from database.models import init_db, Account, JournalEntry, JournalLine
from database.license_models import User
from core.iran_accounting_codes import ACCOUNT_CODES

# مدل بودجه - مستقیماً در دیتابیس ایجاد می‌شود
BUDGET_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_code VARCHAR(20) NOT NULL,
    budget_type VARCHAR(10) NOT NULL DEFAULT 'monthly',
    amount REAL NOT NULL DEFAULT 0,
    period_year INTEGER,
    period_month INTEGER,
    is_active BOOLEAN DEFAULT 1,
    note VARCHAR(200),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, account_code, period_year, period_month)
)
"""


class BudgetManager:
    """مدیریت بودجه‌ریزی و مقایسه با عملکرد واقعی."""

    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self._ensure_table()

    def _ensure_table(self) -> None:
        """اطمینان از وجود جدول budgets."""
        conn = self.engine.connect()
        try:
            conn.execute(text(BUDGET_TABLE_DDL))
            conn.commit()
        finally:
            conn.close()

    def set_budget(self, user_id: int, account_code: str, amount: float,
                   budget_type: str = "monthly",
                   period_year: Optional[int] = None,
                   period_month: Optional[int] = None,
                   note: str = "") -> Dict:
        """تعریف یا به‌روزرسانی بودجه برای یک حساب."""
        session = self.Session()
        try:
            now = datetime.now()
            year = period_year or now.year
            month = period_month or now.month

            existing = session.execute(
                text("SELECT id FROM budgets WHERE user_id=:uid AND account_code=:ac AND period_year=:y AND period_month=:m"),
                {"uid": user_id, "ac": account_code, "y": year, "m": month}
            ).fetchone()

            if existing:
                session.execute(
                    text("UPDATE budgets SET amount=:amt, note=:n, updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                    {"amt": amount, "n": note, "id": existing[0]}
                )
            else:
                session.execute(
                    text("INSERT INTO budgets (user_id, account_code, budget_type, amount, period_year, period_month, note) VALUES (:uid, :ac, :bt, :amt, :y, :m, :n)"),
                    {"uid": user_id, "ac": account_code, "bt": budget_type, "amt": amount, "y": year, "m": month, "n": note}
                )
            session.commit()
            return {"success": True, "message": "بودجه با موفقیت ثبت شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def get_budgets(self, user_id: int, year: Optional[int] = None,
                    month: Optional[int] = None) -> List[Dict]:
        """دریافت بودجه‌های تعریف‌شده."""
        session = self.Session()
        try:
            now = datetime.now()
            y = year or now.year
            m = month or now.month

            rows = session.execute(
                text("""SELECT b.id, b.account_code, a.name as account_name, b.budget_type,
                          b.amount, b.period_year, b.period_month, b.is_active, b.note
                   FROM budgets b
                   LEFT JOIN accounts a ON a.code = b.account_code
                   WHERE b.user_id=:uid AND b.period_year=:y AND b.period_month=:m
                   ORDER BY b.account_code"""),
                {"uid": user_id, "y": y, "m": m}
            ).fetchall()

            return [
                {
                    "id": r[0], "account_code": r[1], "account_name": r[2] or r[1],
                    "budget_type": r[3], "amount": float(r[4]), "year": r[5],
                    "month": r[6], "is_active": bool(r[7]), "note": r[8] or "",
                }
                for r in rows
            ]
        finally:
            session.close()

    def get_budget_vs_actual(self, user_id: int, year: Optional[int] = None,
                             month: Optional[int] = None) -> List[Dict]:
        """مقایسه بودجه با عملکرد واقعی."""
        session = self.Session()
        try:
            now = datetime.now()
            y = year or now.year
            m = month or now.month

            # بودجه‌ها
            budgets = self.get_budgets(user_id, y, m)
            if not budgets:
                return []

            # عملکرد واقعی
            start_date = datetime(y, m, 1)
            if m == 12:
                end_date = datetime(y + 1, 1, 1)
            else:
                end_date = datetime(y, m + 1, 1)

            result = []
            for b in budgets:
                account = session.query(Account).filter_by(code=b["account_code"]).first()
                if not account:
                    result.append({**b, "actual": 0, "variance": -b["amount"],
                                   "variance_pct": -100.0})
                    continue

                actual = session.query(func.coalesce(func.sum(JournalLine.amount), 0)).join(
                    JournalEntry, JournalEntry.id == JournalLine.entry_id
                ).filter(
                    JournalLine.account_id == account.id,
                    JournalEntry.user_id == user_id,
                    JournalEntry.date >= start_date,
                    JournalEntry.date < end_date,
                ).scalar() or 0

                actual = float(actual)
                variance = actual - b["amount"]
                variance_pct = round((variance / b["amount"]) * 100, 1) if b["amount"] else 0

                result.append({
                    **b,
                    "actual": actual,
                    "variance": variance,
                    "variance_pct": variance_pct,
                })

            return result
        finally:
            session.close()

    def get_alerts(self, user_id: int, threshold_pct: float = 20.0) -> List[Dict]:
        """هشدار بودجه: بودجه‌هایی که بیش از threshold درصد مصرف شده‌اند."""
        comparisons = self.get_budget_vs_actual(user_id)
        alerts = []
        for item in comparisons:
            if item["amount"] <= 0:
                continue
            usage_pct = round((item["actual"] / item["amount"]) * 100, 1)
            if usage_pct >= (100 - threshold_pct):
                alerts.append({
                    **item,
                    "usage_pct": usage_pct,
                    "alert_type": "warning" if usage_pct < 100 else "critical",
                    "message": f"بودجه {item['account_name']}: {usage_pct}% مصرف شده "
                               f"({item['actual']:,.0f} از {item['amount']:,.0f} تومان)",
                })
        return alerts
