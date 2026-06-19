# core/inventory_reconciler.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from database.models import init_db, InvoiceItem, ProformaInvoice, PurchaseItem, PurchaseInvoice


class InventoryReconciler:
    """تطبیق میزان فروش رسمی با خرید رسمی برای هر کالا، برای شناسایی کسری احتمالی (فروش بیش از خرید ثبت‌شده)."""

    def __init__(self, db_path: str = "accounting.db") -> None:
        self.engine = init_db(db_path)
        self.Session = sessionmaker(bind=self.engine)

    def get_official_balance(self, user_id: int, product_name: str) -> Dict:
        session = self.Session()
        try:
            purchased = session.query(func.coalesce(func.sum(PurchaseItem.quantity), 0)).join(
                PurchaseInvoice, PurchaseItem.purchase_invoice_id == PurchaseInvoice.id
            ).filter(
                PurchaseInvoice.user_id == user_id,
                PurchaseInvoice.is_official == True,
                PurchaseItem.description == product_name,
            ).scalar() or 0

            sold = session.query(func.coalesce(func.sum(InvoiceItem.quantity), 0)).join(
                ProformaInvoice, InvoiceItem.invoice_id == ProformaInvoice.id
            ).filter(
                ProformaInvoice.user_id == user_id,
                ProformaInvoice.is_official == True,
                InvoiceItem.description == product_name,
            ).scalar() or 0

            return {
                "product_name": product_name,
                "purchased_official": float(purchased),
                "sold_official": float(sold),
                "deficit": max(float(sold) - float(purchased), 0),
            }
        finally:
            session.close()

    def check_sale_items(self, user_id: int, items: List[Dict]) -> List[str]:
        """قبل از ثبت یک فاکتور فروش رسمی، بررسی می‌کند که آیا با لحاظ این فاکتور، فروش رسمی هر کالا از خرید رسمی ثبت‌شده آن بیشتر می‌شود یا نه."""
        warnings = []
        for item in items:
            name = item.get("description", "")
            if not name:
                continue
            balance = self.get_official_balance(user_id, name)
            projected_sold = balance["sold_official"] + float(item.get("quantity", 0))
            projected_deficit = projected_sold - balance["purchased_official"]
            if projected_deficit > 0:
                warnings.append(
                    f"کالای «{name}»: تاکنون {balance['sold_official']:,.0f} {item.get('unit', 'عدد')} با فاکتور رسمی فروخته شده "
                    f"و {balance['purchased_official']:,.0f} {item.get('unit', 'عدد')} با فاکتور رسمی خریداری شده. "
                    f"با ثبت این فاکتور، {projected_deficit:,.0f} {item.get('unit', 'عدد')} بیش از خرید رسمی فروخته خواهد شد."
                )
        return warnings
