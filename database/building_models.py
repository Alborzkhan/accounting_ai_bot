# database/building_models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Building(Base):
    __tablename__ = 'buildings'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # نام مجتمع
    address = Column(String(300))
    total_units = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    user_id = Column(Integer)  # صاحب ساختمان/مدیر

class BuildingUnit(Base):
    __tablename__ = 'building_units'
    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey('buildings.id'))
    unit_number = Column(String(20), nullable=False)  # شماره واحد (مثلاً 101)
    owner_name = Column(String(100))
    owner_phone = Column(String(20))
    area = Column(Float)  # متراژ واحد
    created_at = Column(DateTime, default=datetime.now)

class BuildingExpense(Base):
    __tablename__ = 'building_expenses'
    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey('buildings.id'))
    expense_type = Column(String(50))  # برق، آب، گاز، نظافت، آسانسور، موتورخانه
    amount = Column(Float)
    date = Column(DateTime, default=datetime.now)
    description = Column(String(200))

class BuildingInvoice(Base):
    __tablename__ = 'building_invoices'
    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey('buildings.id'))
    unit_id = Column(Integer, ForeignKey('building_units.id'))
    month = Column(String(20))  # مثلاً "1402/01"
    total_amount = Column(Float)
    is_paid = Column(Boolean, default=False)
    paid_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)