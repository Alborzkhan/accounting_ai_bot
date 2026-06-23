import sys, os, json, re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY, OPENAI_MODEL

LLM_SYSTEM_PROMPT = """تو نارین هستی، حسابدار و حسابرس هوشمند و دستیار حسابداری.
وظیفه تو اینه که متن‌های کاربر رو به یک سند حسابداری دوطرفه تبدیل کنی.

محدوده کاری تو: فقط و فقط حسابداری، حسابرسی و موضوعات مالی پیرامون کسب‌وکار کاربر (ثبت سند، مالیات،
فاکتور، موجودی، گزارش‌های مالی، تحلیل صورت‌های مالی). هیچ موضوع دیگری (غیر از سلام/احوالپرسی ساده)
را پاسخ نده، حتی اگر کاربر اصرار کند.

شرح عملیات رایج و نحوه تشخیص (کدهای زیر واقعی و معتبر هستند، فقط همین‌ها را استفاده کن):
1. خرید کالا/خدمات:
   - کلمات: خریدم، گرفتم، خرید، سفارش دادم، تهیه کردم
   - بدهکار: موجودی کالا (1201) — اگر مشخصاً مواد اولیه تولیدی بود از 1301 استفاده کن
   - بستانکار: بستانکاران تجاری/صندوق (2001/1001)

2. فروش کالا/خدمات:
   - کلمات: فروختم، فروش، تحویل دادم
   - بدهکار: بدهکاران تجاری/صندوق (1101/1001)
   - بستانکار: فروش کالا (4001) — اگر مشخصاً خدماتی بود از 4301، اگر شارژ ساختمان بود از 4501 استفاده کن

3. دریافت وجه از مشتری:
   - کلمات: پول زد، واریز کرد، پرداخت کرد، تسویه کرد، ریخت، داد
   - بدهکار: صندوق/بانک (1001/1002)
   - بستانکار: بدهکاران تجاری (1101)

4. پرداخت به فروشنده/تامین‌کننده:
   - کلمات: پرداخت کردم، واریز کردم، دادم، تسویه کردم
   - بدهکار: بستانکاران تجاری (2001)
   - بستانکار: صندوق/بانک (1001/1002)

5. پرداخت هزینه (اجاره، حقوق، حمل، تعمیرات، کارمزد، بیمه، تبلیغات، مالیات، آب و برق، تلفن و اینترنت):
   - بدهکار: حساب هزینه مربوطه از کدینگ زیر (5601 تا 5610)
   - بستانکار: صندوق/بانک (1001/1002)

6. ثبت سرمایه/برداشت:
   - کلمات: سرمایه گذاری، برداشت، آورده
   - بدهکار/بستانکار: صندوق و سرمایه (3001)

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

کدینگ حساب‌ها (فقط این کدها در دیتابیس وجود دارند؛ از کد دیگری استفاده نکن):
1001 = صندوق
1002 = بانک
1101 = بدهکاران تجاری
1201 = موجودی کالا (بازرگانی)
1301 = مواد اولیه (تولیدی)
1303 = ماشین‌آلات (تولیدی)
1601 = بدهکاران شارژ واحدها (مدیریت آپارتمان)
2001 = بستانکاران تجاری
3001 = سرمایه
3900 = سود (زیان) انباشته
4001 = فروش کالا (بازرگانی)
4201 = فروش محصولات (تولیدی)
4301 = درآمد خدمات (خدماتی)
4401 = درآمد پیمانکاری (پیمانکاری)
4501 = درآمد شارژ دریافتی (مدیریت آپارتمان)
4601 = سایر درآمدها
5101 = بهای تمام شده کالای فروش رفته
5201 = بهای تمام شده تولید
5501..5507 = هزینه‌های جاری ساختمان (برق/آب/گاز/نظافت/آسانسور/موتورخانه/سایر) - فقط مدیریت آپارتمان
5601 = هزینه حقوق و دستمزد
5602 = هزینه اجاره
5603 = هزینه حمل و نقل
5604 = هزینه تعمیر و نگهداری
5605 = هزینه کارمزد بانکی
5606 = هزینه بیمه
5607 = هزینه تبلیغات
5608 = هزینه مالیاتی
5609 = هزینه آب و برق و سوخت
5610 = هزینه تلفن و اینترنت

اگر متن کاربر یک سوال خارج از محدوده کاری تو بود (هر چیزی غیر از حسابداری/حسابرسی/مالی، مثل آب و هوا، ورزش، خبر، آشپزی، سیاست، برنامه‌نویسی و ...):
{
  "success": false,
  "type": "general",
  "message": "من نارین هستم، حسابدار و حسابرس هوشمند شما. فقط می‌تونم توی امور حسابداری، حسابرسی و مالی کمکت کنم. مثال: ثبت سند خرید، فروش، دریافت و پرداخت، مانده حساب، گزارش"
}

اگر سلام و احوالپرسی معمولی بود، یه جواب دوستانه و کوتاه بده، بدون خروج از محدوده کاری حسابداری."""

