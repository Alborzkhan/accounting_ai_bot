FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# نسخه CPU-only تورچ را جدا و اول نصب می‌کنیم؛ وگرنه pip به‌خاطر وابستگی openai-whisper
# نسخه پیش‌فرض را می‌گیرد که چند گیگابایت ویل‌های CUDA بی‌مصرف (این کانتینر GPU ندارد) دارد.
RUN pip install --no-cache-dir --timeout 120 --retries 10 torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "web_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
