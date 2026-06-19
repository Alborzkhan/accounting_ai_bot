# core/voucher_editor.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from sqlalchemy.orm import sessionmaker
from database.models import init_db, JournalEntry, JournalLine, Account
from core.accounting_engine import AccountingEngine
import jdatetime
from typing import List, Dict, Optional

class VoucherEditor:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self.acc_engine = AccountingEngine(db_path)
    
    def to_shamsi_datetime(self, gregorian_datetime: datetime) -> str:
        """تبدیل تاریخ و زمان میلادی به شمسی"""
        try:
            shamsi = jdatetime.datetime.fromgregorian(datetime=gregorian_datetime)
            return shamsi.strftime('%Y/%m/%d %H:%M:%S')
        except:
            return gregorian_datetime.strftime('%Y-%m-%d %H:%M:%S')
    
    def to_shamsi(self, gregorian_date: datetime) -> str:
        """تبدیل تاریخ میلادی به شمسی"""
        try:
            shamsi = jdatetime.date.fromgregorian(date=gregorian_date)
            return shamsi.strftime('%Y/%m/%d')
        except:
            return gregorian_date.strftime('%Y-%m-%d')
    
    def get_voucher(self, voucher_id: int) -> Optional[Dict]:
        """دریافت سند با شماره مشخص"""
        session = self.Session()
        try:
            entry = session.query(JournalEntry).filter(
                JournalEntry.id == voucher_id
            ).first()
            
            if not entry:
                return None
            
            lines = session.query(JournalLine).filter(
                JournalLine.entry_id == voucher_id
            ).all()
            
            for line in lines:
                account = session.query(Account).filter(
                    Account.id == line.account_id
                ).first()
                line.account_code = account.code if account else None
                line.account_name = account.name if account else None
            
            return {"entry": entry, "lines": lines}
        finally:
            session.close()
    
    def get_all_vouchers(self, limit: int = 50) -> List[JournalEntry]:
        """دریافت لیست آخرین اسناد"""
        session = self.Session()
        try:
            entries = session.query(JournalEntry).order_by(
                JournalEntry.id.desc()
            ).limit(limit).all()
            return entries
        finally:
            session.close()
    
    def update_voucher(self, voucher_id: int, description: Optional[str] = None, lines: Optional[list] = None) -> Dict:
        """ویرایش سند موجود"""
        session = self.Session()
        try:
            entry = session.query(JournalEntry).filter(
                JournalEntry.id == voucher_id
            ).first()
            
            if not entry:
                return {"success": False, "message": f"❌ سند شماره {voucher_id} یافت نشد."}
            
            if description:
                entry.description = description
            
            if lines:
                # حذف خطوط قدیمی
                session.query(JournalLine).filter(
                    JournalLine.entry_id == voucher_id
                ).delete()
                
                # اضافه کردن خطوط جدید
                for account_code, amount, side in lines:
                    account = session.query(Account).filter_by(code=account_code).first()
                    if not account:
                        raise ValueError(f"حساب با کد {account_code} یافت نشد.")
                    
                    new_line = JournalLine(
                        entry_id=voucher_id,
                        account_id=account.id,
                        side=side,
                        amount=amount,
                        description=entry.description[:200]
                    )
                    session.add(new_line)
            
            session.commit()
            return {"success": True, "message": f"✅ سند شماره {voucher_id} با موفقیت ویرایش شد."}
            
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {str(e)}"}
        finally:
            session.close()
    
    def delete_voucher(self, voucher_id: int) -> Dict:
        """حذف سند"""
        session = self.Session()
        try:
            entry = session.query(JournalEntry).filter(
                JournalEntry.id == voucher_id
            ).first()
            
            if not entry:
                return {"success": False, "message": f"❌ سند شماره {voucher_id} یافت نشد."}
            
            session.query(JournalLine).filter(
                JournalLine.entry_id == voucher_id
            ).delete()
            session.delete(entry)
            session.commit()
            
            return {"success": True, "message": f"✅ سند شماره {voucher_id} با موفقیت حذف شد."}
            
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {str(e)}"}
        finally:
            session.close()
    
    def show_voucher_details(self, voucher_id: int) -> Optional[Dict]:
        """نمایش جزئیات سند"""
        voucher_data = self.get_voucher(voucher_id)
        if not voucher_data:
            print(f"❌ سند شماره {voucher_id} یافت نشد.")
            return None
        
        entry = voucher_data['entry']
        lines = voucher_data['lines']
        
        date_str = self.to_shamsi_datetime(entry.date)
        
        print(f"\n📄 **سند شماره {entry.id}**")
        print(f"   تاریخ: {date_str}")
        print(f"   شرح: {entry.description}")
        if entry.reference_no:
            print(f"   شماره مرجع: {entry.reference_no}")
        print(f"\n   آرتیکل‌ها:")
        for line in lines:
            code_disp = line.account_code if hasattr(line, 'account_code') else "---"
            name_disp = line.account_name if hasattr(line, 'account_name') else f"حساب {line.account_id}"
            print(f"     {code_disp} - {name_disp}: {line.side} {line.amount:,.0f}")
        
        return voucher_data
    
    def interactive_edit_voucher(self, voucher_id: int) -> None:
        """ویرایش سند با شماره مشخص (بدون جستجو)"""
        voucher_data = self.show_voucher_details(voucher_id)
        if not voucher_data:
            return
        
        print("\n" + "-" * 35)
        print("1. ویرایش شرح سند")
        print("2. ویرایش آرتیکل‌ها (بدهکار/بستانکار)")
        print("3. حذف سند")
        print("4. انصراف")
        
        choice = input("\nانتخاب کنید: ").strip()
        
        if choice == "1":
            new_desc = input("شرح جدید: ").strip()
            if new_desc:
                result = self.update_voucher(voucher_id, description=new_desc)
                print(result['message'])
            else:
                print("❌ شرح جدید وارد نشد.")
        
        elif choice == "2":
            print("\n⚠️ وارد کردن آرتیکل‌های جدید:")
            print("   فرمت: کدحساب:مبلغ:debit/credit")
            print("   مثال: 1201:5000000:debit")
            print("   (برای پایان 'done' را وارد کنید)")
            
            new_lines = []
            total_debit = 0
            total_credit = 0
            
            while True:
                line_input = input("آرتیکل جدید: ").strip()
                if line_input.lower() == 'done':
                    break
                if not line_input:
                    continue
                try:
                    parts = line_input.split(':')
                    if len(parts) != 3:
                        print("❌ فرمت نامعتبر. مثال: 1201:5000000:debit")
                        continue
                    account_code = parts[0].strip()
                    amount = float(parts[1].strip())
                    side = parts[2].strip().lower()
                    if side not in ['debit', 'credit']:
                        print("❌ سمت باید debit یا credit باشد")
                        continue
                    new_lines.append((account_code, amount, side))
                    if side == 'debit':
                        total_debit += amount
                    else:
                        total_credit += amount
                    print(f"✅ اضافه شد: {account_code} - {amount:,.0f} - {side}")
                    print(f"   جمع بدهکار: {total_debit:,.0f} | جمع بستانکار: {total_credit:,.0f}")
                except ValueError:
                    print("❌ مبلغ نامعتبر. عدد وارد کنید.")
                except Exception as e:
                    print(f"❌ خطا: {e}")
            
            if new_lines:
                if abs(total_debit - total_credit) > 0.01:
                    print(f"\n⚠️ هشدار: جمع بدهکار ({total_debit:,.0f}) با بستانکار ({total_credit:,.0f}) برابر نیست!")
                    confirm = input("آیا ادامه می‌دهید؟ (بله/خیر): ").strip()
                    if confirm not in ['بله', 'ب', 'yes', 'y']:
                        print("❌ عملیات لغو شد.")
                        return
                
                result = self.update_voucher(voucher_id, lines=new_lines)
                print(result['message'])
            else:
                print("❌ هیچ آرتیکلی وارد نشد.")
        
        elif choice == "3":
            confirm = input(f"آیا از حذف سند شماره {voucher_id} مطمئن هستید؟ (بله/خیر): ").strip()
            if confirm in ['بله', 'ب', 'yes', 'y']:
                result = self.delete_voucher(voucher_id)
                print(result['message'])
            else:
                print("❌ عملیات حذف لغو شد.")
        
        else:
            print("❌ انصراف.")
    
    def interactive_edit(self) -> None:
        """ویرایش تعاملی سند با نمایش لیست"""
        print("\n" + "=" * 50)
        print("✏️ ویرایش سند حسابداری")
        print("=" * 50)
        
        vouchers = self.get_all_vouchers(10)
        if not vouchers:
            print("❌ هیچ سندی یافت نشد.")
            return
        
        print("\n📋 آخرین اسناد:")
        for v in vouchers:
            date_str = self.to_shamsi(v.date)
            desc = v.description[:60] + "..." if len(v.description) > 60 else v.description
            print(f"  {v.id}. {date_str} - {desc}")
        
        print("\n💡 نکته: می‌توانید شماره سند را وارد کنید، یا از جستجوی هوشمند استفاده کنید.")
        choice = input("\nآیا می‌خواهید جستجو کنید؟ (بله/خیر): ").strip()
        
        if choice in ['بله', 'ب', 'yes', 'y']:
            from core.smart_voucher_finder import SmartVoucherFinder
            finder = SmartVoucherFinder()
            finder.interactive_find_and_edit()
        else:
            try:
                voucher_id = int(input("\nشماره سند مورد نظر را وارد کنید: ").strip())
                self.interactive_edit_voucher(voucher_id)
            except ValueError:
                print("❌ شماره معتبر وارد کنید.")
            except Exception as e:
                print(f"❌ خطا: {e}")


if __name__ == "__main__":
    editor = VoucherEditor()
    
    print("🔧 سامانه ویرایش اسناد حسابداری")
    print("=" * 40)
    print("گزینه‌ها:")
    print("1. نمایش و ویرایش آخرین اسناد")
    print("2. جستجوی هوشمند سند")
    
    mode = input("\nانتخاب کنید (1 یا 2): ").strip()
    
    if mode == "2":
        from core.smart_voucher_finder import SmartVoucherFinder
        finder = SmartVoucherFinder()
        finder.interactive_find_and_edit()
    else:
        editor.interactive_edit()