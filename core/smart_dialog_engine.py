# core/smart_dialog_engine.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from core.accounting_engine import AccountingEngine
from database.models import Customer, Vendor, JournalLine, JournalEntry

class SmartDialogEngine:
    def __init__(self, engine: AccountingEngine) -> None:
        self.engine = engine
        self.session_data = {}
        self.transaction_keywords = {
            'payment_received': ['پول زد', 'واریز کرد', 'پرداخت کرد', 'تسویه', 'حساب واریز', 'پول داد', 'وصول', 'دریافت'],
            'payment_sent': ['پرداخت به', 'انتقال به', 'واریز به', 'پول داد به'],
            'sale': ['فروش', 'خریداری کرد', 'فروخت'],
            'purchase': ['خرید', 'خریداری'],
            'customer_balance': ['مانده حساب', 'چقدر بدهکار است', 'تسویه حساب', 'چقدر بدهی', 'بدهی', 'باقی']
        }
    
    def _clean_customer_name(self, text: str) -> str:
        """استخراج نام مشتری از متن بدون اعداد و کلمات اضافی"""
        # حذف کلمات کلیدی ابتدایی
        text = re.sub(r'^(مانده\s*حساب|مشتری|بدهی|چقدر|باقی)\s*', '', text)
        
        # حذف اعداد و کلمات عددی
        text = re.sub(r'\d+', '', text)
        
        # حذف کلمات مربوط به مبلغ
        amount_words = ['هزار', 'میلیون', 'میلیارد', 'تومان', 'ریال', 'پول', 'زد', 'واریز', 'کرد', 'پرداخت', 'تسویه', 'دریافت']
        for word in amount_words:
            text = text.replace(word, '')
        
        # حذف فاصله‌های اضافی
        text = ' '.join(text.split())
        
        return text.strip()
    
    def _extract_amount(self, text: str) -> int:
        """استخراج مبلغ از متن با پشتیبانی از اعداد و حروف"""
        text = text.replace(',', '')
        
        # الگوهای عددی
        patterns = [
            r'(\d+)\s*(?:هزار|میلیون|میلیارد)',
            r'(\d+)\s*(?:تومان|ریال)',
            r'(\d+)\s*$',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                amount = int(match.group(1))
                if 'هزار' in text:
                    amount *= 1000
                elif 'میلیون' in text:
                    amount *= 1_000_000
                elif 'میلیارد' in text:
                    amount *= 1_000_000_000
                return amount
        
        # تشخیص کلمات عددی
        word_to_number = {
            'یک': 1, 'دو': 2, 'سه': 3, 'چهار': 4, 'پنج': 5,
            'شش': 6, 'هفت': 7, 'هشت': 8, 'نه': 9, 'ده': 10,
            'بیست': 20, 'سی': 30, 'چهل': 40, 'پنجاه': 50,
            'صد': 100, 'دویست': 200, 'سیصد': 300, 'چهارصد': 400,
            'پانصد': 500, 'ششصد': 600, 'هفتصد': 700, 'هشتصد': 800,
            'نهصد': 900, 'هزار': 1000
        }
        
        words = text.split()
        multiplier_words = {'هزار': 1000, 'میلیون': 1_000_000, 'میلیارد': 1_000_000_000}
        total = 0
        i = 0
        while i < len(words):
            word = words[i]
            if word in word_to_number:
                value = word_to_number[word]
                if i + 1 < len(words) and words[i + 1] in multiplier_words:
                    value *= multiplier_words[words[i + 1]]
                    i += 1
                total += value
            i += 1
        if total > 0:
            return total
        
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[-1])
        
        return 0
    
    def detect_intent(self, text: str) -> Dict:
        """تشخیص نیت کاربر از متن"""
        result = {
            'intent': None,
            'entities': {},
            'missing_info': [],
            'suggested_question': None
        }
        
        # 1. تشخیص تسویه حساب مشتری (دریافت پول)
        if any(kw in text for kw in self.transaction_keywords['payment_received']):
            result['intent'] = 'payment_received'
            
            # استخراج نام مشتری
            customer_name = self._clean_customer_name(text)
            if customer_name and len(customer_name) > 1:
                result['entities']['customer_name'] = customer_name
            else:
                result['missing_info'].append('customer_name')
            
            # استخراج مبلغ
            amount = self._extract_amount(text)
            if amount > 0:
                result['entities']['amount'] = amount
            else:
                result['missing_info'].append('amount')
        
        # 2. تشخیص پرداخت به تامین‌کننده
        elif any(kw in text for kw in self.transaction_keywords['payment_sent']):
            result['intent'] = 'payment_sent'
            
            # استخراج نام تامین‌کننده
            vendor_match = re.search(r'به\s*([^\d]+?)(?:\s*\d+|\s*$)', text)
            if vendor_match:
                vendor_name = vendor_match.group(1).strip()
                amount_words = ['هزار', 'میلیون', 'میلیارد', 'تومان', 'پرداخت', 'به']
                for word in amount_words:
                    vendor_name = vendor_name.replace(word, '')
                vendor_name = ' '.join(vendor_name.split())
                if vendor_name:
                    result['entities']['vendor_name'] = vendor_name
                else:
                    result['missing_info'].append('vendor_name')
            else:
                result['missing_info'].append('vendor_name')
            
            # استخراج مبلغ
            amount = self._extract_amount(text)
            if amount > 0:
                result['entities']['amount'] = amount
            else:
                result['missing_info'].append('amount')
        
        # 3. تشخیص سوال در مورد مانده حساب
        elif any(kw in text for kw in self.transaction_keywords['customer_balance']):
            result['intent'] = 'customer_balance'
            customer_name = self._clean_customer_name(text)
            if customer_name and len(customer_name) > 1:
                result['entities']['customer_name'] = customer_name
            else:
                result['missing_info'].append('customer_name')
        
        elif any(kw in text for kw in self.transaction_keywords['sale']):
            result['intent'] = 'sale'
        
        elif any(kw in text for kw in self.transaction_keywords['purchase']):
            result['intent'] = 'purchase'
        
        if result['missing_info']:
            result['suggested_question'] = self._generate_question(result)
        
        return result
    
    def _generate_question(self, intent_data: Dict) -> str:
        """تولید سوال هوشمند بر اساس اطلاعات ناقص"""
        intent = intent_data['intent']
        missing = intent_data['missing_info']
        
        if intent == 'payment_received':
            if 'customer_name' in missing:
                return "🤔 از کدام مشتری پول دریافت کردید؟ لطفاً نام مشتری را بگویید.\nمثال: 'علی کریمی'"
            elif 'amount' in missing:
                return "💰 مبلغ واریزی چقدر بوده؟ لطفاً عدد را به تومان بگویید.\nمثال: '۵۰۰ هزار تومان'"
        
        elif intent == 'payment_sent':
            if 'vendor_name' in missing:
                return "🤔 به چه کسی پول پرداخت کردید؟ نام طرف مقابل را بگویید.\nمثال: 'شرکت آذر'"
            elif 'amount' in missing:
                return "💰 مبلغ پرداختی چقدر بوده؟ لطفاً عدد را بگویید.\nمثال: '۲۰۰ هزار تومان'"
        
        elif intent == 'customer_balance' and 'customer_name' in missing:
            return "💰 مانده حساب کدام مشتری را می‌خواهید؟ لطفاً نام مشتری را بگویید.\nمثال: 'علی کریمی'"
        
        return "لطفاً اطلاعات کامل‌تر بگویید."
    
    def process_payment_received(self, entities: Dict) -> Dict:
        """پردازش ثبت دریافت پول از مشتری"""
        session = self.engine.Session()
        try:
            customer_name = entities.get('customer_name', '')
            amount = entities.get('amount', 0)
            
            if not customer_name:
                return {'success': False, 'message': "❌ نام مشتری تشخیص داده نشد."}
            
            if amount == 0:
                return {'success': False, 'message': "❌ مبلغ تشخیص داده نشد. لطفاً مبلغ را به تومان بگویید."}
            
            customer = session.query(Customer).filter(
                Customer.name.like(f"%{customer_name}%")
            ).first()
            
            if not customer:
                return {
                    'success': False,
                    'message': f"❌ مشتری با نام '{customer_name}' یافت نشد.\n\nلطفاً ابتدا با دستور زیر مشتری را ثبت کنید:\nمشتری: {customer_name} 0912xxxxxxx"
                }
            
            entry_id = self.engine.create_voucher(
                date=datetime.now(),
                description=f"دریافت وجه از مشتری {customer.name} به مبلغ {amount:,} تومان",
                lines=[
                    ('1001', amount, 'debit'),
                    ('1101', amount, 'credit')
                ]
            )
            
            return {
                'success': True,
                'message': f"✅ دریافت {amount:,} تومان از {customer.name} با موفقیت ثبت شد.\n📋 شماره سند: {entry_id}"
            }
        except Exception as e:
            return {'success': False, 'message': f"❌ خطا: {str(e)}"}
        finally:
            session.close()
    
    def process_payment_sent(self, entities: Dict) -> Dict:
        """پردازش ثبت پرداخت به تامین‌کننده"""
        session = self.engine.Session()
        try:
            vendor_name = entities.get('vendor_name', '')
            amount = entities.get('amount', 0)
            
            if not vendor_name:
                return {'success': False, 'message': "❌ نام گیرنده تشخیص داده نشد."}
            
            if amount == 0:
                return {'success': False, 'message': "❌ مبلغ تشخیص داده نشد."}
            
            vendor = session.query(Vendor).filter(
                Vendor.name.like(f"%{vendor_name}%")
            ).first()
            
            vendor_text = vendor.name if vendor else vendor_name
            
            if not vendor:
                return {
                    'success': False,
                    'message': f"❌ '{vendor_name}' در لیست فروشندگان یافت نشد.\n\nلطفاً ابتدا با دستور زیر فروشنده را ثبت کنید:\nفروشنده: {vendor_name} 021xxxxxxx"
                }
            
            entry_id = self.engine.create_voucher(
                date=datetime.now(),
                description=f"پرداخت به {vendor_text} به مبلغ {amount:,} تومان",
                lines=[
                    ('2001', amount, 'debit'),
                    ('1001', amount, 'credit')
                ]
            )
            
            return {
                'success': True,
                'message': f"✅ پرداخت {amount:,} تومان به {vendor_text} با موفقیت ثبت شد.\n📋 شماره سند: {entry_id}"
            }
        except Exception as e:
            return {'success': False, 'message': f"❌ خطا: {str(e)}"}
        finally:
            session.close()
    
    def process_customer_balance(self, entities: Dict) -> Dict:
        """نمایش مانده حساب مشتری"""
        session = self.engine.Session()
        try:
            customer_name = entities.get('customer_name', '')
            
            # حذف کلمات اضافی از نام مشتری
            remove_words = ['مانده', 'حساب', 'بدهی', 'چقدر', 'لطفاً', 'باقی']
            for word in remove_words:
                customer_name = customer_name.replace(word, '').strip()
            
            if not customer_name:
                return {'success': False, 'message': "❌ نام مشتری تشخیص داده نشد.\nمثال: 'مانده حساب علی کریمی'"}
            
            customer = session.query(Customer).filter(
                Customer.name.like(f"%{customer_name}%")
            ).first()
            
            if not customer:
                # نمایش لیست مشتریان موجود
                all_customers = session.query(Customer).all()
                customer_list = "\n".join([f"  • {c.name}" for c in all_customers]) if all_customers else "  • هیچ مشتری ثبت نشده است."
                return {
                    'success': False,
                    'message': f"❌ مشتری با نام '{customer_name}' یافت نشد.\n\n📋 لیست مشتریان ثبت شده:\n{customer_list}"
                }
            
            # محاسبه مانده حساب از تراز آزمایشی
            balances = self.engine.get_trial_balance()
            balance = 0
            for row in balances:
                if row.code == '1101':  # بدهکاران تجاری
                    balance = row.total_debit - row.total_credit
                    break
            
            return {
                'success': True,
                'message': f"💰 مانده حساب {customer.name}: {balance:,.0f} تومان"
            }
        except Exception as e:
            return {'success': False, 'message': f"❌ خطا: {str(e)}"}
        finally:
            session.close()
    
    def process_message(self, user_id: int, message: str) -> str:
        """پردازش اصلی پیام کاربر"""
        intent_data = self.detect_intent(message)
        
        if intent_data['missing_info']:
            return intent_data['suggested_question']
        
        if intent_data['intent'] == 'payment_received':
            result = self.process_payment_received(intent_data['entities'])
            return result['message']
        elif intent_data['intent'] == 'payment_sent':
            result = self.process_payment_sent(intent_data['entities'])
            return result['message']
        elif intent_data['intent'] == 'customer_balance':
            result = self.process_customer_balance(intent_data['entities'])
            return result['message']
        else:
            return "🤔 متوجه نشدم.\n\n📋 دستورات قابل تشخیص:\n• مشتری علی کریمی ۵۰۰ هزار تومان پول زد\n• پرداخت به شرکت آذر ۲۰۰ هزار تومان\n• مانده حساب علی کریمی"


if __name__ == "__main__":
    engine = AccountingEngine()
    dialog = SmartDialogEngine(engine)
    
    print("🧠 سیستم گفتگوی هوشمند حسابداری")
    print("=" * 50)
    print("📋 دستورات قابل تشخیص:")
    print("  • مشتری علی کریمی ۵۰۰ هزار تومان پول زد")
    print("  • پرداخت به شرکت آذر ۲۰۰ هزار تومان")
    print("  • مانده حساب علی کریمی")
    print("-" * 50)
    print("💡 نکته: اگر مشتری یا فروشنده وجود نداشته باشد، سیستم راهنمای ثبت را نشان می‌دهد.")
    print("-" * 50)
    
    while True:
        msg = input("\n👤 شما: ").strip()
        if msg == "خروج":
            print("👋 خداحافظ!")
            break
        response = dialog.process_message(1, msg)
        print(f"🤖 سیستم: {response}")