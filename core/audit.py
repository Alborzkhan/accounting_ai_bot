# core/audit.py
"""لاگ ممیزی - ثبت تمام تغییرات مهم با کاربر و زمان"""

import sys, os, json

from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from database.models import init_db

AUDIT_LOG_DDL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(50),
    changes TEXT,
    ip_address VARCHAR(50),
    user_agent VARCHAR(200),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


class AuditService:
    """ثبت و بازیابی لاگ ممیزی."""

    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = self.engine.connect()
        try:
            conn.execute(text(AUDIT_LOG_DDL))
            conn.commit()
        finally:
            conn.close()

    def log(self, user_id: Optional[int], action: str, entity_type: str,
            entity_id: Optional[str] = None, changes: Optional[Dict] = None,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None) -> int:
        """ثبت یک رویداد در لاگ ممیزی."""
        session = self.Session()
        try:
            changes_json = json.dumps(changes, ensure_ascii=False, default=str) if changes else None
            session.execute(
                text("INSERT INTO audit_logs (user_id, action, entity_type, entity_id, changes, ip_address, user_agent) VALUES (:uid, :act, :et, :eid, :ch, :ip, :ua)"),
                {"uid": user_id, "act": action, "et": entity_type, "eid": entity_id,
                 "ch": changes_json, "ip": ip_address, "ua": user_agent}
            )
            session.commit()
            return session.execute(text("SELECT last_insert_rowid()")).scalar() or 0
        except Exception:
            session.rollback()
            return 0
        finally:
            session.close()

    def get_logs(self, user_id: Optional[int] = None,
                 entity_type: Optional[str] = None,
                 action: Optional[str] = None,
                 limit: int = 50, offset: int = 0) -> List[Dict]:
        """دریافت لاگ‌های ممیزی با فیلتر."""
        session = self.Session()
        try:
            conditions = []
            params = {}

            if user_id:
                conditions.append("user_id=:uid")
                params["uid"] = user_id
            if entity_type:
                conditions.append("entity_type=:et")
                params["et"] = entity_type
            if action:
                conditions.append("action=:act")
                params["act"] = action

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            rows = session.execute(
                text(f"SELECT id, user_id, action, entity_type, entity_id, changes, ip_address, created_at FROM audit_logs {where} ORDER BY id DESC LIMIT :lim OFFSET :off"),
                {**params, "lim": limit, "off": offset}
            ).fetchall()

            return [
                {
                    "id": r[0], "user_id": r[1], "action": r[2],
                    "entity_type": r[3], "entity_id": r[4],
                    "changes": json.loads(r[5]) if r[5] else None,
                    "ip_address": r[6],
                    "created_at": str(r[7]) if r[7] else "",
                }
                for r in rows
            ]
        finally:
            session.close()
