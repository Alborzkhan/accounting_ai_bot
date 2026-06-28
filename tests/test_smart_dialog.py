class TestCustomerBalance:
    def test_process_customer_balance_is_per_customer_not_whole_account(self, dialog_engine, engine):
        """رگرسیون: قبلاً مانده‌ی هر مشتری از کل حساب «بدهکاران تجاری» خوانده می‌شد،
        یعنی دو مشتری مختلف همیشه یک عدد یکسان می‌گرفتند. الان باید مانده‌ی واقعی خودش باشد."""
        from datetime import datetime
        from database.models import Customer

        session = engine.Session()
        try:
            c1 = Customer(user_id=1, name="علی کریمی")
            c2 = Customer(user_id=1, name="مصطفی جعفری")
            session.add_all([c1, c2])
            session.commit()
            c1_id, c2_id = c1.id, c2.id
        finally:
            session.close()

        engine.create_voucher(
            date=datetime.now(), description="فروش به علی کریمی",
            lines=[('1101', 1_000_000, 'debit'), ('4001', 1_000_000, 'credit')],
            user_id=1, customer_id=c1_id,
        )
        engine.create_voucher(
            date=datetime.now(), description="فروش به مصطفی جعفری",
            lines=[('1101', 5_000_000, 'debit'), ('4001', 5_000_000, 'credit')],
            user_id=1, customer_id=c2_id,
        )

        result1 = dialog_engine.process_customer_balance({'customer_name': 'علی کریمی'}, user_id=1)
        result2 = dialog_engine.process_customer_balance({'customer_name': 'مصطفی جعفری'}, user_id=1)
        assert result1["success"] and result2["success"]
        assert "1,000,000" in result1["message"]
        assert "5,000,000" in result2["message"]


class TestSmartDialogIntent:
    def test_detect_payment_received(self, dialog_engine):
        result = dialog_engine.detect_intent("مشتری علی کریمی 500 هزار پول زد")
        assert result["intent"] == "payment_received"

    def test_detect_payment_received_variant(self, dialog_engine):
        result = dialog_engine.detect_intent("مشتری رضایی واریز کرد")
        assert result["intent"] == "payment_received"

    def test_detect_payment_received_tasvieh(self, dialog_engine):
        result = dialog_engine.detect_intent("تسویه حساب مشتری احمدی")
        assert result["intent"] == "payment_received"

    def test_detect_payment_sent(self, dialog_engine):
        result = dialog_engine.detect_intent("پرداخت به تامین کننده 1 میلیون تومان")
        assert result["intent"] == "payment_sent"

    def test_detect_customer_balance(self, dialog_engine):
        result = dialog_engine.detect_intent("مشتری احمدی چقدر بدهکار است")
        assert result["intent"] == "customer_balance"

    def test_detect_no_intent(self, dialog_engine):
        result = dialog_engine.detect_intent("سلام خوبی")
        assert result["intent"] is None

    def test_extract_amount_numeric(self, dialog_engine):
        result = dialog_engine.detect_intent("مشتری علی 500000 تومان پول زد")
        assert result["entities"].get("amount") == 500000

    def test_extract_amount_million(self, dialog_engine):
        result = dialog_engine.detect_intent("مشتری علی 2 میلیون تومان واریز کرد")
        assert result["entities"].get("amount") == 2_000_000

    def test_extract_customer_name(self, dialog_engine):
        result = dialog_engine.detect_intent("مشتری علی کریمی 500 هزار پول زد")
        name = result["entities"].get("customer_name", "")
        assert "علی" in name and "کریمی" in name

    def test_missing_info_customer_name(self, dialog_engine):
        result = dialog_engine.detect_intent("پول زد")
        assert "customer_name" in result.get("missing_info", [])
