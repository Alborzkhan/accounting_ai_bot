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
        doc = SimpleDocTemplate(
            filename, pagesize=A4,
            rightMargin=1.5 * cm, leftMargin=1.5 * cm,
            topMargin=1 * cm, bottomMargin=1.5 * cm,
        )

        brand_color = colors.HexColor('#1a3a5c')
        accent_color = colors.HexColor('#2e7d5e')
        header_bg = colors.HexColor('#f5f8fc')
        row_alt = colors.HexColor('#f9fafb')

        p = lambda txt, size=9.5, bold=False, align=TA_RIGHT, color=colors.black: Paragraph(
            txt,
            ParagraphStyle('x', fontName=self.font_name_bold if bold else self.font_name,
                           fontSize=size, alignment=align, leading=size * 1.5, textColor=color)
        )

        story = []
        seller = invoice_data.get('seller')
        invoice = invoice_data.get('invoice')
        is_official = bool(getattr(invoice, 'is_official', False)) if invoice else False

        if document_type == "purchase":
            title_txt = "فاکتور رسمی خرید" if is_official else "فاکتور خرید"
        elif document_type == "proforma":
            title_txt = "پیش‌فاکتور رسمی" if is_official else "پیش‌فاکتور"
        else:
            title_txt = "فاکتور رسمی فروش" if is_official else "فاکتور فروش"

        # ======= هدر: لوگو | عنوان | شماره+تاریخ =======
        shamsi_date = ""
        inv_no = ""
        if invoice:
            shamsi_date = jdatetime.date.fromgregorian(date=invoice.date.date()).strftime('%Y/%m/%d')
            inv_no = invoice.invoice_number or ""

        logo_cell = ""
        if seller and getattr(seller, 'logo_path', None) and os.path.exists(seller.logo_path):
            try:
                logo_cell = Image(seller.logo_path, width=1.8 * cm, height=1.8 * cm)
            except Exception:
                logo_cell = p("")

        title_cell = p(rtl(title_txt), size=16, bold=True, align=TA_CENTER, color=brand_color)
        meta_lines = [f"<b>{rtl('شماره')}</b>: {inv_no}", f"<b>{rtl('تاریخ')}</b>: {shamsi_date}"]
        meta_cell = p("<br/>".join(meta_lines), size=9, align=TA_RIGHT)

        header_tbl = Table([[logo_cell, title_cell, meta_cell]], colWidths=[2 * cm, 12.5 * cm, 3.5 * cm])
        header_tbl.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, brand_color),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(header_tbl)
        story.append(Spacer(1, 0.35 * cm))

        # ======= جدول اطلاعات فروشنده و خریدار =======
        def info_lines(label, lines):
            content = f"<b>{rtl(label)}</b><br/>" + "<br/>".join(lines)
            return p(content, size=9, align=TA_RIGHT)

        seller_lines = []
        if seller:
            cname = getattr(seller, 'company_name', '') or ''
            if cname:
                seller_lines.append(f"<b>{rtl(cname)}</b>")
            if getattr(seller, 'address', ''):
                seller_lines.append(f"{rtl('آدرس')}: {rtl(seller.address)}")
            phones = []
            if getattr(seller, 'phone', ''):
                phones.append(f"{rtl('تلفن')}: {seller.phone}")
            if getattr(seller, 'mobile', ''):
                phones.append(f"{rtl('موبایل')}: {seller.mobile}")
            if phones:
                seller_lines.append("  |  ".join(phones))
            nid = getattr(seller, 'national_id', '') or getattr(seller, 'tax_id', '')
            if nid:
                seller_lines.append(f"{rtl('شناسه ملی')}: {nid}")
            if getattr(seller, 'economic_code', ''):
                seller_lines.append(f"{rtl('کد اقتصادی')}: {seller.economic_code}")
            if getattr(seller, 'company_registration_number', ''):
                seller_lines.append(f"{rtl('شماره ثبت')}: {seller.company_registration_number}")

        customer = invoice_data.get('customer')
        party_lines = []
        if customer:
            party_label = "فروشنده/تامین‌کننده" if document_type == "purchase" else "مشتری"
            party_lines.append(f"<b>{rtl(customer.name)}</b>")
            party_phone = getattr(customer, 'mobile', '') or getattr(customer, 'phone', '') or ''
            if party_phone:
                party_lines.append(f"{rtl('تلفن')}: {party_phone}")
            nid = (getattr(invoice, 'buyer_national_id', '') or getattr(invoice, 'vendor_national_id', '') or '') if invoice else ''
            eco = (getattr(invoice, 'buyer_economic_code', '') or getattr(invoice, 'vendor_economic_code', '') or '') if invoice else ''
            if nid:
                party_lines.append(f"{rtl('شناسه ملی')}: {nid}")
            if eco:
                party_lines.append(f"{rtl('کد اقتصادی')}: {eco}")
            if getattr(customer, 'address', ''):
                party_lines.append(f"{rtl('آدرس')}: {rtl(customer.address)}")

        seller_block = p("<br/>".join(seller_lines) if seller_lines else rtl("—"), size=9)
        party_block = p("<br/>".join(party_lines) if party_lines else rtl("—"), size=9)

        party_header = party_label if customer else "طرف‌حساب"
        info_tbl = Table(
            [[p(f"<b>{rtl('فروشنده')}</b>", size=9, bold=True, color=brand_color),
              p(f"<b>{rtl(party_header)}</b>", size=9, bold=True, color=accent_color)],
             [seller_block, party_block]],
            colWidths=[9 * cm, 9 * cm],
        )
        info_tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.8, brand_color),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('BACKGROUND', (0, 0), (-1, 0), header_bg),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(info_tbl)
        story.append(Spacer(1, 0.35 * cm))

        # ======= جدول اقلام =======
        items = invoice_data.get('items', [])
        header_row = [rtl("جمع (تومان)"), rtl("قیمت واحد"), rtl("واحد"), rtl("تعداد"), rtl("شرح کالا / خدمت"), rtl("ردیف")]
        table_data = [header_row]
        for i, item in enumerate(items, 1):
            qty = item.quantity
            qty_str = f"{qty:,.0f}" if qty == int(qty) else f"{qty:,.3f}".rstrip('0').rstrip('.')
            table_data.append([
                f"{item.total:,.0f}",
                f"{item.unit_price:,.0f}",
                rtl(getattr(item, 'unit', '') or 'عدد'),
                qty_str,
                rtl(item.description),
                str(i),
            ])

        summary_row_count = 0
        if invoice:
            table_data.append([f"{invoice.subtotal:,.0f}", rtl("جمع جزء"), "", "", "", ""])
            summary_row_count += 1
            if invoice.is_vat_applied and invoice.vat_amount > 0:
                table_data.append([f"{invoice.vat_amount:,.0f}", rtl(f"ارزش افزوده ({invoice.vat_rate:.0f}%)"), "", "", "", ""])
                summary_row_count += 1
            table_data.append([f"{invoice.total:,.0f}", rtl("مبلغ قابل پرداخت"), "", "", "", ""])
            summary_row_count += 1

        col_widths = [2.8 * cm, 2.5 * cm, 1.4 * cm, 1.5 * cm, 7.3 * cm, 1.5 * cm]
        items_table = Table(table_data, colWidths=col_widths)
        first_sum = len(table_data) - summary_row_count
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), brand_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), self.font_name_bold),
            ('FONTNAME', (0, 1), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (4, 1), (4, first_sum - 1), 'RIGHT'),
            ('GRID', (0, 0), (-1, first_sum - 1), 0.4, colors.HexColor('#bbbbbb')),
            ('BOX', (0, 0), (-1, first_sum - 1), 0.8, brand_color),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]
        for row_idx in range(1, first_sum):
            if row_idx % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, row_idx), (-1, row_idx), row_alt))
        if summary_row_count:
            style_cmds.append(('BACKGROUND', (0, first_sum), (-1, -1), colors.HexColor('#e8f4ee')))
            style_cmds.append(('BOX', (0, first_sum), (-1, -1), 0.8, accent_color))
            for r in range(first_sum, len(table_data)):
                style_cmds.append(('SPAN', (1, r), (5, r)))
                style_cmds.append(('ALIGN', (1, r), (5, r), 'RIGHT'))
            style_cmds.append(('FONTNAME', (0, -1), (-1, -1), self.font_name_bold))
            style_cmds.append(('TEXTCOLOR', (0, -1), (-1, -1), accent_color))
        items_table.setStyle(TableStyle(style_cmds))
        story.append(items_table)
        story.append(Spacer(1, 0.4 * cm))

        if invoice and invoice.description:
            story.append(p(f"<b>{rtl('توضیحات')}:</b> {rtl(invoice.description)}", size=9))
            story.append(Spacer(1, 0.3 * cm))

        # ======= امضا =======
        story.append(Spacer(1, 1.2 * cm))
        sig_seller = p(rtl("مهر و امضای فروشنده"), size=9, align=TA_RIGHT)
        sig_buyer = p(rtl("مهر و امضای خریدار"), size=9, align=TA_RIGHT)
        sig_tbl = Table([[sig_seller, sig_buyer]], colWidths=[9 * cm, 9 * cm])
        sig_tbl.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.HexColor('#888888')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(sig_tbl)

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
