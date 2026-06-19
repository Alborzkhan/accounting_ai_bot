import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def _fix_console_encoding() -> None:
    """در ویندوز، کدپیج پیش‌فرض کنسول معمولاً UTF-8 نیست و چاپ ایموجی/فارسی باعث
    UnicodeEncodeError و کرش برنامه می‌شود. خروجی را به UTF-8 سوییچ می‌کنیم."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def setup_logging(level: int = logging.INFO) -> None:
    """پیکربندی یکپارچه لاگ‌گیری برای کل پروژه (وب‌اپ، ربات‌ها، اسکریپت‌های ادمین)."""
    _fix_console_encoding()
    root = logging.getLogger()
    if root.handlers:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
