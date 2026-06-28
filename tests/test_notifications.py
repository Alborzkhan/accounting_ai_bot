from datetime import datetime, timedelta
import pytest

from core.notifications import NotificationService
from core.invoice_generator import InvoiceGenerator
from database.license_models import User


@pytest.fixture
def notifier(db_path):
    return NotificationService(db_path)


@pytest.fixture
def invoice_gen(db_path):
    return InvoiceGenerator(db_path)


def _make_user(notifier, user_id=1):
    session = notifier.Session()
    try:
        session.add(User(id=user_id, mobile=f"0912000000{user_id}", name="کاربر تست"))
        session.commit()
    finally:
        session.close()


class TestInventoryDeficitReminder:
    def test_no_reminder_when_no_deficit(self, notifier, invoice_gen):
        _make_user(notifier)
        assert notifier.get_inventory_deficit_reminder(1) is None

    def test_reminder_lists_product_with_no_purchase(self, notifier, invoice_gen):
        _make_user(notifier)
        customer_id = invoice_gen.find_or_create_customer("مشتری الف", user_id=1)
        invoice_gen.create_invoice(
            customer_id=customer_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 150000}],
            user_id=1,
            document_type="sale",
        )
        msg = notifier.get_inventory_deficit_reminder(1)
        assert msg is not None
        assert "میز اداری" in msg

    def test_respects_cooldown_after_first_reminder(self, notifier, invoice_gen):
        """رگرسیون: یادآوری باید «هرازگاهی» باشد، نه روی هر پیام - بدون این کنترل، پیام روی هر تعامل تکرار می‌شد."""
        _make_user(notifier)
        customer_id = invoice_gen.find_or_create_customer("مشتری الف", user_id=1)
        invoice_gen.create_invoice(
            customer_id=customer_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 150000}],
            user_id=1,
            document_type="sale",
        )
        first = notifier.get_inventory_deficit_reminder(1)
        assert first is not None
        second = notifier.get_inventory_deficit_reminder(1)
        assert second is None

    def test_reminder_fires_again_after_cooldown_expires(self, notifier, invoice_gen):
        _make_user(notifier)
        customer_id = invoice_gen.find_or_create_customer("مشتری الف", user_id=1)
        invoice_gen.create_invoice(
            customer_id=customer_id,
            items=[{"description": "میز اداری", "quantity": 5, "unit": "عدد", "unit_price": 150000}],
            user_id=1,
            document_type="sale",
        )
        notifier.get_inventory_deficit_reminder(1)

        session = notifier.Session()
        try:
            user = session.query(User).filter_by(id=1).first()
            user.last_inventory_reminder_at = datetime.now() - timedelta(hours=25)
            session.commit()
        finally:
            session.close()

        assert notifier.get_inventory_deficit_reminder(1) is not None
