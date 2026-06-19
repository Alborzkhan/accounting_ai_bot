import sys, os, json, re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY, OPENAI_MODEL

LLM_SYSTEM_PROMPT = """تو نارین هستی، حسابدار هوشمند و دستیار حسابداری.
وظیفه تو اینه که متن‌های کاربر رو به یک سند حسابداری دوطرفه تبدیل کنی.

شرح عملیات رایج و نحوه تشخیص:
1. خرید کالا/خدمات:
   - کلمات: خریدم، گرفتم، خرید، سفارش دادم، تهیه کردم
   - بدهکار: موجودی کالا (1201)
   - بستانکار: بستانکاران تجاری/صندوق (3001/1001)

2. فروش کالا:
   - کلمات: فروختم، فروش، تحویل دادم
   - بدهکار: بدهکاران تجاری/صندوق (1101/1001)
   - بستانکار: فروش کالا (6001)

3. دریافت وجه از مشتری:
   - کلمات: پول زد، واریز کرد، پرداخت کرد، تسویه کرد، ریخت، داد
   - بدهکار: صندوق/بانک (1001/1002)
   - بستانکار: بدهکاران تجاری (1101)

4. پرداخت به فروشنده/تامین‌کننده:
   - کلمات: پرداخت کردم، واریز کردم، دادم، تسویه کردم
   - بدهکار: بستانکاران تجاری (3001)
   - بستانکار: صندوق/بانک (1001/1002)

5. پرداخت هزینه (اجاره، حقوق، حمل، برق، آب، تلفن، اینترنت و ...):
   - بدهکار: حساب هزینه مربوطه (7003=اجاره، 7002=حقوق، 7004=حمل، ...)
   - بستانکار: صندوق/بانک (1001/1002)

6. ثبت سرمایه/برداشت:
   - کلمات: سرمایه گذاری، برداشت، آورده
   - بدهکار/بستانکار: صندوق و سرمایه (5001)

اعداد می‌تونن به صورت رقم (50000) یا حروف (پنجاه هزار) بیان.
همیشه خروجی JSON برگردون با این ساختار:
{
  "success": true/false,
  "type": "خرید/فروش/دریافت/پرداخت/هزینه/سرمایه",
  "description": "شرح سند به صورت حرفه‌ای",
  "amount": عدد_مبلغ_به_تومان,
  "debit_account": "کد_حساب_بدهکار",
  "credit_account": "کد_حساب_بستانکار",
  "message": "پیام تایید برای کاربر به فارسی"
}

کدینگ حساب‌ها:
1001 = صندوق
1002 = بانک
1101 = بدهکاران تجاری
1102 = اسناد دریافتنی
1201 = موجودی کالا
1202 = مواد اولیه
2003 = ماشین‌آلات
2004 = وسایط نقلیه
2005 = تجهیزات کامپیوتری
3001 = بستانکاران تجاری
3002 = اسناد پرداختنی
3003 = پیش‌دریافت
4001 = تسهیلات بانکی بلندمدت
5001 = سرمایه
5002 = سود انباشته
6001 = فروش کالا
6002 = درآمد خدمات
7001 = بهای تمام شده کالای فروش رفته
7002 = هزینه حقوق و دستمزد
7003 = هزینه اجاره
7004 = هزینه حمل و نقل
7005 = هزینه تعمیر و نگهداری
7006 = هزینه کارمزد
7007 = هزینه بیمه
7008 = هزینه تبلیغات
7010 = هزینه مالیاتی
7011 = هزینه آب و برق و سوخت
7012 = هزینه تلفن و اینترنت

اگر متن کاربر یک سوال غیرمرتبط با حسابداری پرسید (مثل آب و هوا، ورزش، خبر، آشپزی، ...):
{
  "success": false,
  "type": "general",
  "message": "من نارین هستم، حسابدار هوشمند شما. فقط می‌تونم توی امور حسابداری و مالی کمکت کنم. مثال: ثبت سند خرید، فروش، دریافت و پرداخت، مانده حساب، گزارش"
}

اگر سلام و احوالپرسی معمولی بود، یه جواب دوستانه و کوتاه بده."""

