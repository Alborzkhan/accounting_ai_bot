# core/smart_voucher_finder.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import or_, and_
from database.models import init_db, JournalEntry, JournalLine, Account, Customer, Vendor
import jdatetime
from typing import List, Dict, Optional, Any

class SmartVoucherFinder:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
    
    def to_shamsi(self, gregorian_date: datetime) -> str:
        """تبدیل تاریخ میلادی به شمسی"""
        try:
            shamsi = jdatetime.date.fromgregorian(date=gregorian_date)
            return shamsi.strftime('%Y/%m/%d')
        except:
            return gregorian_date.strftime('%Y-%m-%d')
    
    def to_shamsi_datetime(self, gregorian_datetime: datetime) -> str:
        """تبدیل تاریخ و زمان میلادی به شمسی"""
        try:
            shamsi = jdatetime.datetime.fromgregorian(datetime=gregorian_datetime)
            return shamsi.strftime('%Y/%m/%d %H:%M:%S')
        except:
            return gregorian_datetime.strftime('%Y-%m-%d %H:%M:%S')
    
    def search_vouchers(self, search_text: str, limit: int = 10) -> List[JournalEntry]:
        """جستجوی هوشمند سندها بر اساس متن"""
        session = self.Session()
        try:
            # جستجوی مستقیم
            entries = session.query(JournalEntry).filter(
                JournalEntry.description.like(f"%{search_text}%")
            ).order_by(JournalEntry.id.desc()).limit(limit).all()
            
            # اگر پیدا نشد، با کلمات کلیدی
            if not entries and len(search_text) > 3:
                keywords = search_text.split()
                conditions = []
                for kw in keywords:
                    if len(kw) > 2:
                        conditions.append(JournalEntry.description.like(f"%{kw}%"))
                if conditions:
                    entries = session.query(JournalEntry).filter(
                        or_(*conditions)
                    ).order_by(JournalEntry.id.desc()).limit(limit).all()
            
            return entries
        finally:
            session.close()
    
    def search_by_date_range(self, from_date: datetime, to_date: datetime, limit: int = 20) -> List[JournalEntry]:
        """جستجوی سندها در بازه زمانی"""
        session = self.Session()
        try:
            entries = session.query(JournalEntry).filter(
                and_(
                    JournalEntry.date >= from_date,
                    JournalEntry.date <= to_date
                )
            ).order_by(JournalEntry.id.desc()).limit(limit).all()
            return entries
        finally:
            session.close()
    
    def get_all_vouchers(self, limit: int = 20) -> List[JournalEntry]:
        """دریافت آخرین سندها"""
        session = self.Session()
        try:
            entries = session.query(JournalEntry).order_by(
                JournalEntry.id.desc()
            ).limit(limit).all()
            return entries
        finally:
            session.close()
    
    def format_voucher_list(self, entries: List[JournalEntry]) -> str:
        """فرمت کردن لیست سندها"""
        if not entries:
            return "❌ هیچ سندی با این توضیحات پیدا نشد."
        
        result = "\n📋 **لیست سندهای پیدا شده:**\n\n"
        for e in entries:
            date_str = self.to_shamsi(e.date)
            desc = e.description[:70] + "..." if len(e.description) > 70 else e.description
            result += f"📄 **شماره {e.id}** | {date_str}\n"
            result += f"   {desc}\n"
            result += "   " + "─" * 35 + "\n"
        return result
    
    def get_voucher_details(self, voucher_id: int) -> Optional[Dict]:
        """دریافت جزئیات کامل سند"""
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
    
    def show_voucher_details(self, voucher_id: int) -> Optional[Dict]:
        """نمایش جزئیات سند به کاربر"""
        data = self.get_voucher_details(voucher_id)
        if not data:
            print(f"❌ سند شماره {voucher_id} یافت نشد.")
            return None
        
        entry = data['entry']
        lines = data['lines']
        
        date_str = self.to_shamsi_datetime(entry.date)
        
        print(f"\n📄 **سند شماره {entry.id}**")
        print(f"   تاریخ: {date_str}")
        print(f"   شرح: {entry.description}")
        if entry.reference_no:
            print(f"   شماره مرجع: {entry.reference_no}")
        print(f"\n   آرتیکل‌ها:")
        for line in lines:
            code_disp = line.account_code if line.account_code else "---"
            name_disp = line.account_name if line.account_name else f"حساب {line.account_id}"
            print(f"     {code_disp} - {name_disp}: {line.side} {line.amount:,.0f}")
        
        return data
    
    def interactive_find_and_edit(self) -> None:
        """جستجوی تعاملی و ویرایش سند"""
        print("\n" + "=" * 55)
        print("🔍 جستجوی هوشمند سند برای ویرایش")
        print("=" * 55)
        print("\nجمله مورد نظر را بگویید، مثلاً:")
        print("  • 'خریدی که از شرکت آذر کردم'")
        print("  • 'فروش به علی کریمی'")
        print("  • 'پرداخت حقوق'")
        print("  • 'نمایش همه سندها'")
        
        search_text = input("\n🔎 جستجو: ").strip()
        
        if not search_text:
            print("❌ عبارتی وارد نشد.")
            return
        
        # جستجو
        if search_text in ['همه', 'همه سندها', 'لیست', 'نمایش همه']:
            entries = self.get_all_vouchers(20)
            print("\n📋 **آخرین سندها:**")
        else:
            entries = self.search_vouchers(search_text)
            
            if not entries:
                words = search_text.split()
                for word in words:
                    if len(word) > 3:
                        entries = self.search_vouchers(word)
                        if entries:
                            print(f"\n⚠️ با کلمه '{word}' جستجو شد:")
                            break
        
        print(self.format_voucher_list(entries))
        
        if not entries:
            return
        
        try:
            choice = input("\nشماره سند را وارد کنید (یا 0 برای انصراف): ").strip()
            if choice == "0" or not choice:
                print("❌ انصراف.")
                return
            
            voucher_id = int(choice)
            
            # بررسی وجود سند
            data = self.show_voucher_details(voucher_id)
            if not data:
                return
            
            # منوی ویرایش
            print("\n" + "-" * 35)
            print("1. ویرایش شرح سند")
            print("2. ویرایش آرتیکل‌ها (بدهکار/بستانکار)")
            print("3. حذف سند")
            print("4. انصراف")
            
            option = input("\nانتخاب کنید: ").strip()
            
            if option == "1":
                new_desc = input("شرح جدید: ").strip()
                if new_desc:
                    from core.voucher_editor import VoucherEditor
                    editor = VoucherEditor()
                    result = editor.update_voucher(voucher_id, description=new_desc)
                    print(result['message'])
                else:
                    print("❌ شرح جدید وارد نشد.")
            
            elif option == "2":
                print("\n⚠️ فرمت آرتیکل: کدحساب:مبلغ:debit/credit")
                print("   مثال: 1201:5000000:debit")
                print("   مثال: 2001:5000000:credit")
                print("   (برای پایان کلمه 'done' را وارد کنید)")
                
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
                    
                    from core.voucher_editor import VoucherEditor
                    editor = VoucherEditor()
                    result = editor.update_voucher(voucher_id, lines=new_lines)
                    print(result['message'])
                else:
                    print("❌ هیچ آرتیکلی وارد نشد.")
            
            elif option == "3":
                confirm = input(f"آیا از حذف سند شماره {voucher_id} مطمئن هستید؟ (بله/خیر): ").strip()
                if confirm in ['بله', 'ب', 'yes', 'y']:
                    from core.voucher_editor import VoucherEditor
                    editor = VoucherEditor()
                    result = editor.delete_voucher(voucher_id)
                    print(result['message'])
                else:
                    print("❌ حذف سند لغو شد.")
            
            else:
                print("❌ انصراف.")
                
        except ValueError:
            print("❌ شماره معتبر وارد کنید. عدد وارد کنید.")
        except KeyboardInterrupt:
            print("\n❌ انصراف.")
        except Exception as e:
            print(f"❌ خطا: {e}")


if __name__ == "__main__":
    finder = SmartVoucherFinder()
    finder.interactive_find_and_edit()