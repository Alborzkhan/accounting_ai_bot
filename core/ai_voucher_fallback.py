# core/ai_voucher_fallback.py

from datetime import datetime
from typing import Dict, List, Optional

from core.accounting_engine import AccountingEngine


# کلمه‌های کلیدی شروع‌کننده‌ی یک تراکنش (خرید/فروش/پرداخت/دریافت/...)
_TRANSACTION_TRIGGERS = (
    "خرید", "فروش", "پرداخت", "دریافت", "واریز", "تسویه",
    "قسط", "نسیه", "اجاره", "حقوق", "بیمه", "گرفت", "داد", "تحویل",
)

# واحدهای مبلغ؛ هر مبلغ (با عدد قبلش) نشانه‌ی یک تراکنشِ دارای مبلغ است
_AMOUNT_UNITS = (
    "زارتومان", "زارتومن", "زارتوما", "زارتوم", "زار تومان",
    "هزارتومان", "هزار", "میلیون", "تومان", "تومن",
)

_PERSIAN_NUM_WORDS = (
    "یک", "دو", "سه", "چهار", "پنج", "پنچه", "شش", "هفت", "هشت", "نه", "ده",
    "سی", "بیست", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود", "صد",
    "دویست", "سیصد", "چهارصد", "پانصد", "پونصد", "ششصد", "هفتصد", "هشتصد", "نهصد",
)


def split_transactions(text: str) -> List[str]:
    """گفتار/متنِ چندتراکنشی را به بخش‌های جدا (هر بخش یک تراکنش) تقسیم می‌کند.

    تقسیم بر اساس کلمه‌های کلیدی شروع‌کننده‌ی تراکنش (خرید/فروش/پرداخت/دریافت/...)
    انجام می‌شود. اگر فقط یک تراکنش باشد، کل متن را برمی‌گرداند.
    بخشی که هیچ مبلغ/عددی نداشته باشد (فقط فعلِ پایانی) به بخش قبلی می‌چسبد.
    """
    if not text:
        return []
    marks: List[int] = []
    for kw in _TRANSACTION_TRIGGERS:
        s = 0
        while True:
            i = text.find(kw, s)
            if i == -1:
                break
            # از مارک‌های تکراریِ نزدیک (مثل «خرید» در «خریدم») صرف‌نظر کن
            if marks and i - marks[-1] < 6:
                s = i + len(kw)
                continue
            marks.append(i)
            s = i + len(kw)

    if len(marks) <= 1:
        return [text]

    marks = sorted(marks)
    segments: List[str] = []
    for idx, pos in enumerate(marks):
        end = marks[idx + 1] if idx + 1 < len(marks) else len(text)
        seg = text[pos:end].strip().lstrip("،. ؛:«»-")
        if seg:
            segments.append(seg)

    # بخش بدون مبلغ (فقط فعل/وصله) → به بخش قبلی بچسبان
    def has_amount_hint(seg: str) -> bool:
        if any(c.isdigit() for c in seg):
            return True
        if any(w in seg for w in _PERSIAN_NUM_WORDS):
            return True
        if any(u in seg for u in _AMOUNT_UNITS):
            return True
        return False

    merged: List[str] = []
    for seg in segments:
        if merged and not has_amount_hint(seg):
            merged[-1] += " " + seg
        else:
            merged.append(seg)
    return merged


_SEGMENT_SUFFIXES = ("بعدش", "بعد از آن", "بعد از", "بعد هم", "بعد", "سپس", "و بعد", "و سپس")


def _clean_segment(seg: str) -> str:
    """حذف واژه‌های پیوندیِ انتهای هر بخش (بعدش/بعد/سپس/...) که با یک بخشِ دیگر می‌آیند."""
    seg = seg.strip()
    changed = True
    while changed:
        changed = False
        for suffix in _SEGMENT_SUFFIXES:
            if seg.endswith(suffix):
                seg = seg[: -len(suffix)].strip(" ،؛.")
                changed = True
    return seg


