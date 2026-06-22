import pytest
from core.invoice_generator import InvoiceGenerator
from core.inventory_reconciler import InventoryReconciler


@pytest.fixture
def invoice_gen(db_path):
    return InvoiceGenerator(db_path)


@pytest.fixture
def reconciler(db_path):
    return InventoryReconciler(db_path)


class TestOfficialBalance:
    def test_no_data_returns_zero_balance(self, reconciler):
        balance = reconciler.get_official_balance(1, "میز اداری")
        assert balance["purchased_official"] == 0
        assert balance["sold_official"] == 0
        assert balance["deficit"] == 0

    def test_only_counts_official_documents(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        # خرید غیررسمی نباید در محاسبه رسمی لحاظ شود
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 10, "unit": "عدد", "unit_price": 100000}],
            apply_vat=False,
            user_id=1,
        )
        balance = reconciler.get_official_balance(1, "میز اداری")
        assert balance["purchased_official"] == 0


class TestCheckSaleItems:
    def test_no_warning_when_sale_within_purchased_stock(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 10, "unit": "عدد", "unit_price": 100000}],
            apply_vat=True,
            vat_rate=9,
            user_id=1,
        )
        warnings = reconciler.check_sale_items(1, [{"description": "میز اداری", "quantity": 5, "unit": "عدد"}])
        assert warnings == []

    def test_warning_when_sale_exceeds_purchased_stock(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 3, "unit": "عدد", "unit_price": 100000}],
            apply_vat=True,
            vat_rate=9,
            user_id=1,
        )
        warnings = reconciler.check_sale_items(1, [{"description": "میز اداری", "quantity": 5, "unit": "عدد"}])
        assert len(warnings) == 1
        assert "میز اداری" in warnings[0]

    def test_items_without_description_are_skipped(self, reconciler):
        warnings = reconciler.check_sale_items(1, [{"description": "", "quantity": 5}])
        assert warnings == []

    def test_reconciliation_is_isolated_per_user(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 10, "unit": "عدد", "unit_price": 100000}],
            apply_vat=True,
            vat_rate=9,
            user_id=1,
        )
        # کاربر دیگر هیچ خریدی ثبت نکرده؛ فروش او باید هشدار بدهد حتی اگر کاربر ۱ موجودی کافی دارد
        warnings = reconciler.check_sale_items(2, [{"description": "میز اداری", "quantity": 1, "unit": "عدد"}])
        assert len(warnings) == 1