BUSINESS_TYPE_PROMPT = """تو دستیار طبقه‌بندی کسب‌وکار برای یک نرم‌افزار حسابداری ایرانی هستی.
کاربر کسب‌وکار خودش را با متن آزاد توصیف می‌کند. باید دقیقاً یکی از این دسته‌ها را به‌عنوان مناسب‌ترین گزینه انتخاب کنی:
- بازرگانی: خرید و فروش کالا بدون تغییر در آن (فروشگاه، عمده‌فروشی، واردات/صادرات، نمایندگی فروش)
- تولیدی: تولید/ساخت محصول از مواد اولیه (کارگاه، کارخانه، تولید مواد غذایی/پوشاک/مبلمان/...)
- خدماتی: ارائه خدمات بدون فروش کالای فیزیکی (مشاوره، آموزش، تعمیرات، رستوران/کافه، آرایشگاه، حمل‌ونقل)
- پیمانکاری: اجرای پروژه‌های ساختمانی/عمرانی/تأسیساتی برای کارفرما
- سایر: اگر هیچ‌کدام به‌وضوح مناسب نبود

همیشه خروجی را فقط به این فرمت JSON بده، بدون هیچ توضیح اضافه:
{
  "business_type": "یکی از: بازرگانی/تولیدی/خدماتی/پیمانکاری/سایر",
  "confidence": "high/medium/low",
  "reasoning": "یک جمله کوتاه فارسی که توضیح می‌دهد چرا این گزینه را پیشنهاد دادی"
}"""

VALID_BUSINESS_TYPES = {"بازرگانی", "تولیدی", "خدماتی", "پیمانکاری", "سایر"}

INVOICE_EXTRACT_PROMPT = """تو دستیار ثبت فاکتور برای یک نرم‌افزار حسابداری ایرانی هستی.
از روی متن یا گفتار آزاد کاربر (فارسی)، اطلاعات یک فاکتور فروش یا خرید را استخراج کن.

موارد قابل تشخیص:
- document_type: "sale" (فروش/پیش‌فاکتور فروش) یا "purchase" (خرید) — اگر نامشخص بود "sale" در نظر بگیر
- party_name: نام مشتری (برای فروش) یا نام فروشنده/تامین‌کننده (برای خرید). اگر گفته نشده بود رشته خالی بگذار
- party_mobile: شماره موبایل طرف حساب اگر گفته شده بود (۱۱ رقمی، با 09 شروع)، وگرنه رشته خالی
- is_official: true اگر کاربر گفت "رسمی"، "فاکتور رسمی" یا "با مالیات"؛ در غیر این صورت false
- vat_rate: اگر کاربر درصد مالیات را گفت همان عدد (مثلاً 9 یا 10)، وگرنه null
- items: آرایه‌ای از اقلام؛ هر کدام شامل description (شرح کالا/خدمت)، quantity (عدد، پیش‌فرض 1)، unit (واحد، پیش‌فرض "عدد")، unit_price (قیمت واحد به تومان؛ اگر نگفته بود 0)
- description: توضیح کلی اختیاری، رشته خالی اگر نبود
- missing_info: آرایه‌ای از جمله‌های کوتاه فارسی برای هر موردی که نامعلوم/مبهم است (مثلاً قیمت یا تعداد کالایی گفته نشده). اگر چیزی مبهم نبود آرایه خالی بگذار
- message: یک جمله فارسی خلاصه آنچه فهمیدی، برای نشان دادن به کاربر جهت تایید قبل از ثبت

همیشه فقط و فقط JSON با این ساختار برگردان (بدون توضیح اضافه):
{
  "success": true,
  "document_type": "sale",
  "party_name": "",
  "party_mobile": "",
  "is_official": false,
  "vat_rate": null,
  "items": [{"description": "", "quantity": 1, "unit": "عدد", "unit_price": 0}],
  "description": "",
  "missing_info": [],
  "message": ""
}

اگر متن کاربر اصلاً درباره فاکتور/خرید/فروش نبود:
{"success": false, "message": "این متن مربوط به ثبت فاکتور نیست."}
"""

OLLAMA_BASE_URL = "http://localhost:11434"


