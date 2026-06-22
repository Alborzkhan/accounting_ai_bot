import pytest
from core.invoice_generator import InvoiceGenerator


@pytest.fixture
def invoice_gen(db_path):
    return InvoiceGenerator(db_path)


class TestCustomerVendorDedup:
    def test_find_or_create_customer_creates_once(self, invoice_gen):
        id1 = invoice_gen.find_or_create_customer("علی کریمی", "09121234567")
        id2 = invoice_gen.find_or_create_customer("علی کریمی", "09121234567")
        assert id1 == id2

    def test_find_or_create_customer_without_mobile(self, invoice_gen):
        cid = invoice_gen.find_or_create_customer("نامشخص")
        assert cid > 0

    def test_find_or_create_vendor_creates_once(self, invoice_gen):
        id1 = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        id2 = invoice_gen.find_or_create_vendor("تامین‌کننده الف")
        assert id1 == id2


class TestCreateInvoice:
    def test_create_invoice_computes_totals(self, invoice_gen):
        cid = invoice_gen.find_or_create_customer("مشتری ۱")
        result = invoice_gen.create_invoice(
            customer_id=cid,
            items=[{"description": "میز", "quantity": 2, "unit": "عدد", "unit_price": 500000}],
            apply_vat=True, vat_rate=9, user_id=1,
        )
        assert result["success"] is True
        assert result["subtotal"] == 1000000
        assert result["vat_amount"] == pytest.approx(90000)
        assert result["total"] == pytest.approx(1090000)

    def test_create_invoice_without_vat(self, invoice_gen):
        cid = invoice_gen.find_or_create_customer("مشتری ۱")
        result = invoice_gen.create_invoice(
            customer_id=cid,
            items=[{"description": "میز", "quantity": 1, "unit": "عدد", "unit_price": 200000}],
            apply_vat=False, user_id=1,
        )
        assert result["vat_amount"] == 0
        assert result["total"] == 200000


class TestPerUserInvoiceNumbering:
    def test_two_users_do_not_collide_on_invoice_number(self, invoice_gen):
        c1 = invoice_gen.find_or_create_customer("مشتری کاربر یک")
        c2 = invoice_gen.find_or_create_customer("مشتری کاربر دو")
        r1 = invoice_gen.create_invoice(
            customer_id=c1, items=[{"description": "کالا", "quantity": 1, "unit_price": 1000}], user_id=1,
        )
        r2 = invoice_gen.create_invoice(
            customer_id=c2, items=[{"description": "کالا", "quantity": 1, "unit_price": 1000}], user_id=2,
        )
        assert r1["invoice_number"] == r2["invoice_number"]

    def test_same_user_numbers_increment(self, invoice_gen):
        cid = invoice_gen.find_or_create_customer("مشتری")
        r1 = invoice_gen.create_invoice(
            customer_id=cid, items=[{"description": "کالا", "quantity": 1, "unit_price": 1000}], user_id=5,
        )
        r2 = invoice_gen.create_invoice(
            customer_id=cid, items=[{"description": "کالا", "quantity": 1, "unit_price": 1000}], user_id=5,
        )
        assert r1["invoice_number"] != r2["invoice_number"]

    def test_list_invoices_is_isolated_per_user(self, invoice_gen):
        cid = invoice_gen.find_or_create_customer("مشتری")
        invoice_gen.create_invoice(customer_id=cid, items=[{"description": "کالا", "quantity": 1, "unit_price": 1000}], user_id=1)
        invoice_gen.create_invoice(customer_id=cid, items=[{"description": "کالا", "quantity": 1, "unit_price": 1000}], user_id=2)
        assert len(invoice_gen.list_invoices(user_id=1)) == 1
        assert len(invoice_gen.list_invoices(user_id=2)) == 1


class TestPurchaseInvoice:
    def test_create_purchase_invoice_computes_totals(self, invoice_gen):
        vid = invoice_gen.find_or_create_vendor("فروشنده الف")
        result = invoice_gen.create_purchase_invoice(
            vendor_id=vid,
            items=[{"description": "مواد اولیه", "quantity": 4, "unit": "کیلوگرم", "unit_price": 250000}],
            apply_vat=True, vat_rate=9, user_id=1,
        )
        assert result["success"] is True
        assert result["subtotal"] == 1000000
        assert result["vat_amount"] == pytest.approx(90000)

    def test_get_purchase_invoice_is_scoped_to_user(self, invoice_gen):
        vid = invoice_gen.find_or_create_vendor("فروشنده الف")
        created = invoice_gen.create_purchase_invoice(
            vendor_id=vid, items=[{"description": "کالا", "quantity": 1, "unit_price": 1000}], user_id=1,
        )
        found_for_owner = invoice_gen.get_purchase_invoice(created["invoice_id"], user_id=1)
        found_for_other = invoice_gen.get_purchase_invoice(created["invoice_id"], user_id=2)
        assert found_for_owner is not None
        assert found_for_other is None
