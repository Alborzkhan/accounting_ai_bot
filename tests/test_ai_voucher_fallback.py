import pytest
from ai_handlers.llm_processor import LLMProcessor
from core.ai_voucher_fallback import try_ai_voucher


def _patch_llm(monkeypatch, result):
    monkeypatch.setattr(LLMProcessor, "process", lambda self, text: result)


class TestTryAiVoucher:
    def test_creates_voucher_on_successful_ai_result(self, engine, monkeypatch):
        _patch_llm(monkeypatch, {
            "success": True, "type": "فروش", "description": "فروش به مشتری",
            "amount": 250000, "debit_account": "1001", "credit_account": "4001",
            "message": "ok",
        })
        result = try_ai_voucher(engine, "امروز دویست و پنجاه تومن فروختم", user_id=7)
        assert result["success"] is True
        assert result["entry_id"] > 0

        journal = engine.get_journal(user_id=7)
        assert len(journal) == 1
        assert journal[0]["lines"][0]["amount"] == 250000

    def test_ai_failure_returns_unsuccessful(self, engine, monkeypatch):
        _patch_llm(monkeypatch, {"success": False, "error": "no_api_key"})
        result = try_ai_voucher(engine, "یک متن نامفهوم", user_id=7)
        assert result["success"] is False
        assert len(engine.get_journal(user_id=7)) == 0

    def test_zero_amount_is_treated_as_failure(self, engine, monkeypatch):
        _patch_llm(monkeypatch, {
            "success": True, "type": "فروش", "description": "x",
            "amount": 0, "debit_account": "1001", "credit_account": "4001",
        })
        result = try_ai_voucher(engine, "متن", user_id=7)
        assert result["success"] is False

    def test_missing_account_code_is_treated_as_failure(self, engine, monkeypatch):
        _patch_llm(monkeypatch, {
            "success": True, "type": "فروش", "description": "x",
            "amount": 10000, "debit_account": "", "credit_account": "4001",
        })
        result = try_ai_voucher(engine, "متن", user_id=7)
        assert result["success"] is False

    def test_invalid_account_code_does_not_crash(self, engine, monkeypatch):
        _patch_llm(monkeypatch, {
            "success": True, "type": "فروش", "description": "x",
            "amount": 10000, "debit_account": "9999", "credit_account": "4001",
        })
        result = try_ai_voucher(engine, "متن", user_id=7)
        assert result["success"] is False

    def test_respects_user_id_scoping(self, engine, monkeypatch):
        _patch_llm(monkeypatch, {
            "success": True, "type": "فروش", "description": "x",
            "amount": 50000, "debit_account": "1001", "credit_account": "4001",
        })
        try_ai_voucher(engine, "متن", user_id=1)
        try_ai_voucher(engine, "متن", user_id=2)
        assert len(engine.get_journal(user_id=1)) == 1
        assert len(engine.get_journal(user_id=2)) == 1