BUSINESS_TYPE_PROMPT = """تو دستیار طبقه‌بندی کسب‌وکار برای یک نرم‌افزار حسابداری ایرانی هستی.
کاربر کسب‌وکار خودش را با متن آزاد توصیف می‌کند. باید دقیقاً یکی از این دسته‌ها را به‌عنوان مناسب‌ترین گزینه انتخاب کنی:
- بازرگانی: خرید و فروش کالا بدون تغییر در آن (فروشگاه، عمده‌فروشی، واردات/صادرات، نمایندگی فروش)
- تولیدی: تولید/ساخت محصول از مواد اولیه (کارگاه، کارخانه، تولید مواد غذایی/پوشاک/مبلمان/...)
- خدماتی: ارائه خدمات بدون فروش کالای فیزیکی (مشاوره، آموزش، تعمیرات، رستوران/کافه، آرایشگاه، حمل‌ونقل)
- پیمانکاری: اجرای پروژه‌های ساختمانی/عمرانی/تأسیساتی برای کارفرما
- مدیریت آپارتمان‌ها: مدیر مجتمع/ساختمان که شارژ از واحدها دریافت می‌کند و هزینه‌های جاری مشاعات (برق، آب، نظافت، آسانسور) را پرداخت می‌کند

همیشه خروجی را فقط به این فرمت JSON بده، بدون هیچ توضیح اضافه:
{
  "business_type": "یکی از: بازرگانی/تولیدی/خدماتی/پیمانکاری/مدیریت آپارتمان‌ها",
  "confidence": "high/medium/low",
  "reasoning": "یک جمله کوتاه فارسی که توضیح می‌دهد چرا این گزینه را پیشنهاد دادی"
}"""

VALID_BUSINESS_TYPES = {"بازرگانی", "تولیدی", "خدماتی", "پیمانکاری", "مدیریت آپارتمان‌ها"}

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

ACCOUNT_QUERY_PROMPT = """تو نارین هستی، حسابدار و حسابرس هوشمند. کاربر خلاصه‌ی مانده و گردش یک حساب حسابداری را به تو می‌دهد.
یک تحلیل کوتاه (حداکثر دو جمله)، مفید و فارسی درباره وضعیت این حساب بده (روند، نکته قابل توجه یا توصیه).
فقط در محدوده حسابداری/مالی پاسخ بده، بدون توضیح اضافه.
همیشه خروجی را فقط به این فرمت JSON بده:
{"success": true, "explanation": "..."}
"""

OLLAMA_BASE_URL = "http://localhost:11434"

SUPPORTED_PROVIDERS = {
    "openai": {
        "label": "OpenAI (GPT)", "kind": "openai_compatible",
        "base_url": "https://api.openai.com/v1/chat/completions", "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "label": "Anthropic (Claude)", "kind": "anthropic",
        "default_model": "claude-sonnet-4-6",
    },
    "groq": {
        "label": "Groq (رایگان و سریع)", "kind": "openai_compatible",
        "base_url": "https://api.groq.com/openai/v1/chat/completions", "default_model": "llama-3.3-70b-versatile",
    },
    "deepseek": {
        "label": "DeepSeek", "kind": "openai_compatible",
        "base_url": "https://api.deepseek.com/chat/completions", "default_model": "deepseek-chat",
    },
    "gapgpt": {
        "label": "GapGPT (دسترسی ایرانی به ChatGPT/Claude/Gemini، پرداخت ریالی)", "kind": "openai_compatible",
        "base_url": "https://api.gapgpt.app/v1/chat/completions", "default_model": "chatgpt",
    },
    "openrouter": {
        "label": "OpenRouter (چند مدل، گزینه‌های رایگان)", "kind": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1/chat/completions", "default_model": "meta-llama/llama-3.1-8b-instruct:free",
    },
    "gemini": {
        "label": "Google Gemini", "kind": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "default_model": "gemini-2.0-flash",
    },
}


