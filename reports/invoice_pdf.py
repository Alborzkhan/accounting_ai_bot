# reports/invoice_pdf.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
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
import arabic_reshaper
from bidi.algorithm import get_display

from database.models import ProformaInvoice
from core.invoice_generator import InvoiceGenerator

logger = logging.getLogger(__name__)

FONT_DIR = os.path.join("static", "fonts")


def rtl(text) -> str:
    """متن فارسی/عربی را برای نمایش صحیح در PDF (شکل‌دهی حروف + ترتیب راست‌به‌چپ) آماده می‌کند."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return text
    return get_display(arabic_reshaper.reshape(text))


class InvoicePDF:
    def __init__(self) -> None:
        try:
            pdfmetrics.registerFont(TTFont('Vazirmatn', os.path.join(FONT_DIR, 'Vazirmatn-Regular.ttf')))
            pdfmetrics.registerFont(TTFont('Vazirmatn-Bold', os.path.join(FONT_DIR, 'Vazirmatn-Bold.ttf')))
            self.font_name = 'Vazirmatn'
            self.font_name_bold = 'Vazirmatn-Bold'
        except Exception:
            logger.exception("Persian font (Vazirmatn) could not be loaded; PDF text will not render Persian correctly.")
            self.font_name = 'Helvetica'
            self.font_name_bold = 'Helvetica-Bold'

    def create_invoice_pdf(self, invoice_data: dict, filename: str = "invoice.pdf", document_type: str = "sale") -> str:
        """ایجاد PDF فاکتور/پیش‌فاکتور با چیدمان راست‌به‌چپ و قلم فارسی."""
        doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=1.5 * cm, leftMargin=1.5 * cm)
        styles = getSampleStyleSheet()

        persian_style = ParagraphStyle(
            'PersianStyle', parent=styles['Normal'],
            fontName=self.font_name, fontSize=10, alignment=TA_RIGHT, leading=15,
        )
        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Title'],
            fontName=self.font_name_bold, fontSize=16, alignment=TA_CENTER,
        )

        story = []

        seller = invoice_data.get('seller')
        if seller and getattr(seller, 'logo_path', None) and os.path.exists(seller.logo_path):
            try:
                story.append(Image(seller.logo_path, width=2 * cm, height=2 * cm))
            except Exception:
                pass

        invoice = invoice_data.get('invoice')
        is_official = bool(getattr(invoice, 'is_official', False)) if invoice else False
        if document_type == "purchase":
            title = "فاکتور رسمی خرید" if is_official else "فاکتور خرید"
        elif document_type == "proforma":
            title = "پیش‌فاکتور رسمی" if is_official else "پیش‌فاکتور"
        else:
            title = "فاکتور رسمی فروش" if is_official else "فاکتور فروش"
        story.append(Paragraph(rtl(title), title_style))
        story.append(Spacer(1, 0.5 * cm))

        if invoice:
            shamsi_date = jdatetime.date.fromgregorian(date=invoice.date.date()).strftime('%Y/%m/%d')
            info_text = f"{rtl('شماره فاکتور')}: {invoice.invoice_number}     {rtl('تاریخ')}: {shamsi_date}"
            story.append(Paragraph(info_text, persian_style))
            story.append(Spacer(1, 0.4 * cm))

        if seller:
            seller_lines = [f"<b>{rtl(getattr(seller, 'company_name', '') or '-')}</b>"]
            seller_lines.append(f"{rtl('آدرس')}: {rtl(getattr(seller, 'address', '') or '-')}")
            seller_lines.append(
                f"{rtl('تلفن')}: {getattr(seller, 'phone', '') or '-'} | "
                f"{rtl('موبایل')}: {getattr(seller, 'mobile', '') or '-'}"
            )
            if getattr(seller, 'national_id', '') or getattr(seller, 'tax_id', ''):
                seller_lines.append(f"{rtl('شناسه ملی')}: {getattr(seller, 'national_id', '') or getattr(seller, 'tax_id', '')}")
            if getattr(seller, 'economic_code', ''):
                seller_lines.append(f"{rtl('کد اقتصادی')}: {seller.economic_code}")
            if getattr(seller, 'company_registration_number', ''):
                seller_lines.append(f"{rtl('شماره ثبت شرکت')}: {seller.company_registration_number}")
            story.append(Paragraph("<br/>".join(seller_lines), persian_style))
            story.append(Spacer(1, 0.4 * cm))

        customer = invoice_data.get('customer')
        if customer:
            party_label = "فروشنده/تامین‌کننده" if document_type == "purchase" else "مشتری"
            party_phone = getattr(customer, 'mobile', None) or getattr(customer, 'phone', None) or '-'
            customer_lines = [f"<b>{rtl(party_label)}:</b> {rtl(customer.name)}", f"{rtl('تلفن')}: {party_phone}"]
            party_national_id = getattr(invoice, 'buyer_national_id', None) or getattr(invoice, 'vendor_national_id', None) if invoice else None
            party_economic_code = getattr(invoice, 'buyer_economic_code', None) or getattr(invoice, 'vendor_economic_code', None) if invoice else None
            party_address = getattr(customer, 'address', None)
            if party_national_id:
                customer_lines.append(f"{rtl('شناسه ملی')}: {party_national_id}")
            if party_economic_code:
                customer_lines.append(f"{rtl('کد اقتصادی')}: {party_economic_code}")
            if party_address:
                customer_lines.append(f"{rtl('آدرس')}: {rtl(party_address)}")
            story.append(Paragraph("<br/>".join(customer_lines), persian_style))
            story.append(Spacer(1, 0.5 * cm))

        # جدول اقلام - راست به چپ: ردیف سمت راست‌ترین ستون است، پس ترتیب آرایه برعکس می‌شود
        items = invoice_data.get('items', [])
        header_row = [rtl("جمع"), rtl("بهای واحد"), rtl("واحد"), rtl("تعداد"), rtl("شرح کالا/خدمت"), rtl("ردیف")]
        table_data = [header_row]
        for i, item in enumerate(items, 1):
            table_data.append([
                f"{item.total:,.0f}",
                f"{item.unit_price:,.0f}",
                rtl(getattr(item, 'unit', '') or 'عدد'),
                f"{item.quantity:,.0f}",
                rtl(item.description),
                str(i),
            ])

        summary_row_count = 0
        if invoice:
            table_data.append([f"{invoice.subtotal:,.0f}", rtl("جمع کل"), "", "", "", ""])
            summary_row_count += 1
            if invoice.is_vat_applied and invoice.vat_amount > 0:
                table_data.append([f"{invoice.vat_amount:,.0f}", rtl(f"مالیات ({invoice.vat_rate:.0f}%)"), "", "", "", ""])
                summary_row_count += 1
            table_data.append([f"{invoice.total:,.0f}", rtl("مبلغ نهایی قابل پرداخت"), "", "", "", ""])
            summary_row_count += 1

        col_widths = [2.5 * cm, 2.5 * cm, 1.5 * cm, 1.5 * cm, 7 * cm, 1.5 * cm]
        table = Table(table_data, colWidths=col_widths)
        first_summary_row = len(table_data) - summary_row_count
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), self.font_name_bold),
            ('FONTNAME', (0, 1), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('GRID', (0, 0), (-1, len(items)), 0.5, colors.black),
        ]
        if summary_row_count:
            style_commands.append(('BACKGROUND', (0, first_summary_row), (-1, -1), colors.HexColor('#f0f0f0')))
            for r in range(first_summary_row, len(table_data)):
                style_commands.append(('SPAN', (1, r), (5, r)))
            style_commands.append(('FONTNAME', (0, -1), (-1, -1), self.font_name_bold))
        table.setStyle(TableStyle(style_commands))
        story.append(table)
        story.append(Spacer(1, 1 * cm))

        if invoice and invoice.description:
            story.append(Paragraph(f"{rtl('توضیحات')}: {rtl(invoice.description)}", persian_style))

        story.append(Spacer(1, 2 * cm))
        story.append(Paragraph(rtl("امضا و مهر فروشنده"), persian_style))

        doc.build(story)
        logger.info("Invoice PDF saved to %s", filename)
        return filename


if __name__ == "__main__":
    gen = InvoiceGenerator()
    pdf_maker = InvoicePDF()

    session = gen.Session()
    try:
        last_invoice = session.query(ProformaInvoice).order_by(ProformaInvoice.id.desc()).first()

        if last_invoice:
            invoice_data = gen.get_invoice(last_invoice.id)
            if invoice_data:
                pdf_maker.create_invoice_pdf(invoice_data, "test_invoice.pdf")
                print("test PDF created")
            else:
                print("invoice data not found")
        else:
            print("no invoice exists to test with")
    except Exception as e:
        print(f"error: {e}")
    finally:
        session.close()