class LLMProcessor:
    def __init__(self) -> None:
        self.api_key = OPENAI_API_KEY
        self.model = OPENAI_MODEL
        self.ollama_url = f"{OLLAMA_BASE_URL}/api/chat"
        self.use_ollama = self._check_ollama()

    def _check_ollama(self) -> bool:
        try:
            import requests
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def process(self, text: str) -> dict:
        import requests
        if self.use_ollama:
            return self._call_ollama(text)
        if self.api_key:
            return self._call_openai(text)
        return {"success": False, "error": "no_api_key"}

    def classify_business_type(self, description: str) -> dict:
        """تشخیص نوع کسب‌وکار از روی توضیح آزاد کاربر با استفاده از LLM."""
        if self.use_ollama:
            result = self._call_ollama(description, system_prompt=BUSINESS_TYPE_PROMPT)
        elif self.api_key:
            result = self._call_openai(description, system_prompt=BUSINESS_TYPE_PROMPT)
        else:
            return {"success": False, "message": "سرویس هوش مصنوعی در دسترس نیست. لطفاً نوع کسب‌وکار را خودتان انتخاب کنید."}

        business_type = result.get("business_type")
        if business_type not in VALID_BUSINESS_TYPES:
            return {"success": False, "message": result.get("message", "تشخیص نوع کسب‌وکار ممکن نشد. لطفاً خودتان انتخاب کنید.")}

        return {
            "success": True,
            "business_type": business_type,
            "confidence": result.get("confidence", "medium"),
            "reasoning": result.get("reasoning", ""),
        }

    def extract_invoice(self, text: str) -> dict:
        """استخراج اطلاعات فاکتور (فروش/خرید) از متن یا رونویسی صدای کاربر."""
        if self.use_ollama:
            result = self._call_ollama(text, system_prompt=INVOICE_EXTRACT_PROMPT)
        elif self.api_key:
            result = self._call_openai(text, system_prompt=INVOICE_EXTRACT_PROMPT)
        else:
            return {"success": False, "message": "سرویس هوش مصنوعی در دسترس نیست."}

        if not result.get("success"):
            return {"success": False, "message": result.get("message", "اطلاعات فاکتور قابل تشخیص نبود.")}

        items = result.get("items") or []
        cleaned_items = []
        for item in items:
            try:
                cleaned_items.append({
                    "description": str(item.get("description", "")).strip(),
                    "quantity": float(item.get("quantity") or 1),
                    "unit": str(item.get("unit") or "عدد").strip(),
                    "unit_price": float(item.get("unit_price") or 0),
                })
            except (TypeError, ValueError):
                continue

        return {
            "success": True,
            "document_type": result.get("document_type") if result.get("document_type") in ("sale", "purchase") else "sale",
            "party_name": str(result.get("party_name", "")).strip(),
            "party_mobile": str(result.get("party_mobile", "")).strip(),
            "is_official": bool(result.get("is_official", False)),
            "vat_rate": result.get("vat_rate"),
            "items": cleaned_items,
            "description": str(result.get("description", "")).strip(),
            "missing_info": result.get("missing_info") or [],
            "message": result.get("message", ""),
        }

    def _call_openai(self, text: str, system_prompt: str = LLM_SYSTEM_PROMPT) -> dict:
        import requests
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300
                },
                timeout=20
            )
            data = resp.json()
            if "choices" not in data:
                return {"success": False, "error": "api_error", "message": f"خطای API: {data.get('error', {}).get('message', 'نامشخص')}"}
            content = data["choices"][0]["message"]["content"]
            return self._parse_response(content)
        except Exception as e:
            return {"success": False, "error": "exception", "message": f"خطا: {str(e)}"}

    def _call_ollama(self, text: str, system_prompt: str = LLM_SYSTEM_PROMPT) -> dict:
        import requests
        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": "qwen2.5:3b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    "options": {"temperature": 0.1},
                    "stream": False
                },
                timeout=120
            )
            data = resp.json()
            content = data["message"]["content"]
            return self._parse_response(content)
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "ollama_offline", "message": "Ollama روشن نیست"}
        except Exception as e:
            return {"success": False, "error": "exception", "message": f"خطا: {str(e)}"}

    def _parse_response(self, content: str) -> dict:
        import json
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"success": False, "error": "parse_error", "message": "خطا در پردازش پاسخ"}


if __name__ == "__main__":
    llm = LLMProcessor()
    print(f"Ollama: {'✅' if llm.use_ollama else '❌'} | OpenAI: {'✅' if llm.api_key else '❌'}")
    tests = [
        "سلام چطوری",
        "خرید ۱۰۰ عدد خودکار ۵۰۰۰ تومان",
        "من ۵۰ تا کتاب خریدم ۲۰ هزار تومن",
        "علی کریمی ۵۰۰ هزار تومان پول زد",
        "به شرکت آذر ۲ میلیون پرداخت کردم",
        "اجاره مغازه رو ۱۰ میلیون دادم",
        "برق و آب ۲ میلیون پرداخت کردم",
    ]
    for t in tests:
        print(f"\n📝 {t}")
        r = llm.process(t)
        print(f"   {json.dumps(r, ensure_ascii=False, indent=2)}")
