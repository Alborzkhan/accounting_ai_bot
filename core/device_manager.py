import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import secrets
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from database.license_models import User

DEVICE_BASE = declarative_base()

class UserDevice(DEVICE_BASE):
    __tablename__ = 'user_devices'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    device_name = Column(String(100), default="")
    device_fingerprint = Column(String(200))
    last_active = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)

class DeviceManager:
    MAX_DEVICES = 2

    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        DEVICE_BASE.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def register_device(self, user_id: int, device_fingerprint: str, device_name: str = "") -> Dict:
        session = self.Session()
        try:
            existing = session.query(UserDevice).filter(
                UserDevice.user_id == user_id,
                UserDevice.device_fingerprint == device_fingerprint,
                UserDevice.is_active == True
            ).first()
            if existing:
                existing.last_active = datetime.now()
                session.commit()
                return {"success": True, "message": "دستگاه قبلاً ثبت شده است."}

            active_count = session.query(UserDevice).filter(
                UserDevice.user_id == user_id,
                UserDevice.is_active == True
            ).count()

            if active_count >= self.MAX_DEVICES:
                return {"success": False, "message": f"شما مجاز به استفاده از حداکثر {self.MAX_DEVICES} دستگاه هستید. برای اتصال دستگاه جدید، یکی از دستگاه‌های قبلی را غیرفعال کنید."}

            device = UserDevice(
                user_id=user_id,
                device_fingerprint=device_fingerprint,
                device_name=device_name
            )
            session.add(device)
            session.commit()
            return {"success": True, "message": "دستگاه با موفقیت ثبت شد.", "device_count": active_count + 1}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"خطا: {e}"}
        finally:
            session.close()

    def remove_device(self, user_id: int, device_fingerprint: str) -> Dict:
        session = self.Session()
        try:
            device = session.query(UserDevice).filter(
                UserDevice.user_id == user_id,
                UserDevice.device_fingerprint == device_fingerprint,
                UserDevice.is_active == True
            ).first()
            if device:
                device.is_active = False
                session.commit()
                return {"success": True, "message": "دستگاه با موفقیت حذف شد."}
            return {"success": False, "message": "دستگاه یافت نشد."}
        finally:
            session.close()

    def get_user_devices(self, user_id: int) -> List[Dict]:
        session = self.Session()
        try:
            devices = session.query(UserDevice).filter(
                UserDevice.user_id == user_id,
                UserDevice.is_active == True
            ).all()
            return [{"id": d.id, "name": d.device_name or "ناشناس", "last_active": d.last_active.strftime("%Y-%m-%d %H:%M") if d.last_active else ""} for d in devices]
        finally:
            session.close()

    def can_add_device(self, user_id: int) -> bool:
        session = self.Session()
        try:
            count = session.query(UserDevice).filter(
                UserDevice.user_id == user_id,
                UserDevice.is_active == True
            ).count()
            return count < self.MAX_DEVICES
        finally:
            session.close()