class LLMProcessor:
    def __init__(self) -> None:
        self.ollama_url = f"{OLLAMA_BASE_URL}/api/chat"
        self.use_ollama = self._check_ollama()
        self._load_config()

    def _load_config(self) -> None:
        """تنظیمات پنل ادمین (دیتابیس) را تازه می‌خواند تا تغییرات بدون ری‌استارت سرور اعمال شوند؛
        متغیرهای .env فقط fallback برای توسعه/سازگاری قدیمی‌اند."""
        settings = {}
        try:
            from core.platform_settings import PlatformSettingsManager
            settings = PlatformSettingsManager().get_all()
        except Exception:
            settings = {}

        self.api_key = settings.get("ai_api_key") or OPENAI_API_KEY
        self.provider = settings.get("ai_provider") or ("openai" if OPENAI_API_KEY else "")
        self.model = settings.get("ai_model") or (OPENAI_MODEL if self.provider == "openai" else "") \
            or SUPPORTED_PROVIDERS.get(self.provider, {}).get("default_model", "")

    def _check_ollama(self) -> bool:
        try:
            import requests
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _call_cloud(self, text: str, system_prompt: str) -> dict:
        provider_info = SUPPORTED_PROVIDERS.get(self.provider, SUPPORTED_PROVIDERS["openai"])
        if provider_info.get("kind") == "anthropic":
            return self._call_anthropic(text, system_prompt)
        base_url = provider_info.get("base_url", SUPPORTED_PROVIDERS["openai"]["base_url"])
        return self._call_openai(text, system_prompt, base_url=base_url)

    def process(self, text: str) -> dict:
        self._load_config()
        if self.api_key:
            return self._call_cloud(text, LLM_SYSTEM_PROMPT)
        if self.use_ollama:
            return self._call_ollama(text)
        return {"success": False, "error": "no_api_key"}

    def test_connection(self) -> dict:
        """برای دکمه «تست اتصال» در پنل ادمین: یک پیام نمونه می‌فرستد و وضعیت اتصال را برمی‌گرداند."""
        if self.api_key:
            label = SUPPORTED_PROVIDERS.get(self.provider, {}).get("label", "ارائه‌دهنده انتخابی")
        elif self.use_ollama:
            label = "Ollama (محلی)"
        else:
            return {"success": False, "message": "هیچ سرویس هوش مصنوعی تنظیم نشده است."}

        result = self.process("سلام، حالت چطوره؟")
        if result.get("error"):
            return {"success": False, "message": f"❌ اتصال به {label} برقرار نشد: {result.get('message', result.get('error'))}"}
        return {"success": True, "message": f"✅ اتصال به {label} با موفقیت برقرار شد."}

    def classify_business_type(self, description: str) -> dict:
        """تشخیص نوع کسب‌وکار از روی توضیح آزاد کاربر با استفاده از LLM."""
        self._load_config()
        if self.api_key:
            result = self._call_cloud(description, BUSINESS_TYPE_PROMPT)
        elif self.use_ollama:
            result = self._call_ollama(description, system_prompt=BUSINESS_TYPE_PROMPT)
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
        self._load_config()
        if self.api_key:
            result = self._call_cloud(text, INVOICE_EXTRACT_PROMPT)
        elif self.use_ollama:
            result = self._call_ollama(text, system_prompt=INVOICE_EXTRACT_PROMPT)
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

    def answer_account_query(self, summary: str) -> dict:
        """تحلیل کوتاه یک حساب برای دکمه «پرسش از نارین» در صفحه جزئیات حساب."""
        self._load_config()
        if self.api_key:
            result = self._call_cloud(summary, ACCOUNT_QUERY_PROMPT)
        elif self.use_ollama:
            result = self._call_ollama(summary, system_prompt=ACCOUNT_QUERY_PROMPT)
        else:
            return {"success": False, "message": "سرویس هوش مصنوعی تنظیم نشده است."}

        if not result.get("success"):
            return {"success": False, "message": result.get("message", "تحلیل ممکن نشد.")}
        return {"success": True, "explanation": str(result.get("explanation", "")).strip()}

    def _call_openai(self, text: str, system_prompt: str = LLM_SYSTEM_PROMPT, base_url: str = None) -> dict:
        import requests
        try:
            resp = requests.post(
                base_url or SUPPORTED_PROVIDERS["openai"]["base_url"],
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

    def _call_anthropic(self, text: str, system_prompt: str = LLM_SYSTEM_PROMPT) -> dict:
        import requests
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model or SUPPORTED_PROVIDERS["anthropic"]["default_model"],
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": text}],
                    "max_tokens": 500,
                    "temperature": 0.1
                },
                timeout=20
            )
            data = resp.json()
            if "content" not in data:
                return {"success": False, "error": "api_error", "message": f"خطای API: {data.get('error', {}).get('message', 'نامشخص')}"}
            content = "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")
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
