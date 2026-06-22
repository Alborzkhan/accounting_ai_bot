import pytest
from core.building_manager import BuildingManager


@pytest.fixture
def bm(db_path):
    return BuildingManager(db_path)


def _building_with_units(bm, user_id, charge_method="area"):
    b = bm.add_building(user_id, "برج آذر", total_units=2, charge_method=charge_method)
    building_id = b["building_id"]
    u1 = bm.add_unit(building_id, "1", area=100, occupant_count=2)
    u2 = bm.add_unit(building_id, "2", area=50, occupant_count=1)
    return building_id, u1["unit_id"], u2["unit_id"]


class TestChargeCalculation:
    def test_area_based_split(self, bm):
        building_id, u1, u2 = _building_with_units(bm, user_id=1, charge_method="area")
        bm.add_expense(building_id, "برق مشاعات", 300000)
        calc = bm.calculate_maintenance_fee(building_id, "1404-04")
        assert calc["success"] is True
        fee1 = next(f for f in calc["unit_fees"] if f["unit_id"] == u1)
        fee2 = next(f for f in calc["unit_fees"] if f["unit_id"] == u2)
        # واحد ۱ متراژ ۱۰۰ و واحد ۲ متراژ ۵۰ از کل ۳۰۰,۰۰۰ تومان -> نسبت ۲ به ۱
        assert fee1["fee"] == pytest.approx(200000)
        assert fee2["fee"] == pytest.approx(100000)

    def test_equal_split_with_vacant_weight(self, bm):
        building_id = bm.add_building(1, "برج تست", charge_method="equal")["building_id"]
        occupied = bm.add_unit(building_id, "1", is_vacant=False)["unit_id"]
        vacant = bm.add_unit(building_id, "2", is_vacant=True)["unit_id"]
        bm.add_expense(building_id, "نظافت", 150000)
        calc = bm.calculate_maintenance_fee(building_id, "1404-04")
        fee_occupied = next(f for f in calc["unit_fees"] if f["unit_id"] == occupied)["fee"]
        fee_vacant = next(f for f in calc["unit_fees"] if f["unit_id"] == vacant)["fee"]
        # وزن واحد خالی پیش‌فرض 0.5 است، پس واحد ساکن دو برابر سهم می‌گیرد
        assert fee_occupied == pytest.approx(100000)
        assert fee_vacant == pytest.approx(50000)

    def test_no_expense_returns_failure(self, bm):
        building_id, _, _ = _building_with_units(bm, user_id=1)
        calc = bm.calculate_maintenance_fee(building_id, "1404-04")
        assert calc["success"] is False

    def test_invalid_charge_method_falls_back_to_area(self, bm):
        building_id = bm.add_building(1, "برج تست", charge_method="invalid")["building_id"]
        session = bm.Session()
        try:
            from database.building_models import Building
            building = session.query(Building).filter_by(id=building_id).first()
            assert building.charge_method == "area"
        finally:
            session.close()


class TestAccountingIntegration:
    def test_expense_posts_voucher_with_building_owner_user_id(self, bm, engine):
        building_id = bm.add_building(42, "برج آذر")["building_id"]
        bm.add_expense(building_id, "آسانسور", 200000)
        journal = engine.get_journal(user_id=42)
        assert len(journal) == 1
        assert journal[0]["lines"][0]["amount"] == 200000

    def test_invoice_and_payment_post_vouchers_for_correct_user(self, bm, engine):
        building_id, u1, _ = _building_with_units(bm, user_id=99)
        bm.add_expense(building_id, "برق مشاعات", 300000)
        bm.issue_invoices_for_month(building_id, "1404-04")

        unpaid = bm.get_unpaid_invoices(building_id)
        assert len(unpaid) == 2

        bm.mark_invoice_paid(unpaid[0].id)

        journal = engine.get_journal(user_id=99)
        # یک سند هزینه + دو سند صدور قبض + یک سند دریافت = ۴
        assert len(journal) == 4

        other_user_journal = engine.get_journal(user_id=1)
        assert len(other_user_journal) == 0
