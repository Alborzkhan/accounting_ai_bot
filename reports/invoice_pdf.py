# reports/invoice_pdf.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jdatetime
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
import os

from database.models import ProformaInvoice
from core.invoice_generator import InvoiceGenerator


class InvoicePDF:
    def __init__(self) -> None:
        # تلاش برای بارگذاری فونت فارسی (اختیاری)
        try:
            pdfmetrics.registerFont(TTFont('Vazir', 'static/Vazir.ttf'))
            self.font_name = 'Vazir'
        except:
            self.font_name = 'Helvetica'
    
    def create_invoice_pdf(self, invoice_data: dict, filename: str = "invoice.pdf", document_type: str = "sale") -> str:
        """ایجاد PDF پیش‌فاکتور"""
        doc = SimpleDocTemplate(filename, pagesize=A4)
        styles = getSampleStyleSheet()
        
        # استایل فارسی
        persian_style = ParagraphStyle(
            'PersianStyle',
            parent=styles['Normal'],
            fontName=self.font_name,
            fontSize=10,
            alignment=TA_RIGHT
        )
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontName=self.font_name,
            fontSize=16,
            alignment=TA_CENTER
        )
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Heading2'],
            fontName=self.font_name,
            fontSize=12,
            alignment=TA_RIGHT
        )
        
        story = []
        
        # لوگو (اگر وجود داشته باشد)
        seller = invoice_data.get('seller')
        if seller and seller.logo_path and os.path.exists(seller.logo_path):
            try:
                logo = Image(seller.logo_path, width=2*cm, height=2*cm)
                story.append(logo)
            except:
                pass
        
        # عنوان
        invoice = invoice_data.get('invoice')
        is_official = bool(getattr(invoice, 'is_official', False)) if invoice else False
        if document_type == "purchase":
            title = "فاکتور رسمی خرید" if is_official else "فاکتور خرید"
        elif document_type == "proforma":
            title = "پیش‌فاکتور رسمی" if is_official else "پیش‌فاکتور"
        else:
            title = "فاکتور رسمی فروش" if is_official else "فاکتور فروش"
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.5*cm))

        # اطلاعات فروشنده
        if seller:
            seller_lines = [f"<b>{getattr(seller, 'company_name', '') or '-'}</b>"]
            seller_lines.append(f"آدرس: {getattr(seller, 'address', '') or '-'}")
            seller_lines.append(f"تلفن: {getattr(seller, 'phone', '') or '-'} | موبایل: {getattr(seller, 'mobile', '') or '-'}")
            if getattr(seller, 'national_id', '') or getattr(seller, 'tax_id', ''):
                seller_lines.append(f"شناسه ملی: {getattr(seller, 'national_id', '') or getattr(seller, 'tax_id', '') or '-'}")
            if getattr(seller, 'economic_code', ''):
                seller_lines.append(f"کد اقتصادی: {seller.economic_code}")
            if getattr(seller, 'company_registration_number', ''):
                seller_lines.append(f"شماره ثبت شرکت: {seller.company_registration_number}")
            story.append(Paragraph("<br/>".join(seller_lines), persian_style))
            story.append(Spacer(1, 0.5*cm))

        # اطلاعات مشتری
        customer = invoice_data.get('customer')
        if customer:
            party_label = "فروشنده/تامین‌کننده" if document_type == "purchase" else "مشتری"
            party_phone = getattr(customer, 'mobile', None) or getattr(customer, 'phone', None) or '-'
            customer_lines = [f"<b>{party_label}:</b> {customer.name}", f"تلفن: {party_phone}"]
            party_national_id = getattr(invoice, 'buyer_national_id', None) or getattr(invoice, 'vendor_national_id', None) if invoice else None
            party_economic_code = getattr(invoice, 'buyer_economic_code', None) or getattr(invoice, 'vendor_economic_code', None) if invoice else None
            if party_national_id:
                customer_lines.append(f"شناسه ملی: {party_national_id}")
            if party_economic_code:
                customer_lines.append(f"کد اقتصادی: {party_economic_code}")
            story.append(Paragraph("<br/>".join(customer_lines), persian_style))
            story.append(Spacer(1, 0.5*cm))

        # اطلاعات فاکتور
        if invoice:
            shamsi_date = jdatetime.date.fromgregorian(date=invoice.date.date()).strftime('%Y/%m/%d')
            info_text = f"شماره فاکتور: {invoice.invoice_number} | تاریخ: {shamsi_date}"
            story.append(Paragraph(info_text, persian_style))
            story.append(Spacer(1, 0.5*cm))
        
        # جدول کالاها
        items = invoice_data.get('items', [])
        table_data = [["ردیف", "شرح کالا/خدمت", "تعداد", "قیمت واحد", "جمع"]]
        
        for i, item in enumerate(items, 1):
            table_data.append([
                str(i),
                item.description,
                f"{item.quantity:,.0f}",
                f"{item.unit_price:,.0f}",
                f"{item.total:,.0f}"
            ])
        
        # جمع کل
        if invoice:
            table_data.append(["", "", "", "جمع کل:", f"{invoice.subtotal:,.0f}"])
            if invoice.is_vat_applied and invoice.vat_amount > 0:
                table_data.append(["", "", "", f"مالیات ({invoice.vat_rate:.0f}%):", f"{invoice.vat_amount:,.0f}"])
            table_data.append(["", "", "", "مبلغ نهایی:", f"{invoice.total:,.0f}"])
        
        table = Table(table_data, colWidths=[1.5*cm, 7*cm, 2*cm, 3*cm, 3*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.black),
            ('BACKGROUND', (0, -3), (-1, -1), colors.lightgrey),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 1*cm))
        
        # توضیحات
        if invoice and invoice.description:
            story.append(Paragraph(f"توضیحات: {invoice.description}", persian_style))
        
        # امضا
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph("امضا و مهر فروشنده", persian_style))
        
        doc.build(story)
        print(f"✅ PDF در {filename} ذخیره شد.")
        return filename


if __name__ == "__main__":
    gen = InvoiceGenerator()
    pdf_maker = InvoicePDF()
    
    # دریافت آخرین فاکتور
    session = gen.Session()
    try:
        last_invoice = session.query(ProformaInvoice).order_by(ProformaInvoice.id.desc()).first()
        
        if last_invoice:
            invoice_data = gen.get_invoice(last_invoice.id)
            if invoice_data:
                pdf_maker.create_invoice_pdf(invoice_data, "test_invoice.pdf")
                print("✅ PDF تست ساخته شد.")
            else:
                print("⚠️ داده‌های فاکتور یافت نشد.")
        else:
            print("⚠️ فاکتوری برای تست وجود ندارد. ابتدا یک فاکتور بسازید.")
    except Exception as e:
        print(f"❌ خطا: {e}")
    finally:
        session.close()