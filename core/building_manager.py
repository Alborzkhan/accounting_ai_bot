# core/building_manager.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from database.models import init_db
from database.building_models import Building, BuildingUnit, BuildingExpense, BuildingInvoice
from database.license_models import User
from core.accounting_engine import AccountingEngine

class BuildingManager:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        # ایجاد جداول مجتمع
        from database.building_models import Base
        Base.metadata.create_all(self.engine)
        self.acc_engine = AccountingEngine(db_path)
    
    def validate_mobile(self, mobile: str) -> bool:
        """اعتبارسنجی شماره موبایل ایران"""
        if not mobile:
            return True  # خالی اشکال ندارد
        pattern = r'^09[0-9]{9}$'
        return bool(re.match(pattern, mobile))
    
    def validate_phone(self, phone: str) -> bool:
        """اعتبارسنجی شماره تلفن ثابت (اختیاری)"""
        if not phone:
            return True
        pattern = r'^0[0-9]{2,3}[0-9]{8}$'
        return bool(re.match(pattern, phone))
    
    def add_building(self, user_id: int, name: str, address: str = "", total_units: int = 0) -> dict:
        """ثبت مجتمع جدید"""
        session = self.Session()
        try:
            building = Building(
                user_id=user_id,
                name=name,
                address=address,
                total_units=total_units
            )
            session.add(building)
            session.commit()
            return {"success": True, "building_id": building.id, "message": f"✅ مجتمع {name} با موفقیت ثبت شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {e}"}
        finally:
            session.close()
    
    def add_unit(self, building_id: int, unit_number: str, owner_name: str = "", owner_phone: str = "", area: float = 0) -> dict:
        """ثبت واحد آپارتمان با اعتبارسنجی شماره موبایل"""
        # اعتبارسنجی شماره موبایل
        if owner_phone and not self.validate_mobile(owner_phone):
            return {"success": False, "message": "❌ شماره موبایل نامعتبر. شماره باید با 09 شروع شود و 11 رقم باشد."}
        
        session = self.Session()
        try:
            unit = BuildingUnit(
                building_id=building_id,
                unit_number=unit_number,
                owner_name=owner_name,
                owner_phone=owner_phone,
                area=area
            )
            session.add(unit)
            session.commit()
            return {"success": True, "unit_id": unit.id, "message": f"✅ واحد {unit_number} با موفقیت ثبت شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {e}"}
        finally:
            session.close()
    
    def add_expense(self, building_id: int, expense_type: str, amount: float, description: str = "") -> dict:
        """ثبت هزینه ساختمان"""
        session = self.Session()
        try:
            expense = BuildingExpense(
                building_id=building_id,
                expense_type=expense_type,
                amount=amount,
                description=description
            )
            session.add(expense)
            session.commit()
            
            # ثبت در حسابداری (هزینه ساختمان)
            self.acc_engine.create_voucher(
                date=datetime.now(),
                description=f"هزینه {expense_type} ساختمان - مبلغ {amount:,} تومان",
                lines=[
                    ("7005", amount, 'debit'),  # هزینه تعمیر و نگهداری
                    ("1001", amount, 'credit')   # صندوق
                ]
            )
            
            return {"success": True, "expense_id": expense.id, "message": f"✅ هزینه {expense_type} ثبت شد."}
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {e}"}
        finally:
            session.close()
    
    def calculate_maintenance_fee(self, building_id: int, month: str) -> dict:
        """محاسبه شارژ ماهیانه هر واحد بر اساس متراژ"""
        session = self.Session()
        try:
            # محاسبه کل هزینه‌های ماه جاری
            from datetime import datetime
            now = datetime.now()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0)
            
            expenses = session.query(BuildingExpense).filter(
                BuildingExpense.building_id == building_id,
                BuildingExpense.date >= start_of_month
            ).all()
            
            total_expense = sum(e.amount for e in expenses)
            
            if total_expense == 0:
                return {"success": False, "message": "هزینه‌ای برای این ماه ثبت نشده است."}
            
            # جمع کل متراژ واحدها
            units = session.query(BuildingUnit).filter(
                BuildingUnit.building_id == building_id
            ).all()
            
            total_area = sum(u.area for u in units if u.area > 0)
            
            if total_area == 0:
                return {"success": False, "message": "متراژ واحدها ثبت نشده است."}
            
            # محاسبه شارژ هر واحد بر اساس متراژ
            unit_fees = []
            for unit in units:
                fee = (unit.area / total_area) * total_expense if unit.area > 0 else 0
                unit_fees.append({
                    "unit_id": unit.id,
                    "unit_number": unit.unit_number,
                    "owner_name": unit.owner_name,
                    "area": unit.area,
                    "fee": fee
                })
            
            return {
                "success": True,
                "total_expense": total_expense,
                "total_area": total_area,
                "unit_fees": unit_fees
            }
        finally:
            session.close()
    
    def create_invoice_for_unit(self, unit_id: int, month: str, amount: float) -> dict:
        """صدور قبض شارژ برای یک واحد"""
        session = self.Session()
        try:
            invoice = BuildingInvoice(
                unit_id=unit_id,
                month=month,
                total_amount=amount,
                is_paid=False
            )
            session.add(invoice)
            session.commit()
            
            # پیدا کردن واحد برای نمایش
            unit = session.query(BuildingUnit).filter(BuildingUnit.id == unit_id).first()
            
            return {
                "success": True,
                "invoice_id": invoice.id,
                "message": f"✅ قبض شارژ ماه {month} برای واحد {unit.unit_number if unit else unit_id} صادر شد. مبلغ: {amount:,.0f} تومان"
            }
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {e}"}
        finally:
            session.close()
    
    def get_all_buildings(self, user_id: int) -> list:
        """دریافت لیست مجتمع‌های کاربر"""
        session = self.Session()
        try:
            buildings = session.query(Building).filter(
                Building.user_id == user_id
            ).all()
            return buildings
        finally:
            session.close()
    
    def get_all_units(self, building_id: int) -> list:
        """دریافت لیست واحدهای یک مجتمع"""
        session = self.Session()
        try:
            units = session.query(BuildingUnit).filter(
                BuildingUnit.building_id == building_id
            ).all()
            return units
        finally:
            session.close()
    
    def interactive_building_manager(self, user_id: int) -> None:
        """منوی تعاملی مدیریت مجتمع"""
        while True:
            print("\n" + "=" * 50)
            print("🏢 مدیریت مجتمع و آپارتمان")
            print("=" * 50)
            print("\n1. ثبت مجتمع جدید")
            print("2. ثبت واحد آپارتمان")
            print("3. ثبت هزینه ساختمان")
            print("4. محاسبه شارژ ماهیانه")
            print("5. صدور قبض برای واحدها")
            print("6. لیست مجتمع‌ها")
            print("7. لیست واحدها")
            print("8. خروج")
            
            choice = input("\nانتخاب کنید: ").strip()
            
            if choice == "1":
                name = input("نام مجتمع: ").strip()
                address = input("آدرس: ").strip()
                result = self.add_building(user_id, name, address)
                print(result["message"])
            
            elif choice == "2":
                buildings = self.get_all_buildings(user_id)
                if not buildings:
                    print("❌ ابتدا یک مجتمع ثبت کنید.")
                    continue
                
                print("\n📋 لیست مجتمع‌ها:")
                for b in buildings:
                    print(f"   {b.id}. {b.name}")
                
                building_id = int(input("\nشناسه مجتمع: ").strip())
                unit_number = input("شماره واحد (مثال: 101): ").strip()
                owner_name = input("نام مالک: ").strip()
                owner_phone = input("تلفن مالک: ").strip()
                
                # اعتبارسنجی شماره موبایل
                if owner_phone and not self.validate_mobile(owner_phone):
                    print("❌ شماره موبایل نامعتبر. شماره باید با 09 شروع شود و 11 رقم باشد.")
                    continue
                
                try:
                    area = float(input("متراژ: ").strip() or 0)
                except:
                    area = 0
                
                result = self.add_unit(building_id, unit_number, owner_name, owner_phone, area)
                print(result["message"])
            
            elif choice == "3":
                buildings = self.get_all_buildings(user_id)
                if not buildings:
                    print("❌ ابتدا یک مجتمع ثبت کنید.")
                    continue
                
                print("\n📋 لیست مجتمع‌ها:")
                for b in buildings:
                    print(f"   {b.id}. {b.name}")
                
                building_id = int(input("\nشناسه مجتمع: ").strip())
                print("\nنوع هزینه:")
                print("1. برق مشاعات")
                print("2. آب مشاعات")
                print("3. گاز مشاعات")
                print("4. نظافت")
                print("5. آسانسور")
                print("6. موتورخانه")
                print("7. سایر")
                exp_choice = input("\nانتخاب کنید: ").strip()
                exp_map = {
                    "1": "برق مشاعات", "2": "آب مشاعات", "3": "گاز مشاعات",
                    "4": "نظافت", "5": "آسانسور", "6": "موتورخانه", "7": "سایر"
                }
                expense_type = exp_map.get(exp_choice, "سایر")
                
                try:
                    amount = float(input("مبلغ (تومان): ").strip())
                except:
                    print("❌ مبلغ نامعتبر.")
                    continue
                
                result = self.add_expense(building_id, expense_type, amount)
                print(result["message"])
            
            elif choice == "4":
                buildings = self.get_all_buildings(user_id)
                if not buildings:
                    print("❌ ابتدا یک مجتمع ثبت کنید.")
                    continue
                
                print("\n📋 لیست مجتمع‌ها:")
                for b in buildings:
                    print(f"   {b.id}. {b.name}")
                
                building_id = int(input("\nشناسه مجتمع: ").strip())
                month = input("ماه (مثال: 1404/02): ").strip()
                result = self.calculate_maintenance_fee(building_id, month)
                if result["success"]:
                    print(f"\n📊 مجموع هزینه‌ها: {result['total_expense']:,.0f} تومان")
                    print(f"📐 مجموع متراژ: {result['total_area']:.0f} متر")
                    print("\n💰 شارژ هر واحد:")
                    for u in result["unit_fees"]:
                        print(f"   واحد {u['unit_number']} - {u['owner_name']}: {u['fee']:,.0f} تومان")
                else:
                    print(result["message"])
            
            elif choice == "5":
                buildings = self.get_all_buildings(user_id)
                if not buildings:
                    print("❌ ابتدا یک مجتمع ثبت کنید.")
                    continue
                
                building_id = int(input("شناسه مجتمع: ").strip())
                units = self.get_all_units(building_id)
                if not units:
                    print("❌ هیچ واحدی برای این مجتمع ثبت نشده است.")
                    continue
                
                print("\n📋 لیست واحدها:")
                for u in units:
                    print(f"   {u.id}. واحد {u.unit_number} - {u.owner_name}")
                
                unit_id = int(input("\nشناسه واحد: ").strip())
                month = input("ماه (مثال: 1404/02): ").strip()
                
                try:
                    amount = float(input("مبلغ شارژ (تومان): ").strip())
                except:
                    print("❌ مبلغ نامعتبر.")
                    continue
                
                result = self.create_invoice_for_unit(unit_id, month, amount)
                print(result["message"])
            
            elif choice == "6":
                buildings = self.get_all_buildings(user_id)
                if not buildings:
                    print("❌ هیچ مجتمعی ثبت نشده است.")
                else:
                    print("\n📋 لیست مجتمع‌ها:")
                    for b in buildings:
                        print(f"   {b.id}. {b.name} - {b.address or 'آدرس ثبت نشده'}")
            
            elif choice == "7":
                buildings = self.get_all_buildings(user_id)
                if not buildings:
                    print("❌ ابتدا یک مجتمع ثبت کنید.")
                    continue
                
                print("\n📋 لیست مجتمع‌ها:")
                for b in buildings:
                    print(f"   {b.id}. {b.name}")
                
                building_id = int(input("\nشناسه مجتمع: ").strip())
                units = self.get_all_units(building_id)
                if not units:
                    print("❌ هیچ واحدی برای این مجتمع ثبت نشده است.")
                else:
                    print("\n📋 لیست واحدها:")
                    for u in units:
                        print(f"   {u.id}. واحد {u.unit_number} - {u.owner_name} - تلفن: {u.owner_phone or '-'} - متراژ: {u.area} متر")
            
            elif choice == "8":
                print("👋 خروج از مدیریت مجتمع.")
                break
            
            else:
                print("❌ انتخاب نامعتبر.")


if __name__ == "__main__":
    manager = BuildingManager()
    
    print("🏢 سامانه مدیریت مجتمع‌های مسکونی و تجاری")
    print("=" * 50)
    print("این سیستم در دسته 'خدماتی' قرار می‌گیرد.")
    print("قابلیت‌ها:")
    print("  • ثبت مجتمع و واحدها")
    print("  • ثبت هزینه‌های مشاعات")
    print("  • محاسبه خودکار شارژ بر اساس متراژ")
    print("  • صدور قبض برای هر واحد")
    print("  • اعتبارسنجی شماره موبایل")
    print("-" * 50)
    
    user_id = 1
    manager.interactive_building_manager(user_id)