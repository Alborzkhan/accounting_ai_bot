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


class TestCheckSaleItemsGeneral:
    """رگرسیون: قبلاً هشدار «فروش بیش از موجودی» فقط وقتی فاکتور رسمی(VAT) بود اجرا می‌شد،
    پس فروش بدون تیک رسمی هیچ هشداری نمی‌گرفت حتی اگر کالا اصلاً خریداری نشده بود."""

    def test_warns_when_item_never_purchased_at_all(self, reconciler):
        warnings = reconciler.check_sale_items_general(1, [{"description": "میز اداری", "quantity": 1, "unit": "عدد"}])
        assert len(warnings) == 1
        assert "میز اداری" in warnings[0]

    def test_no_warning_for_unofficial_purchase_then_unofficial_sale_within_stock(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 10, "unit": "عدد", "unit_price": 100000}],
            apply_vat=False,
            user_id=1,
        )
        warnings = reconciler.check_sale_items_general(1, [{"description": "میز اداری", "quantity": 5, "unit": "عدد"}])
        assert warnings == []

    def test_warns_when_unofficial_sale_exceeds_unofficial_purchase(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 2, "unit": "عدد", "unit_price": 100000}],
            apply_vat=False,
            user_id=1,
        )
        warnings = reconciler.check_sale_items_general(1, [{"description": "میز اداری", "quantity": 5, "unit": "عدد"}])
        assert len(warnings) == 1

    def test_opening_balance_avoids_warning_with_no_purchase_history(self, reconciler):
        """موجودی اول دوره باید معادل خرید قبلی لحاظ شود تا کالایی که قبل از نارین موجود بوده،
        هشدار «فاکتور خرید ندارد» نگیرد."""
        from database.models import OpeningStockBalance
        session = reconciler.Session()
        try:
            session.add(OpeningStockBalance(user_id=1, product_name="میز اداری", quantity=10, unit="عدد"))
            session.commit()
        finally:
            session.close()
        warnings = reconciler.check_sale_items_general(1, [{"description": "میز اداری", "quantity": 5, "unit": "عدد"}])
        assert warnings == []

    def test_opening_balance_does_not_fully_cover_excess_sale(self, reconciler):
        from database.models import OpeningStockBalance
        session = reconciler.Session()
        try:
            session.add(OpeningStockBalance(user_id=1, product_name="میز اداری", quantity=3, unit="عدد"))
            session.commit()
        finally:
            session.close()
        warnings = reconciler.check_sale_items_general(1, [{"description": "میز اداری", "quantity": 5, "unit": "عدد"}])
        assert len(warnings) == 1

    def test_proforma_sales_do_not_count_against_stock(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 100000}],
            user_id=1,
        )
        customer_id = invoice_gen.find_or_create_customer("مشتری الف", user_id=1)
        invoice_gen.create_invoice(
            customer_id=customer_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 150000}],
            user_id=1,
            document_type="proforma",
        )
        # پیش‌فاکتور قبلی نباید به‌عنوان «فروش شده» حساب شود، پس فروش واقعی هنوز باید مجاز باشد
        warnings = reconciler.check_sale_items_general(1, [{"description": "میز اداری", "quantity": 5, "unit": "عدد"}])
        assert warnings == []


class TestGetAllDeficits:
    def test_finds_product_sold_without_any_purchase(self, invoice_gen, reconciler):
        customer_id = invoice_gen.find_or_create_customer("مشتری الف", user_id=1)
        invoice_gen.create_invoice(
            customer_id=customer_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 150000}],
            user_id=1,
            document_type="sale",
        )
        deficits = reconciler.get_all_deficits(1)
        assert len(deficits) == 1
        assert deficits[0]["product_name"] == "میز اداری"
        assert deficits[0]["deficit"] == 5

    def test_no_deficit_once_fully_purchased(self, invoice_gen, reconciler):
        vendor_id = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        invoice_gen.create_purchase_invoice(
            vendor_id=vendor_id,
            items=[{"description": "میز اداری", "quantity": 10, "unit": "عدد", "unit_price": 100000}],
            user_id=1,
        )
        customer_id = invoice_gen.find_or_create_customer("مشتری الف", user_id=1)
        invoice_gen.create_invoice(
            customer_id=customer_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 150000}],
            user_id=1,
            document_type="sale",
        )
        assert reconciler.get_all_deficits(1) == []

    def test_isolated_per_user(self, invoice_gen, reconciler):
        customer_id = invoice_gen.find_or_create_customer("مشتری الف", user_id=1)
        invoice_gen.create_invoice(
            customer_id=customer_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 150000}],
            user_id=1,
            document_type="sale",
        )
        assert reconciler.get_all_deficits(2) == []
