# core/ai_voucher_fallback.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import Dict, Optional

from core.accounting_engine import AccountingEngine


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
