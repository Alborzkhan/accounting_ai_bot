import sys, requests, json
sys.stdout.reconfigure(encoding="utf-8")

PROMPT = """تو نارین هستی، حسابدار و حسابرس هوشمند ایرانی. متن زیر ممکن است شامل چند تراکنش (خرید/فروش/دریافت/پرداخت/هزینه) باشد.
همه تراکنش‌های موجود را جدا کن و برای هرکدام یک آیتم در آرایه برگردان.

کدینگ معتبر (فقط همین‌ها):
1001 صندوق، 1002 بانک، 1101 بدهکاران تجاری، 1201 موجودی کالا، 2001 بستانکاران تجاری، 3001 سرمایه
4101 فروش کالا عمده، 4102 فروش کالا خرده، 4301 فروش خدمات، 4601 سایر درآمدها
5111 خرید کالا عمده، 5112 خرید کالا خرده، 5602 اجاره، 5603 حمل، 5609 آب و برق، 5610 تلفن، 5611 لوازم تحریر

خروجی فقط و فقط JSON با این ساختار (بدون توضیح اضافه):
{"success": true, "transactions": [
  {"description": "شرح", "type": "خرید/فروش/دریافت/پرداخت/هزینه", "amount": 0, "debit_account": "کد", "credit_account": "کد"}
]}
اگر فقط یک تراکنش بود، همان را داخل آرایه بگذار. اگر هیچ تراکنش مشخصی نبود:
{"success": false, "message": "توضیح کوتاه"}"""

text = "سلام امرو سو برافتا بازار و یه سری لبازم تهریر خریدم برای مبازه تیستو سیه زارتوماً پولشت بعد شی مشتری عمد 5 دفترچه و دتخود کاربورت کفت آخرمه پولش رمیده بعد زوه هم ینفر عمد قست قبلش رو پر داختکت، حونسته زارتوماً نبدي"

resp = requests.post("http://localhost:11434/api/chat", json={
    "model": "qwen2.5:3b",
    "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
    "stream": False,
}, timeout=120)

data = resp.json()
content = data.get("message", {}).get("content", "")
print("RAW:", content[:1500])
print("---")
try:
    parsed = json.loads(content)
    print("PARSED:", json.dumps(parsed, ensure_ascii=False, indent=2))
except Exception as e:
    print("JSON parse failed:", e)
