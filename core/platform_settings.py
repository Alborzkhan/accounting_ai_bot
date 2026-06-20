# core/platform_settings.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Optional
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from database.license_models import PlatformSetting

KNOWN_KEYS = [
    "platform_logo_path",
    "support_technical_phone",
    "support_technical_telegram",
    "support_sales_phone",
    "support_sales_telegram",
]


class PlatformSettingsManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)

    def get_all(self) -> Dict[str, str]:
        session = self.Session()
        try:
            rows = session.query(PlatformSetting).all()
            values = {row.key: row.value or "" for row in rows}
            return {key: values.get(key, "") for key in KNOWN_KEYS}
        finally:
            session.close()

    def get(self, key: str, default: str = "") -> str:
        session = self.Session()
        try:
            row = session.query(PlatformSetting).filter_by(key=key).first()
            return row.value if row and row.value else default
        finally:
            session.close()

    def set(self, key: str, value: Optional[str]) -> None:
        session = self.Session()
        try:
            row = session.query(PlatformSetting).filter_by(key=key).first()
            if row:
                row.value = value
            else:
                session.add(PlatformSetting(key=key, value=value))
            session.commit()
        finally:
            session.close()

    def update_many(self, fields: Dict[str, Optional[str]]) -> None:
        for key, value in fields.items():
            if key in KNOWN_KEYS and value is not None:
                self.set(key, value)
