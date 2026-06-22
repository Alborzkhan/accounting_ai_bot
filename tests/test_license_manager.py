from datetime import datetime, timedelta
import pytest
from core.license_manager import LicenseManager


@pytest.fixture
def license_manager(db_path):
    return LicenseManager(db_path)


class TestPricingPlans:
    def test_default_plans_are_seeded(self, license_manager):
        plans = license_manager.get_pricing_plans()
        assert set(plans.keys()) == {"free_trial", "monthly", "quarterly", "semi_annual", "annual"}
        assert plans["monthly"]["months"] == 1
        assert plans["free_trial"]["vouchers"] == 50

    def test_update_pricing_plan(self, license_manager):
        result = license_manager.update_pricing_plan("monthly", price=6000000)
        assert result["success"] is True
        plans = license_manager.get_pricing_plans()
        assert plans["monthly"]["price"] == 6000000

    def test_update_unknown_plan_fails(self, license_manager):
        result = license_manager.update_pricing_plan("not_a_plan", price=1)
        assert result["success"] is False

    def test_inactive_plan_excluded_unless_requested(self, license_manager):
        license_manager.update_pricing_plan("annual", is_active=False)
        active_only = license_manager.get_pricing_plans()
        assert "annual" not in active_only
        with_inactive = license_manager.get_pricing_plans(include_inactive=True)
        assert "annual" in with_inactive


class TestLicenseIssuance:
    def test_generate_license_key_uses_plan_duration_and_cap(self, license_manager):
        key = license_manager.generate_license_key(1, "monthly")
        assert len(key) == 16
        status = license_manager.check_license(1)
        assert status["is_valid"] is True
        assert status["plan_type"] == "monthly"
        assert status["max_vouchers"] == 0

    def test_new_license_deactivates_previous_one(self, license_manager):
        license_manager.generate_license_key(1, "free_trial")
        license_manager.generate_license_key(1, "monthly")
        status = license_manager.check_license(1)
        assert status["plan_type"] == "monthly"

    def test_can_create_voucher_respects_free_trial_cap(self, license_manager, engine):
        license_manager.generate_license_key(2, "free_trial")
        for i in range(50):
            engine.create_voucher(
                date=datetime.now(), description=f"سند {i}",
                lines=[('1001', 1000, 'debit'), ('4001', 1000, 'credit')], user_id=2,
            )
        result = license_manager.can_create_voucher(2)
        assert result["allowed"] is False

    def test_can_create_voucher_unlimited_for_paid_plan(self, license_manager, engine):
        license_manager.generate_license_key(3, "monthly")
        for i in range(60):
            engine.create_voucher(
                date=datetime.now(), description=f"سند {i}",
                lines=[('1001', 1000, 'debit'), ('4001', 1000, 'credit')], user_id=3,
            )
        result = license_manager.can_create_voucher(3)
        assert result["allowed"] is True

    def test_check_license_without_one_is_invalid(self, license_manager):
        status = license_manager.check_license(999)
        assert status["is_valid"] is False


class TestDiscountCodes:
    def test_create_and_list_discount_code(self, license_manager):
        result = license_manager.create_discount_code("OFF10", "ده درصد", "percent", 10)
        assert result["success"] is True
        codes = license_manager.list_discount_codes()
        assert any(c["code"] == "OFF10" for c in codes)

    def test_duplicate_code_rejected(self, license_manager):
        license_manager.create_discount_code("OFF10", "ده درصد", "percent", 10)
        result = license_manager.create_discount_code("OFF10", "تکراری", "percent", 5)
        assert result["success"] is False

    def test_toggle_discount_code(self, license_manager):
        created = license_manager.create_discount_code("OFF10", "ده درصد", "percent", 10)
        toggled = license_manager.toggle_discount_code(created["id"])
        assert toggled["is_active"] is False

    def test_validate_percent_discount(self, license_manager):
        license_manager.create_discount_code("OFF10", "ده درصد", "percent", 10)
        result = license_manager.validate_and_apply_discount("OFF10", "monthly", 1000000)
        assert result["success"] is True
        assert result["final_price"] == 900000

    def test_validate_fixed_discount(self, license_manager):
        license_manager.create_discount_code("FLAT50K", "تخفیف ثابت", "fixed", 50000)
        result = license_manager.validate_and_apply_discount("FLAT50K", "monthly", 1000000)
        assert result["final_price"] == 950000

    def test_invalid_code_rejected(self, license_manager):
        result = license_manager.validate_and_apply_discount("NOPE", "monthly", 1000000)
        assert result["success"] is False

    def test_discount_restricted_to_other_plan_rejected(self, license_manager):
        license_manager.create_discount_code("MONTHLYONLY", "فقط ماهانه", "percent", 10, applicable_plan="monthly")
        result = license_manager.validate_and_apply_discount("MONTHLYONLY", "annual", 1000000)
        assert result["success"] is False

    def test_expired_discount_rejected(self, license_manager):
        license_manager.create_discount_code(
            "EXPIRED", "منقضی", "percent", 10, end_date=datetime.now() - timedelta(days=1)
        )
        result = license_manager.validate_and_apply_discount("EXPIRED", "monthly", 1000000)
        assert result["success"] is False

    def test_max_uses_enforced(self, license_manager):
        license_manager.create_discount_code("ONEUSE", "یک‌بار", "percent", 10, max_uses=1)
        first = license_manager.validate_and_apply_discount("ONEUSE", "monthly", 1000000)
        assert first["success"] is True
        second = license_manager.validate_and_apply_discount("ONEUSE", "monthly", 1000000)
        assert second["success"] is False
