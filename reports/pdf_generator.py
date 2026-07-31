# reports/pdf_generator.py

from datetime import datetime
from typing import Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import matplotlib.pyplot as plt
import pandas as pd
from core.accounting_engine import AccountingEngine

class PDFReportGenerator:
    def __init__(self, engine: AccountingEngine) -> None:
        self.engine = engine
    
    def create_trial_balance_pdf(self, filename: str = "trial_balance.pdf", user_id: Optional[int] = None) -> str:
        """ایجاد گزارش تراز آزمایشی PDF"""
        doc = SimpleDocTemplate(filename, pagesize=A4)
        styles = getSampleStyleSheet()
        
        # ایجاد استایل فارسی (در صورت نبود فونت، از استایل پیش‌فرض استفاده می‌کند)
        try:
            pdfmetrics.registerFont(TTFont('Vazir', 'static/Vazir.ttf'))
            persian_style = ParagraphStyle('PersianStyle', parent=styles['Normal'], fontName='Vazir', fontSize=10, encoding='utf-8')
            title_style = ParagraphStyle('TitleStyle', parent=styles['Title'], fontName='Vazir', fontSize=16, encoding='utf-8')
        except:
            persian_style = styles['Normal']
            title_style = styles['Title']
        
        story = []
        
        # عنوان
        story.append(Paragraph("گزارش تراز آزمایشی", title_style))
        story.append(Paragraph(f"تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", persian_style))
        story.append(Spacer(1, 0.5*cm))
        
        # دریافت داده‌ها
        balances = self.engine.get_trial_balance(user_id=user_id)

        # آماده سازی جدول
        data = [["کد حساب", "نام حساب", "بدهکار (تومان)", "بستانکار (تومان)"]]
        total_debit = 0
        total_credit = 0
        
        for row in balances:
            if row.total_debit != 0 or row.total_credit != 0:
                data.append([
                    row.code,
                    row.name,
                    f"{row.total_debit:,.0f}",
                    f"{row.total_credit:,.0f}"
                ])
                total_debit += row.total_debit
                total_credit += row.total_credit
        
        # جمع کل
        data.append(["", "جمع کل", f"{total_debit:,.0f}", f"{total_credit:,.0f}"])
        
        table = Table(data, colWidths=[2*cm, 5*cm, 3.5*cm, 3.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ]))
        
        story.append(table)
        doc.build(story)
        print(f"✅ گزارش PDF در {filename} ذخیره شد.")
        return filename
    
    def create_chart(self, filename: str = "chart.png", user_id: Optional[int] = None) -> str:
        """ایجاد نمودار میله‌ای از مانده حساب‌ها"""
        balances = self.engine.get_trial_balance(user_id=user_id)
        
        # آماده سازی داده
        accounts = []
        debits = []
        credits = []
        
        for row in balances:
            if row.total_debit != 0 or row.total_credit != 0:
                accounts.append(row.name)
                debits.append(row.total_debit)
                credits.append(row.total_credit)
        
        # ایجاد نمودار
        fig, ax = plt.subplots(figsize=(12, 6))
        
        x = range(len(accounts))
        width = 0.35
        
        ax.bar([i - width/2 for i in x], debits, width, label='بدهکار', color='skyblue')
        ax.bar([i + width/2 for i in x], credits, width, label='بستانکار', color='lightcoral')
        
        ax.set_xlabel('حساب‌ها')
        ax.set_ylabel('مبلغ (تومان)')
        ax.set_title('نمودار مانده حساب‌ها')
        ax.set_xticks(x)
        ax.set_xticklabels(accounts, rotation=45, ha='right')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"✅ نمودار در {filename} ذخیره شد.")
        return filename


# تست سریع
if __name__ == "__main__":
    engine = AccountingEngine()
    reporter = PDFReportGenerator(engine)
    
    print("📊 تولید گزارش و نمودار...")
    reporter.create_trial_balance_pdf("trial_balance.pdf")
    reporter.create_chart("chart.png")
    print("✅ گزارش‌ها با موفقیت تولید شدند.")