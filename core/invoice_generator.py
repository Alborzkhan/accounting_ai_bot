# core/invoice_generator.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from sqlalchemy.orm import sessionmaker
from database.models import (
    init_db, Customer, SellerProfile, 
    ProformaInvoice, InvoiceItem
)
from core.seller_manager import SellerManager
from core.product_manager import ProductManager
from core.accounting_engine import AccountingEngine

class InvoiceGenerator:
    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)
        self.seller_manager = SellerManager(db_path)
        self.product_manager = ProductManager(db_path)
        self.accounting_engine = AccountingEngine(db_path)
    
    def get_next_invoice_number(self) -> str:
        session = self.Session()
        try:
            last_invoice = session.query(ProformaInvoice).order_by(
                ProformaInvoice.id.desc()
            ).first()
            
            if last_invoice and last_invoice.invoice_number:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            return f"INV-{datetime.now().strftime('%Y%m')}-{new_num:04d}"
        finally:
            session.close()
    
    def create_invoice(
        self,
        customer_id: int,
        items: List[Dict],
        description: str = "",
        vat_rate: float = 0.0,
        apply_vat: bool = False
    ) -> Dict:
        session = self.Session()
        try:
            subtotal = 0
            for item in items:
                item_total = item['quantity'] * item['unit_price']
                item['total'] = item_total
                subtotal += item_total
            
            vat_amount = 0
            if apply_vat and vat_rate > 0:
                vat_amount = subtotal * (vat_rate / 100)
            
            total = subtotal + vat_amount
            
            invoice = ProformaInvoice(
                invoice_number=self.get_next_invoice_number(),
                date=datetime.now(),
                customer_id=customer_id,
                subtotal=subtotal,
                vat_rate=vat_rate if apply_vat else 0,
                vat_amount=vat_amount,
                total=total,
                is_vat_applied=apply_vat,
                description=description
            )
            session.add(invoice)
            session.flush()
            
            for item in items:
                invoice_item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=item['description'],
                    quantity=item['quantity'],
                    unit=item.get('unit', 'عدد'),
                    unit_price=item['unit_price'],
                    total=item['total']
                )
                session.add(invoice_item)
            
            session.commit()
            
            return {
                "success": True,
                "invoice": invoice,
                "message": f"✅ پیش‌فاکتور شماره {invoice.invoice_number} با موفقیت ایجاد شد."
            }
            
        except Exception as e:
            session.rollback()
            return {"success": False, "message": f"❌ خطا: {str(e)}"}
        finally:
            session.close()
    
    def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        session = self.Session()
        try:
            invoice = session.query(ProformaInvoice).filter(
                ProformaInvoice.id == invoice_id
            ).first()
            
            if not invoice:
                return None
            
            items = session.query(InvoiceItem).filter(
                InvoiceItem.invoice_id == invoice.id
            ).all()
            
            seller = self.seller_manager.get_profile()
            customer = session.query(Customer).filter(
                Customer.id == invoice.customer_id
            ).first()
            
            return {
                "invoice": invoice,
                "items": items,
                "seller": seller,
                "customer": customer
            }
        finally:
            session.close()
    
    def extract_number_and_unit(self, input_str: str) -> Tuple[float, str]:
        num_str = ''
        unit_str = ''
        for ch in input_str:
            if ch.isdigit() or ch == '.':
                num_str += ch
            else:
                unit_str += ch
        num = float(num_str) if num_str else 1
        unit = unit_str.strip() or 'عدد'
        return num, unit
    
    def is_yes(self, text: str) -> bool:
        yes_words = ['بله', 'آره', 'ها', 'اره', 'yeah', 'yes', 'y', 'ب']
        return text.strip().lower() in yes_words
    
    def is_no(self, text: str) -> bool:
        no_words = ['نه', 'نخیر', 'no', 'n', 'خیر']
        return text.strip().lower() in no_words
    
    def is_done(self, text: str) -> bool:
        done_words = ['تمام', 'همینا', 'همین‌ها', 'بستن', 'پایان', 'done', 'enough']
        return text.strip().lower() in done_words
    
    def find_customer(self, session: Any, search_name: str) -> Tuple[Optional[Customer], str]:
        customers = session.query(Customer).filter(
            Customer.name.like(f"%{search_name}%")
        ).all()
        
        if not customers:
            return None, "not_found"
        
        if len(customers) == 1:
            return customers[0], "single"
        
        print(f"\n⚠️ چندین مشتری با نام '{search_name}' یافت شد:")
        for i, c in enumerate(customers, 1):
            print(f"  {i}. {c.name} - موبایل: {c.mobile or 'ندارد'} | تلفن: {c.phone or 'ندارد'}")
        
        if len(customers) > 3:
            phone_search = input("\nلطفاً شماره موبایل مشتری را وارد کنید: ").strip()
            exact_customer = session.query(Customer).filter(
                Customer.mobile.like(f"%{phone_search}%")
            ).first()
            if exact_customer:
                return exact_customer, "exact_phone"
            else:
                return None, "phone_not_found"
        else:
            choice = input("\nشماره مورد نظر را انتخاب کنید (یا 0 برای انصراف): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(customers):
                return customers[int(choice)-1], "selected"
            else:
                return None, "cancelled"
    
    def interactive_create_invoice(self) -> None:
        print("\n" + "=" * 50)
        print("📄 ایجاد پیش‌فاکتور جدید")
        print("=" * 50)
        
        session = self.Session()
        try:
            # جستجوی مشتری
            print("\n📋 جستجوی مشتری:")
            search_name = input("نام یا فامیل مشتری را وارد کنید: ").strip()
            
            if not search_name:
                print("❌ نام مشتری وارد نشد.")
                return
            
            customer, status = self.find_customer(session, search_name)
            
            if status == "not_found":
                print(f"❌ مشتری با نام '{search_name}' یافت نشد.")
                create_new = input("آیا مشتری جدید ثبت کنید؟ (بله/خیر): ").strip()
                if self.is_yes(create_new):
                    name = input("نام کامل مشتری: ").strip()
                    print("\n📞 اطلاعات تماس (حداقل یکی از موارد زیر الزامی است):")
                    mobile = input("شماره موبایل (مثال: 09121234567): ").strip()
                    phone = input("شماره تلفن ثابت (مثال: 02112345678): ").strip()
                    
                    try:
                        cust_id = self.accounting_engine.add_customer(name, mobile, phone)
                        customer_id = cust_id
                    except ValueError as e:
                        print(f"\n❌ {e}")
                        return
                else:
                    print("❌ ایجاد فاکتور لغو شد.")
                    return
            elif status in ["single", "exact_phone", "selected"]:
                customer_id = customer.id
                mobile_display = customer.mobile or 'ندارد'
                phone_display = customer.phone or 'ندارد'
                print(f"✅ مشتری انتخاب شد: {customer.name} - موبایل: {mobile_display} | تلفن: {phone_display}")
            else:
                print("❌ ایجاد فاکتور لغو شد.")
                return
            
            # تنظیمات مالیات
            print("\n💰 تنظیمات مالیات بر ارزش افزوده:")
            apply_vat_input = input("آیا مالیات اعمال شود؟ (بله/خیر): ").strip()
            apply_vat = self.is_yes(apply_vat_input)
            vat_rate = 0
            if apply_vat:
                vat_rate_input = input("درصد مالیات (مثلاً 10): ").strip()
                vat_rate = float(vat_rate_input) if vat_rate_input else 10
            
            # وارد کردن کالاها
            items = []
            print("\n🛒 وارد کردن کالاها/خدمات")
            print("💡 نکته: تعداد را با واحد وارد کنید (مثال: 25 کیلو، 10 متر، 100 عدد)")
            print("📝 برای پایان، کلمه 'تمام' یا 'همینا' را وارد کنید.\n")
            
            while True:
                desc_input = input("شرح کالا/خدمت: ").strip()
                if not desc_input:
                    continue
                
                if self.is_done(desc_input):
                    break
                
                product, p_status = self.product_manager.find_or_ask_product(desc_input)
                
                if p_status == "not_found":
                    print(f"⚠️ کالای '{desc_input}' در لیست محصولات یافت نشد.")
                    add_new = input("آیا این کالا را به لیست اضافه کنید؟ (بله/خیر): ").strip()
                    if self.is_yes(add_new):
                        unit_input = input("واحد (مثال: کیلو، متر، عدد): ").strip() or "عدد"
                        price_input = input("قیمت واحد (تومان): ").strip()
                        try:
                            price = float(price_input)
                        except:
                            price = 0
                        product = self.product_manager.add_product(desc_input, unit_input, price)
                        desc = product.name
                        unit = product.unit
                        default_price = product.price
                        print(f"✅ کالای {desc} با موفقیت اضافه شد.")
                    else:
                        print("❌ ورودی کالا لغو شد. دوباره تلاش کنید.")
                        continue
                elif p_status == "cancelled":
                    print("❌ ورودی کالا لغو شد. دوباره تلاش کنید.")
                    continue
                elif p_status in ["single", "selected"]:
                    desc = product.name
                    unit = product.unit
                    default_price = product.price
                
                qty_input = input("تعداد (مثال: 25 کیلو): ").strip()
                qty, _ = self.extract_number_and_unit(qty_input)
                
                price_input = input(f"قیمت واحد (تومان) [پیش‌فرض: {default_price:,.0f}]: ").strip()
                price = float(price_input) if price_input else default_price
                
                items.append({
                    "description": desc,
                    "quantity": qty,
                    "unit": unit,
                    "unit_price": price
                })
                print(f"✅ {desc} با تعداد {qty} {unit} اضافه شد.\n")
                
                more = input("آیا کالای دیگری اضافه می‌کنید؟ (بله/خیر): ").strip()
                if self.is_no(more):
                    break
            
            if not items:
                print("❌ هیچ کالایی وارد نشد.")
                return
            
            description = input("\nتوضیحات اضافی (اختیاری): ").strip() or ""
            
            result = self.create_invoice(
                customer_id=customer_id,
                items=items,
                description=description,
                vat_rate=vat_rate,
                apply_vat=apply_vat
            )
            
            print(f"\n{result['message']}")
            if result['success']:
                inv = result['invoice']
                print(f"\n📊 خلاصه فاکتور:")
                print(f"  شماره: {inv.invoice_number}")
                print(f"  جمع کل: {inv.subtotal:,.0f} تومان")
                if apply_vat:
                    print(f"  مالیات ({inv.vat_rate:.0f}%): {inv.vat_amount:,.0f} تومان")
                print(f"  مبلغ نهایی: {inv.total:,.0f} تومان")
            
        except Exception as e:
            print(f"❌ خطا: {str(e)}")
        finally:
            session.close()


if __name__ == "__main__":
    generator = InvoiceGenerator()
    generator.interactive_create_invoice()