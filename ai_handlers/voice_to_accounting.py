import whisper
import os
import re
from typing import Dict, Tuple

class VoiceToAccounting:
    def __init__(self, model_size: str = "base") -> None:
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
        os.makedirs(cache_dir, exist_ok=True)
        model_path = os.path.join(cache_dir, f"{model_size}.pt")

        if not os.path.exists(model_path):
            print(f"مدل {model_size} یافت نشد. در حال دانلود...")
            import requests
            url = "https://hf-mirror.com/openai/whisper-base/resolve/main/pytorch_model.bin"
            response = requests.get(url, stream=True)
            with open(model_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print("دانلود کامل شد.")

        print(f"🔄 در حال بارگذاری مدل Whisper ({model_size})...")
        self.model = whisper.load_model(model_path)
        print("✅ مدل بارگذاری شد.")
    
    def transcribe_voice(self, audio_path: str) -> str:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"فایل {audio_path} یافت نشد.")
        result = self.model.transcribe(audio_path, language=None, task="transcribe")
        return result["text"]
    
    def extract_amount(self, text: str) -> int:
        """استخراج مبلغ از متن با پشتیبانی از اعداد و حروف"""
        text = text.replace(',', '')
        
        # تبدیل حروف به اعداد
        word_to_number = {
            'یک': 1, 'دو': 2, 'سه': 3, 'چهار': 4, 'پنج': 5, 'پنچه': 5,
            'شش': 6, 'هفت': 7, 'هشت': 8, 'نه': 9, 'ده': 10,
            'بیست': 20, 'سی': 30, 'چهل': 40, 'پنجاه': 50,
            'شصت': 60, 'هفتاد': 70, 'هشتاد': 80, 'نود': 90,
            'صد': 100, 'دویست': 200, 'سیصد': 300, 'چهارصد': 400,
            'پانصد': 500, 'ششصد': 600, 'هفتصد': 700, 'هشتصد': 800,
            'نهصد': 900, 'هزار': 1000
        }
        
        words = text.split()
        for i, word in enumerate(words):
            if word in word_to_number:
                num = word_to_number[word]
                if i + 1 < len(words) and words[i + 1] == 'هزار':
                    return num * 1000
                if len(words) == 1:
                    return num
                return num
        
        # الگوهای عددی
        patterns = [
            r'(\d+)\s*(?:تومان|هزار|میلیون)',
            r'(\d+)\s*(?:toman|thousand|million)',
            r'(\d+)\s*$',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = int(match.group(1))
                if "هزار" in text or "thousand" in text or "زارتومن" in text:
                    amount *= 1000
                elif "میلیون" in text or "million" in text:
                    amount *= 1_000_000
                return amount
        
        numbers = re.findall(r'\d+', text)
        if numbers:
            amount = int(numbers[-1])
            if 'زارتومن' in text or 'هزار' in text:
                amount *= 1000
            return amount
        
        return 0
    
    def voice_to_voucher(self, audio_path: str) -> Tuple[Dict, str]:
        print("🎤 در حال تبدیل صدا به متن...")
        text = self.transcribe_voice(audio_path)
        print(f"📝 متن تشخیص داده شده: {text}")
        
        text_lower = text.lower()
        
        data = {
            "type": None,
            "amount": 0,
            "description": text,
            "debit_account": None,
            "credit_account": None,
        }
        
        # تشخیص نوع عملیات (فارسی و انگلیسی)
        if "خرید" in text or "buy" in text_lower or "purchase" in text_lower or "by" in text_lower:
            data["type"] = "خرید"
            data["debit_account"] = "1201"
            data["credit_account"] = "2001"
        elif "فروش" in text or "sell" in text_lower or "sale" in text_lower:
            data["type"] = "فروش"
            data["debit_account"] = "1101"
            data["credit_account"] = "4001"
        elif "پرداخت" in text or "pay" in text_lower:
            data["type"] = "پرداخت"
            data["debit_account"] = "2001"
            data["credit_account"] = "1001"
        elif "دریافت" in text or "receive" in text_lower:
            data["type"] = "دریافت"
            data["debit_account"] = "1001"
            data["credit_account"] = "1101"
        
        # استخراج مبلغ
        data["amount"] = self.extract_amount(text)
        
        # اصلاح مبلغ اگر "زارتومن" در متن بود و مبلغ کمتر از 100 بود
        if 'زارتومن' in text and data["amount"] < 100 and data["amount"] > 0:
            data["amount"] = data["amount"] * 1000
        
        return data, text


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        engine = VoiceToAccounting(model_size="base")
        data, transcript = engine.voice_to_voucher(audio_file)
        
        print("\n" + "=" * 50)
        print("📊 اطلاعات استخراج شده:")
        print(f"نوع عملیات: {data['type']}")
        print(f"مبلغ: {data['amount']:,} تومان")
        print(f"حساب بدهکار: {data['debit_account']}")
        print(f"حساب بستانکار: {data['credit_account']}")
        print(f"شرح: {data['description'][:100]}")
        print("=" * 50)
        
        if data["type"] and data["amount"] > 0:
            print("\n✅ اطلاعات آماده ثبت در دیتابیس است.")
        else:
            if not data["type"]:
                print("\n⚠️ نوع عملیات تشخیص داده نشد. از کلمات 'خرید' یا 'فروش' استفاده کنید.")
            if data["amount"] == 0:
                print("\n⚠️ مبلغ تشخیص داده نشد. لطفاً عدد را واضح‌تر بگویید.")
    else:
        print("=" * 50)
        print("🤖 سیستم تبدیل ویس به سند حسابداری")
        print("=" * 50)
        print("\nنحوه استفاده:")
        print("  python voice_to_accounting.py <مسیر فایل صوتی>")
        print("\nمثال:")
        print("  python voice_to_accounting.py voice_files/my_voice.mp3")
        print("\nجمله‌های قابل تشخیص:")
        print("  - خرید 100 عدد خودکار 5000 تومان")
        print("  - فروش 50 عدد کتاب 20000 تومان")
        print("  - buy 100 pens 5000 tomans")
        print("=" * 50)