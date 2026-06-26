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

    def get_general_balance(self, user_id: int, product_name: str) -> Dict:
        """مثل get_official_balance ولی بدون فیلتر رسمی/غیررسمی - خرید و فروش کل این کالا برای این کاربر."""
        session = self.Session()
        try:
            purchased = session.query(func.coalesce(func.sum(PurchaseItem.quantity), 0)).join(
                PurchaseInvoice, PurchaseItem.purchase_invoice_id == PurchaseInvoice.id
            ).filter(
                PurchaseInvoice.user_id == user_id,
                PurchaseItem.description == product_name,
            ).scalar() or 0

            sold = session.query(func.coalesce(func.sum(InvoiceItem.quantity), 0)).join(
                ProformaInvoice, InvoiceItem.invoice_id == ProformaInvoice.id
            ).filter(
                ProformaInvoice.user_id == user_id,
                ProformaInvoice.document_type != "proforma",
                InvoiceItem.description == product_name,
            ).scalar() or 0

            return {
                "product_name": product_name,
                "purchased": float(purchased),
                "sold": float(sold),
                "deficit": max(float(sold) - float(purchased), 0),
            }
        finally:
            session.close()

    def check_sale_items_general(self, user_id: int, items: List[Dict]) -> List[str]:
        """قبل از ثبت هر فاکتور فروش (رسمی یا نه)، بررسی می‌کند که آیا این کالا تا به حال اصلاً خریداری شده یا نه،
        و آیا با لحاظ این فاکتور، فروش کل این کالا از خرید کل آن بیشتر می‌شود یا نه."""
        warnings = []
        for item in items:
            name = item.get("description", "")
            if not name:
                continue
            balance = self.get_general_balance(user_id, name)
            projected_sold = balance["sold"] + float(item.get("quantity", 0))
            projected_deficit = projected_sold - balance["purchased"]
            if projected_deficit > 0:
                if balance["purchased"] == 0:
                    warnings.append(
                        f"کالای «{name}»: سابقه خریدی برای این کالا ثبت نشده، اما در حال فروش "
                        f"{item.get('quantity', 0):,.0f} {item.get('unit', 'عدد')} از آن هستید."
                    )
                else:
                    warnings.append(
                        f"کالای «{name}»: تاکنون {balance['sold']:,.0f} {item.get('unit', 'عدد')} فروخته شده "
                        f"و {balance['purchased']:,.0f} {item.get('unit', 'عدد')} خریداری شده. "
                        f"با ثبت این فاکتور، {projected_deficit:,.0f} {item.get('unit', 'عدد')} بیش از موجودی خریداری‌شده فروخته خواهد شد."
                    )
        return warnings

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
