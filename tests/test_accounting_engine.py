from datetime import datetime

class TestValidation:
    def test_validate_phone_valid(self, engine):
        assert engine.validate_phone("09121111111") is True

    def test_validate_phone_invalid(self, engine):
        assert engine.validate_phone("091111111") is False
        assert engine.validate_phone("02112345678") is False
        assert engine.validate_phone("") is False

    def test_validate_landline_valid(self, engine):
        assert engine.validate_landline("02112345678") is True
        assert engine.validate_landline("04112345678") is True

    def test_validate_landline_invalid(self, engine):
        assert engine.validate_landline("1234") is False
        assert engine.validate_landline("") is False
        assert engine.validate_landline("0912111111") is False

    def test_validate_customer_name_valid(self, engine):
        assert engine.validate_customer_name("علی کریمی") is True
        assert engine.validate_customer_name("شرکت آذر") is True

    def test_validate_customer_name_invalid(self, engine):
        assert engine.validate_customer_name("12345") is False
        assert engine.validate_customer_name("") is False
        assert engine.validate_customer_name("a") is False


class TestCustomer:
    def test_add_customer_with_mobile(self, engine):
        cust_id = engine.add_customer("علی کریمی", "09121111111")
        assert cust_id > 0

    def test_add_customer_with_landline(self, engine):
        cust_id = engine.add_customer("شرکت آذر", "", "02112345678")
        assert cust_id > 0

    def test_add_customer_invalid_name_raises(self, engine):
        import pytest
        with pytest.raises(ValueError, match="نام مشتری معتبر نیست"):
            engine.add_customer("12345", "09121111111")

    def test_add_customer_invalid_phone_raises(self, engine):
        import pytest
        with pytest.raises(ValueError, match="شماره تماس معتبر نیست"):
            engine.add_customer("علی کریمی", "1234")

    def test_get_all_customers(self, engine):
        engine.add_customer("مشتری یک", "09121111111")
        engine.add_customer("مشتری دو", "09122222222")
        customers = engine.get_all_customers()
        assert len(customers) == 2


class TestVendor:
    def test_add_vendor(self, engine):
        vid = engine.add_vendor("تامین‌کننده الف", "02112345678")
        assert vid > 0

    def test_add_vendor_with_economic_code(self, engine):
        vid = engine.add_vendor("تامین‌کننده ب", "02112345678", "987654321")
        assert vid > 0


class TestVoucher:
    def test_create_voucher(self, engine):
        eid = engine.create_voucher(
            date=datetime.now(),
            description="خرید کالا",
            lines=[('1201', 5000000, 'debit'), ('2001', 5000000, 'credit')]
        )
        assert eid > 0

    def test_create_multiple_vouchers(self, engine):
        eid1 = engine.create_voucher(
            date=datetime.now(), description="سند اول",
            lines=[('1201', 1000000, 'debit'), ('2001', 1000000, 'credit')]
        )
        eid2 = engine.create_voucher(
            date=datetime.now(), description="سند دوم",
            lines=[('1101', 2000000, 'debit'), ('4001', 2000000, 'credit')]
        )
        assert eid2 > eid1

    def test_create_voucher_unbalanced_raises(self, engine):
        import pytest
        with pytest.raises(ValueError, match="جمع بدهکار"):
            engine.create_voucher(
                date=datetime.now(), description="نابرابر",
                lines=[('1201', 5000000, 'debit'), ('2001', 3000000, 'credit')]
            )

    def test_create_voucher_links_customer_id(self, engine):
        """رگرسیون: صورت‌حساب طرف‌حساب باید بتواند اسناد مربوط به یک مشتری خاص را پیدا کند،
        که نیاز به ذخیره‌ی customer_id روی خود سند دارد (قبلاً چنین فیلدی وجود نداشت)."""
        from database.models import JournalEntry
        eid = engine.create_voucher(
            date=datetime.now(), description="فروش به مشتری",
            lines=[('1101', 1000000, 'debit'), ('4001', 1000000, 'credit')],
            customer_id=42,
        )
        session = engine.Session()
        try:
            entry = session.query(JournalEntry).filter_by(id=eid).first()
            assert entry.customer_id == 42
            assert entry.vendor_id is None
        finally:
            session.close()

    def test_create_voucher_links_vendor_id(self, engine):
        from database.models import JournalEntry
        eid = engine.create_voucher(
            date=datetime.now(), description="خرید از تامین‌کننده",
            lines=[('1201', 1000000, 'debit'), ('2001', 1000000, 'credit')],
            vendor_id=7,
        )
        session = engine.Session()
        try:
            entry = session.query(JournalEntry).filter_by(id=eid).first()
            assert entry.vendor_id == 7
            assert entry.customer_id is None
        finally:
            session.close()

    def test_create_voucher_invalid_account_raises(self, engine):
        import pytest
        with pytest.raises(ValueError, match="حساب با کد"):
            engine.create_voucher(
                date=datetime.now(), description="خرید",
                lines=[('9999', 1000000, 'debit'), ('2001', 1000000, 'credit')]
            )


class TestTrialBalance:
    def test_empty_trial_balance(self, engine):
        tb = engine.get_trial_balance()
        assert len(tb) >= 0

    def test_trial_balance_after_voucher(self, engine):
        engine.create_voucher(
            date=datetime.now(), description="خرید",
            lines=[('1201', 5000000, 'debit'), ('2001', 5000000, 'credit')]
        )
        tb = engine.get_trial_balance()
        rows_with_activity = [r for r in tb if r.total_debit != 0 or r.total_credit != 0]
        assert len(rows_with_activity) == 2