def _has_mixed_units(seg: str) -> bool:
    """اگر در یک بخش هم «میلیون» و هم «هزار»/«تومان» باشد، احتمالاً چند مبلغ در آن هست و
    استخراجِ قانون‌محور می‌تواند مبلغ غلط (مثلاً ضرب در میلیون) بدهد؛ این بخش‌ها باید به AI بروند."""
    return "میلیون" in seg and any(u in seg for u in ("هزار", "زارتومان", "تومان", "تومن"))


def create_vouchers_multi(engine: AccountingEngine, text: str, user_id: Optional[int]) -> Dict:
    """متن چندتراکنشی را جدا کرده و برای هر بخش یک سند ثبت می‌کند.

    برای هر بخش ابتدا مسیر قانون‌محور (سریع و مطمئن برای متن ساده) امتحان می‌شود و اگر
    جواب نداد، همان بخش با هوش مصنوعی ثبت می‌شود. اگر فقط یک تراکنش باشد، مسیر قبلی
    (try_ai_voucher) دنبال می‌شود.
    """
    segments = split_transactions(text)
    if len(segments) <= 1:
        return try_ai_voucher(engine, text, user_id)

    from core.text_command_handler import TextCommandHandler
    handler = TextCommandHandler(engine)

    created = []
    failed = []
    for raw_seg in segments:
        seg = _clean_segment(raw_seg)
        # اول قوانین (سریع و بی‌هزینه) — فقط اگر مبلغش مبهم/ترکیبی نباشد
        if not _has_mixed_units(seg):
            rule = handler.parse_and_create_voucher(seg, user_id=user_id)
            if rule.get("success"):
                created.append({"message": rule["message"], "entry_id": rule.get("entry_id")})
                continue
        # اگر قوانین جواب نداد (یا مبلغ ترکیبی بود)، هوش مصنوعی
        r = try_ai_voucher(engine, seg, user_id)
        if r.get("success"):
            created.append({"message": r["message"], "entry_id": r.get("entry_id")})
        else:
            failed.append(seg[:80])

    if created:
        msg = f"✅ {len(created)} سند ثبت شد."
        if failed:
            msg += f" ⚠️ {len(failed)} بخش تشخیص داده نشد: " + " | ".join(failed[:2])
        return {"success": True, "message": msg, "count": len(created), "failed_count": len(failed)}
    return {"success": False, "message": "تراکنش‌های پیام تشخیص داده نشد. لطفاً هر تراکنش را جدا بفرستید."}


def try_ai_voucher(engine: AccountingEngine, text: str, user_id: Optional[int]) -> Dict:
    """وقتی تشخیص قانون‌محور (کلمه‌کلیدی) روی متن/رونویسی‌شده‌ی ویس جواب نداد، قبل از رد کردن پیام کاربر
    یک‌بار با هوش مصنوعی (ابری در صورت تنظیم‌بودن کلید، وگرنه Ollama محلی) امتحان می‌کند."""
    from ai_handlers.llm_processor import LLMProcessor

    ai_result = LLMProcessor().process(text)
    if not ai_result.get("success"):
        return {"success": False}

    try:
        amount = float(ai_result.get("amount") or 0)
        debit_account = str(ai_result.get("debit_account") or "")
        credit_account = str(ai_result.get("credit_account") or "")
        if amount <= 0 or not debit_account or not credit_account:
            return {"success": False}

        entry_id = engine.create_voucher(
            date=datetime.now(),
            description=ai_result.get("description") or text[:200],
            lines=[(debit_account, amount, "debit"), (credit_account, amount, "credit")],
            user_id=user_id,
        )
        return {
            "success": True,
            "entry_id": entry_id,
            "amount": amount,
            "type": ai_result.get("type", ""),
            "description": ai_result.get("description") or text[:200],
            "debit_account": debit_account,
            "credit_account": credit_account,
            "message": f"✅ سند شماره {entry_id} با موفقیت ثبت شد. (تشخیص با هوش مصنوعی)",
        }
    except ValueError:
        return {"success": False}
