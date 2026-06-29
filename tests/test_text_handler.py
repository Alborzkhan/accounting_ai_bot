import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.text_command_handler import TextCommandHandler
from core.accounting_engine import AccountingEngine


class TestTextCommandHandler:
    @pytest.fixture
    def handler(self, db_path):
        engine = AccountingEngine(db_path)
        return TextCommandHandler(engine)

    def test_parse_purchase(self, handler):
        result = handler.parse_and_create_voucher("خرید 100 عدد خودکار 5000 تومان")
        assert result["success"] is True
        assert result["data"]["type"] == "خرید"

    def test_parse_purchase_credits_creditors_not_capital(self, handler):
        """رگرسیون: قبلاً سمت بستانکار «خرید» به اشتباه حساب ۳۰۰۱ (سرمایه) بود، نه ۲۰۰۱
        (بستانکاران تجاری) - یعنی هر خرید نسیه، عملاً به‌عنوان آوردن سرمایه توسط صاحب کسب‌وکار ثبت می‌شد."""
        result = handler.parse_and_create_voucher("خرید 100 عدد خودکار 5000 تومان")
        assert result["data"]["credit_account"] == "2001"

    def test_parse_payment(self, handler):
        result = handler.parse_and_create_voucher("پرداخت 100000 تومان به تامین کننده")
        assert result["success"] is True
        assert result["data"]["type"] == "پرداخت"

    def test_parse_payment_debits_creditors_not_capital(self, handler):
        result = handler.parse_and_create_voucher("پرداخت 100000 تومان به تامین کننده")
        assert result["data"]["debit_account"] == "2001"

    def test_parse_receipt(self, handler):
        result = handler.parse_and_create_voucher("دریافت 500000 تومان از مشتری")
        assert result["success"] is True
        assert result["data"]["type"] == "دریافت"

    def test_parse_unknown_type(self, handler):
        result = handler.parse_and_create_voucher("سلام چطوری")
        assert result["success"] is False
        assert "تشخیص داده نشد" in result["message"]

    def test_parse_no_amount(self, handler):
        result = handler.parse_and_create_voucher("خرید کالا")
        assert result["success"] is False
        assert "مبلغ" in result["message"]

    def test_parse_amount_with_thousand(self, handler):
        result = handler.parse_and_create_voucher("خرید مفتول 5 هزار تومان")
        assert result["success"] is True
        assert result["data"]["amount"] == 5000

    def test_parse_amount_with_million(self, handler):
        result = handler.parse_and_create_voucher("خرید مفتول 2 میلیون تومان")
        assert result["success"] is True
        assert result["data"]["amount"] == 2_000_000
