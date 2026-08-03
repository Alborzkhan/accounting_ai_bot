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
            tmp_path = model_path + ".part"
            try:
                response = requests.get(url, stream=True, timeout=(15, 60))
                response.raise_for_status()
                with open(tmp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                os.replace(tmp_path, model_path)
                print("دانلود کامل شد.")
            except Exception as e:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise RuntimeError(f"دانلود مدل Whisper ناموفق بود (شبکه؟): {e}") from e

        print(f"🔄 در حال بارگذاری مدل Whisper ({model_size})...")
        self.model = whisper.load_model(model_path)
        print("✅ مدل بارگذاری شد.")
    
    def transcribe_voice(self, audio_path: str) -> str:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"فایل {audio_path} یافت نشد.")
        # زبان را صریحاً فارسی می‌گیریم؛ در غیر این صورت Whisper روی صوت کوتاه/با لهجه ممکن است
        # زبان را اشتباه تشخیص دهد و خروجی نامفهوم (مثلاً آلمانی) بدهد.
        result = self.model.transcribe(audio_path, language="fa", task="transcribe")
        return result["text"]
    
    def extract_amount(self, text: str) -> int:
        """استخراج مبلغ از متن با پشتیبانی از اعداد فارسی/رقمی و رونویسی‌های رایج Whisper.

        فقط عددی که بلافاصله با یک واحد پول (تومان/هزار/میلیون/...) همراه باشد به‌عنوان مبلغ
        در نظر گرفته می‌شود تا اعداد کمیت (مثل «۵۰ عدد») با مبلغ اشتباه گرفته نشوند.
        """
        text = text.replace(',', '').strip()

        # نرمال‌سازی واحدها: اشکال رونویسی‌شده‌ی «هزار تومان» (بدون «ه» ابتدا) به «هزارتومان»
        # تبدیل شوند؛ با lookbehind تا داخل کلمه‌ی سالم «هزار» یا «بازار» دستکاری نشود.
        text = re.sub(r'(?<!ه)زار\s*تومان', 'هزارتومان', text)
        text = re.sub(r'(?<!ه)زارتومن\b', 'هزارتومان', text)
        text = re.sub(r'(?<!ه)زارتومان\b', 'هزارتومان', text)
        text = re.sub(r'(?<!ه)زارتوما\b', 'هزارتومان', text)
        text = re.sub(r'(?<!ه)زارتوم\b', 'هزارتومان', text)
        text = re.sub(r'(?<!\w)زار(?!\w)', 'هزار', text)   # «زار» تنها
        text = re.sub(r'حزار\b', 'هزار', text)
        text = re.sub(r'ميليونو', 'میلیون و', text)
        text = re.sub(r'میلیونو', 'میلیون و', text)
        text = re.sub(r'ميليون', 'میلیون', text)
        text = re.sub(r'ميليارد', 'میلیارد', text)

        word_to_number = {
            'یک': 1, 'دو': 2, 'سه': 3, 'چهار': 4, 'پنج': 5, 'پنچه': 5, 'پنجا': 50,
            'شش': 6, 'هفت': 7, 'هشت': 8, 'نه': 9, 'ده': 10,
            'یازده': 11, 'دوازده': 12, 'سیزده': 13, 'چهارده': 14, 'پانزده': 15,
            'شانزده': 16, 'هفده': 17, 'هجده': 18, 'نوزده': 19,
            'بیست': 20, 'سی': 30, 'چهل': 40, 'پنجاه': 50,
            'شصت': 60, 'هفتاد': 70, 'هشتاد': 80, 'نود': 90,
            'صد': 100, 'دویست': 200, 'سیصد': 300, 'چهارصد': 400,
            'پانصد': 500, 'پونصد': 500, 'پنصد': 500, 'ٹونست': 500,
            'ششصد': 600, 'هفتصد': 700, 'هشتصد': 800,
            'نهصد': 900,
            'هزار': 1000, 'هزارتومان': 1000,
            'میلیون': 1_000_000, 'میلیارد': 1_000_000_000,
        }

        words = text.split()
        n = len(words)
        result = 0
        i = 0

        def accumulate(start: int):
            """جمع اعداد فارسی/رقمی پشت‌سرهم (با «و») تا رسیدن به غیرعدد"""
            cur = 0
            j = start
            while j < n:
                w = words[j]
                if w in word_to_number and word_to_number[w] < 1000:
                    cur = (cur + word_to_number[w]) if cur else word_to_number[w]
                    j += 1
                elif w.isdigit():
                    cur = int(w)
                    j += 1
                elif w == 'و':
                    j += 1
                else:
                    break
            return cur, j

        while i < n:
            w = words[i]
            if (w in word_to_number and word_to_number[w] < 1000) or w.isdigit():
                val, j = accumulate(i)
                # فقط اگر بعد از عدد، واحد پول (مقیاس یا «تومان») آمده باشد، مبلغ است
                if j < n and words[j] in word_to_number and word_to_number[words[j]] >= 1000:
                    unit = word_to_number[words[j]]
                    result += (val or 1) * unit
                    i = j + 1
                elif j < n and words[j] in ('تومان', 'تومن'):
                    result += val
                    i = j + 1
                else:
                    i = j
            else:
                i += 1

        if result > 0:
            return result

        # بازگشت آخرین عدد ساده (اگر واحدی نبود ولی عددی در متن هست)
        numbers = re.findall(r'\d+', text)
        if numbers:
            amount = int(numbers[-1])
            if any(u in text for u in ('زارتومن', 'زارتومان', 'هزارتومان', 'هزار', 'زارتوم')):
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

        # پشتیبان: اگر واحدی از «هزار تومان» در متن بود ولی مبلغ کوچک استخراج شد، در ۱۰۰۰ ضرب کن
        if data["amount"] < 100 and data["amount"] > 0:
            if any(u in text for u in ('زارتومن', 'زارتومان', 'زار تومان', 'زارتوما', 'زارتوم', 'هزارتومان', 'هزار')):
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