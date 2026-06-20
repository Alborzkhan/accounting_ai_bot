# نارین | دستیار حسابداری هوشمند

دستیار حسابداری فارسی که توضیح متنی یا صوتی تراکنش‌ها را به سند حسابداری دوطرفه (بدهکار/بستانکار) تبدیل می‌کند. از طریق تلگرام، بله و یک وب‌اپ قابل استفاده است.

## پیش‌نیازها

- Python 3.11+
- (اختیاری) [Ollama](https://ollama.com) با مدل `qwen2.5:3b` به‌عنوان fallback محلی در صورت نبود کلید OpenAI
- حساب فراپیامک (یا هر سرویس پیامک دیگر) برای ارسال کد تایید ورود در محیط Production

## نصب

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

سپس مقادیر `.env` را تکمیل کنید (توکن تلگرام/بله، کلید OpenAI، یوزرنیم/پسورد فراپیامک و ...). فایل `.env` هرگز نباید به گیت اضافه شود (در `.gitignore` پوشش داده شده).

## اجرا

وب‌اپ (FastAPI):
```powershell
python -m uvicorn web_app.main:app --host 0.0.0.0 --port 8000
```

ربات تلگرام:
```powershell
python bot_handlers/telegram_bot.py
```

ربات بله:
```powershell
python bot_handlers/bale_bot.py
```

هرکدام پروسه جدا هستند و باید جداگانه اجرا/مانیتور شوند (فعلاً بدون orchestration؛ برای استقرار واقعی به Docker/Supervisor نیاز است).

## تست

```powershell
pytest
```

## ساختار پروژه

- `core/` — منطق اصلی حسابداری، احراز هویت، لایسنس، پرداخت
- `ai_handlers/` — پردازش زبان طبیعی (OpenAI/Ollama) و تبدیل صدا به متن (Whisper)
- `bot_handlers/` — ربات‌های تلگرام و بله
- `web_app/` — اپلیکیشن وب FastAPI
- `database/` — مدل‌های SQLAlchemy
- `reports/` — تولید گزارش و PDF
- `tests/` — تست‌های pytest

## وضعیت امنیتی

ورود کاربران در وب‌اپ از طریق کد تایید یک‌بارمصرف (OTP) ارسالی با پیامک انجام می‌شود (`core/auth.py`, `core/sms_service.py`). اگر `FARAPAYAMAK_USERNAME`/`FARAPAYAMAK_PASSWORD` در `.env` خالی باشند، کد تایید فقط در `logs/app.log` ثبت می‌شود — این حالت فقط برای توسعه/تست است و **قبل از انتشار عمومی باید اطلاعات واقعی پیامک تنظیم شود**.

موارد باز که قبل از مقیاس بزرگ‌تر باید انجام شود: مهاجرت دیتابیس با Alembic، Dockerize کردن، CI/CD، و جابه‌جایی rate limiter از حافظه به Redis در صورت اجرای چند-پروسه‌ای.
