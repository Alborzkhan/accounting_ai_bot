# core/recurring_service.py
"""سرویس تراکنش‌های دوره‌ای - ثبت خودکار اسناد تکراری"""

import sys, os

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from core.accounting_engine import AccountingEngine

RECURRING_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS recurring_vouchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title VARCHAR(100) NOT NULL,
    description VARCHAR(500) NOT NULL,
    frequency VARCHAR(20) NOT NULL DEFAULT 'monthly',
    interval_count INTEGER NOT NULL DEFAULT 1,
    debit_account_code VARCHAR(20) NOT NULL,
    credit_account_code VARCHAR(20) NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    next_run_date DATE NOT NULL,
    end_date DATE,
    last_run_date DATE,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

RECURRING_LOG_DDL = """
CREATE TABLE IF NOT EXISTS recurring_voucher_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recurring_id INTEGER NOT NULL,
    entry_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    message VARCHAR(500),
    run_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


class RecurringVoucherService:
    """مدیریت و اجرای اسناد حسابداری دوره‌ای (اجاره، حقوق، اقساط و ...)."""

    FREQUENCIES = {
        "daily": "روزانه",
        "weekly": "هفتگی",
        "monthly": "ماهانه",
        "quarterly": "سه ماهه",
        "semi_annual": "شش ماهه",
        "annual": "سالانه",
    }

    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self.acc_engine = AccountingEngine(db_path)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        conn = self.engine.connect()
        try:
            conn.execute(text(RECURRING_TABLE_DDL))
            conn.execute(text(RECURRING_LOG_DDL))
            conn.commit()
        finally:
            conn.close()

    def create(self, user_id: int, title: str, description: str,
               frequency: str, debit_code: str, credit_code: str,
               amount: float, next_run: Optional[str] = None,
               end_date: Optional[str] = None,
               interval_count: int = 1) -> Dict:
        """ایجاد سند دوره‌ای جدید."""
        if frequency not in self.FREQUENCIES:
            return {"success": False, "message": "فرکانس نامعتبر است."}
        if amount <= 0:
            return {"success": False, "message": "مبلغ باید بیشتر از صفر باشد."}

        from datetime import date as date_type
        next_date = date_type.today()
        if next_run:
            try:
                next_date = date_type.fromisoformat(next_run)
            except ValueError:
                pass

        end_dt = None
        if end_date:
            try:
                end_dt = date_type.fromisoformat(end_date)
            except ValueError:
                pass

        session = self.Session()
        try:
            session.execute(
                text("""INSERT INTO recurring_vouchers
                   (user_id, title, description, frequency, interval_count,
                    debit_account_code, credit_account_code, amount,
                    next_run_date, end_date, is_active)
                   VALUES (:uid, :title, :desc, :freq, :interval,
                    :dc, :cc, :amt, :next_run, :end_dt, 1)"""),
                {"uid": user_id, "title": title, "desc": description,
                 "freq": frequency, "interval": interval_count,
                 "dc": debit_code, "cc": credit_code, "amt": amount,
                 "next_run": next_date, "end_dt": end_dt}
            )
            session.commit()
            return {"success": True, "message": f"سند دوره‌ای «{title}» با موفقیت ایجاد شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def get_all(self, user_id: int) -> List[Dict]:
        """دریافت لیست اسناد دوره‌ای کاربر."""
        session = self.Session()
        try:
            rows = session.execute(
                text("""SELECT id, title, description, frequency, interval_count,
                          debit_account_code, credit_account_code, amount,
                          next_run_date, end_date, last_run_date, is_active
                   FROM recurring_vouchers
                   WHERE user_id=:uid
                   ORDER BY next_run_date ASC"""),
                {"uid": user_id}
            ).fetchall()

            return [
                {
                    "id": r[0], "title": r[1], "description": r[2],
                    "frequency": r[3], "frequency_label": self.FREQUENCIES.get(r[3], r[3]),
                    "interval": r[4],
                    "debit_code": r[5], "credit_code": r[6],
                    "amount": float(r[7]),
                    "next_run": str(r[8]) if r[8] else "",
                    "end_date": str(r[9]) if r[9] else "",
                    "last_run": str(r[10]) if r[10] else "",
                    "is_active": bool(r[11]),
                }
                for r in rows
            ]
        finally:
            session.close()

    def _calc_next_run(self, current: datetime, frequency: str, interval: int) -> datetime:
        """محاسبه تاریخ اجرای بعدی بر اساس فرکانس."""
        from datetime import date as date_type
        if isinstance(current, date_type) and not isinstance(current, datetime):
            current = datetime.combine(current, datetime.min.time())

        if frequency == "daily":
            return current + timedelta(days=interval)
        elif frequency == "weekly":
            return current + timedelta(weeks=interval)
        elif frequency == "monthly":
            month = current.month + interval
            year = current.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            day = min(current.day, 28)
            try:
                return current.replace(year=year, month=month, day=day)
            except ValueError:
                return current.replace(year=year, month=month, day=28)
        elif frequency == "quarterly":
            return self._calc_next_run(current, "monthly", interval * 3)
        elif frequency == "semi_annual":
            return self._calc_next_run(current, "monthly", interval * 6)
        elif frequency == "annual":
            return self._calc_next_run(current, "monthly", interval * 12)
        return current + timedelta(days=30)

    def process_due(self, user_id: Optional[int] = None) -> List[Dict]:
        """پردازش اسناد دوره‌ای سررسیدشده و ایجاد سند حسابداری."""
        session = self.Session()
        try:
            from datetime import date as date_type
            today = date_type.today()
            results = []

            q = text("SELECT * FROM recurring_vouchers WHERE is_active=1 AND next_run_date <= :today")
            params = {"today": today}
            if user_id:
                q = text("SELECT * FROM recurring_vouchers WHERE is_active=1 AND next_run_date <= :today AND user_id=:uid")
                params = {"today": today, "uid": user_id}

            rows = session.execute(q, params).fetchall()

            for r in rows:
                rec_id = r[0]
                uid = r[1]
                title = r[2]
                desc = r[3]
                freq = r[4]
                interval = r[5]
                debit_code = r[6]
                credit_code = r[7]
                amount = r[8]
                next_run = r[9]
                end_dt = r[10]
                last_run = r[11]

                # بررسی پایان دوره
                if end_dt and today > end_dt:
                    session.execute(
                        text("UPDATE recurring_vouchers SET is_active=0 WHERE id=:id"),
                        {"id": rec_id}
                    )
                    continue

                try:
                    entry_id = self.acc_engine.create_voucher(
                        date=datetime.now(),
                        description=f"[دوره‌ای] {title} - {desc}",
                        lines=[
                            (debit_code, amount, "debit"),
                            (credit_code, amount, "credit"),
                        ],
                        user_id=uid,
                    )

                    # محاسبه تاریخ بعدی
                    next_date = self._calc_next_run(
                        datetime.combine(next_run, datetime.min.time())
                        if not isinstance(next_run, datetime) else next_run,
                        freq, interval
                    )

                    session.execute(
                        text("""UPDATE recurring_vouchers
                           SET last_run_date=:today, next_run_date=:nd, updated_at=CURRENT_TIMESTAMP
                           WHERE id=:id"""),
                        {"today": today, "nd": next_date.date() if hasattr(next_date, 'date') else next_date, "id": rec_id}
                    )

                    session.execute(
                        text("INSERT INTO recurring_voucher_logs (recurring_id, entry_id, status, message) VALUES (:rid, :eid, 'success', :msg)"),
                        {"rid": rec_id, "eid": entry_id, "msg": f"سند شماره {entry_id} با موفقیت ثبت شد."}
                    )

                    results.append({
                        "recurring_id": rec_id, "title": title,
                        "entry_id": entry_id, "status": "success",
                    })

                except Exception as e:
                    session.execute(
                        text("INSERT INTO recurring_voucher_logs (recurring_id, status, message) VALUES (:rid, 'error', :msg)"),
                        {"rid": rec_id, "msg": str(e)}
                    )
                    results.append({
                        "recurring_id": rec_id, "title": title,
                        "entry_id": None, "status": "error", "error": str(e),
                    })

            session.commit()
            return results
        except Exception as e:
            session.rollback()
            return [{"status": "error", "error": str(e)}]
        finally:
            session.close()

    def delete(self, recurring_id: int, user_id: int) -> Dict:
        """حذف سند دوره‌ای."""
        session = self.Session()
        try:
            session.execute(
                text("DELETE FROM recurring_vouchers WHERE id=:id AND user_id=:uid"),
                {"id": recurring_id, "uid": user_id}
            )
            session.commit()
            return {"success": True, "message": "سند دوره‌ای حذف شد."}
        finally:
            session.close()

    def toggle_active(self, recurring_id: int, user_id: int) -> Dict:
        """فعال/غیرفعال کردن سند دوره‌ای."""
        session = self.Session()
        try:
            row = session.execute(
                text("SELECT is_active FROM recurring_vouchers WHERE id=:id AND user_id=:uid"),
                {"id": recurring_id, "uid": user_id}
            ).fetchone()
            if not row:
                return {"success": False, "message": "یافت نشد."}
            new_status = 0 if row[0] else 1
            session.execute(
                text("UPDATE recurring_vouchers SET is_active=:status WHERE id=:id"),
                {"status": new_status, "id": recurring_id}
            )
            session.commit()
            return {"success": True, "is_active": bool(new_status)}
        finally:
            session.close()
