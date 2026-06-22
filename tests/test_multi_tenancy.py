from datetime import datetime, timedelta
import pytest


def _voucher(engine, user_id, amount=1000000, date=None):
    return engine.create_voucher(
        date=date or datetime.now(),
        description="سند تست",
        lines=[('1001', amount, 'debit'), ('4001', amount, 'credit')],
        user_id=user_id,
    )


class TestVoucherScoping:
    def test_create_voucher_stores_user_id(self, engine):
        eid = _voucher(engine, user_id=7)
        session = engine.Session()
        try:
            from database.models import JournalEntry
            entry = session.query(JournalEntry).filter_by(id=eid).first()
            assert entry.user_id == 7
        finally:
            session.close()

    def test_trial_balance_is_isolated_per_user(self, engine):
        _voucher(engine, user_id=1, amount=1000000)
        _voucher(engine, user_id=2, amount=5000000)

        tb1 = engine.get_trial_balance(user_id=1)
        tb2 = engine.get_trial_balance(user_id=2)

        cash1 = next(r for r in tb1 if r.code == '1001')
        cash2 = next(r for r in tb2 if r.code == '1001')
        assert cash1.total_debit == 1000000
        assert cash2.total_debit == 5000000

    def test_profit_loss_is_isolated_per_user(self, engine):
        _voucher(engine, user_id=1, amount=2000000)
        _voucher(engine, user_id=2, amount=3000000)

        pl1 = engine.get_profit_loss(user_id=1)
        pl2 = engine.get_profit_loss(user_id=2)
        sales1 = next(r for r in pl1 if r.code == '4001')
        sales2 = next(r for r in pl2 if r.code == '4001')
        assert sales1.balance == 2000000
        assert sales2.balance == 3000000

    def test_balance_sheet_is_isolated_per_user(self, engine):
        _voucher(engine, user_id=1, amount=1500000)
        _voucher(engine, user_id=2, amount=4500000)

        bs1 = engine.get_balance_sheet(user_id=1)
        bs2 = engine.get_balance_sheet(user_id=2)
        cash1 = next(a for a in bs1["assets"] if a["code"] == '1001')
        cash2 = next(a for a in bs2["assets"] if a["code"] == '1001')
        assert cash1["balance"] == 1500000
        assert cash2["balance"] == 4500000

    def test_journal_is_isolated_per_user(self, engine):
        _voucher(engine, user_id=1)
        _voucher(engine, user_id=1)
        _voucher(engine, user_id=2)

        journal1 = engine.get_journal(user_id=1)
        journal2 = engine.get_journal(user_id=2)
        assert len(journal1) == 2
        assert len(journal2) == 1

    def test_no_user_id_falls_back_to_default_user(self, engine):
        eid = engine.create_voucher(
            date=datetime.now(), description="بدون کاربر",
            lines=[('1001', 1000, 'debit'), ('4001', 1000, 'credit')],
        )
        session = engine.Session()
        try:
            from database.models import JournalEntry
            entry = session.query(JournalEntry).filter_by(id=eid).first()
            assert entry.user_id == 1
        finally:
            session.close()


class TestFiscalYearClosing:
    def test_close_fiscal_year_computes_net_result(self, engine):
        start = datetime(2025, 1, 1)
        end = datetime(2025, 12, 29)
        _voucher(engine, user_id=10, amount=10000000, date=start + timedelta(days=10))

        result = engine.close_fiscal_year(10, start, end, "1404")
        assert result["success"] is True
        assert result["net_result"] == 10000000

    def test_closed_period_blocks_new_voucher_for_same_user(self, engine):
        start = datetime(2025, 1, 1)
        end = datetime(2025, 12, 29)
        _voucher(engine, user_id=11, amount=1000000, date=start + timedelta(days=5))
        engine.close_fiscal_year(11, start, end, "1404")

        with pytest.raises(ValueError, match="دوره مالی بسته‌شده"):
            _voucher(engine, user_id=11, amount=1000, date=start + timedelta(days=6))

    def test_closing_one_user_does_not_block_another_user(self, engine):
        start = datetime(2025, 1, 1)
        end = datetime(2025, 12, 29)
        _voucher(engine, user_id=12, amount=1000000, date=start + timedelta(days=5))
        engine.close_fiscal_year(12, start, end, "1404")

        # کاربر دیگر باید بتواند در همان بازه تاریخی سند ثبت کند
        eid = _voucher(engine, user_id=13, amount=2000, date=start + timedelta(days=6))
        assert eid > 0

    def test_close_fiscal_year_rejects_overlapping_period(self, engine):
        start = datetime(2025, 1, 1)
        end = datetime(2025, 12, 29)
        _voucher(engine, user_id=14, amount=1000000, date=start + timedelta(days=5))
        engine.close_fiscal_year(14, start, end, "1404")

        result = engine.close_fiscal_year(14, datetime(2025, 6, 1), datetime(2025, 12, 31), "1404-b")
        assert result["success"] is False
        assert "تداخل" in result["message"]
