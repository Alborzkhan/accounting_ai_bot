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
