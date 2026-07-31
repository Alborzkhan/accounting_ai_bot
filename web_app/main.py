# web_app/main.py

import os
import asyncio
import html
import json
import logging
import secrets
import jdatetime
from types import SimpleNamespace
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import Optional
import shutil

from core.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from core.accounting_engine import AccountingEngine
from core.text_command_handler import TextCommandHandler
from core.auth import AuthManager
from core.license_manager import LicenseManager
from core.payment_gateway import PaymentGateway
from core.rate_limiter import rate_limit
from core.invoice_generator import InvoiceGenerator
from core.inventory_reconciler import InventoryReconciler
from core.platform_settings import PlatformSettingsManager
from core.building_manager import BuildingManager
from core.sms_service import test_sms_connection
from core.ai_voucher_fallback import try_ai_voucher
from core.dashboard_service import DashboardService
from core.financial_reports import FinancialReports
from core.budget_manager import BudgetManager
from core.recurring_service import RecurringVoucherService
from core.audit import AuditService
from core.data_export import DataExporter
from reports.invoice_pdf import InvoicePDF
from ai_handlers.voice_to_accounting import VoiceToAccounting
from ai_handlers.llm_processor import LLMProcessor, SUPPORTED_PROVIDERS
from database.models import ProformaInvoice, PurchaseInvoice
from config import ALLOWED_ORIGINS

app = FastAPI(title="حسابدار هوشمند | نارین")

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


# ========== HEALTH CHECK ==========

@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    from fastapi.responses import FileResponse as FR
    path = os.path.join("static", "favicon.ico")
    if os.path.exists(path):
        return FR(path)
    return Response(status_code=204)


@app.get("/health")
async def health_check() -> dict:
    """بررسی سلامت سرویس و اتصال به دیتابیس."""
    import time
    start = time.time()
    services = {}
    all_ok = True

    # بررسی دیتابیس
    try:
        from database.models import Account
        session = engine.Session()
        session.query(Account).first()
        session.close()
        services["database"] = "ok"
    except Exception as e:
        services["database"] = f"error: {e}"
        all_ok = False

    services["uptime_seconds"] = round(time.time() - start, 2)
    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={"status": "ok" if all_ok else "degraded", "services": services},
        status_code=status_code,
    )


# ========== MOUNT STATIC FILES ==========
os.makedirs("static", exist_ok=True)

# ایجاد favicon placeholder
favicon_path = os.path.join("static", "favicon.ico")
if not os.path.exists(favicon_path):
    try:
        with open(favicon_path, "wb") as f:
            # یک favicon ساده (ICO خالی)
            f.write(b'\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x20\x00\x68\x04\x00\x00\x16\x00\x00\x00')
    except Exception:
        pass

app.mount("/static", StaticFiles(directory="static"), name="static")

# ایجاد پوشه‌ها
os.makedirs("web_app/templates", exist_ok=True)
os.makedirs("voice_temp", exist_ok=True)

# موتورها
engine = AccountingEngine()
text_handler = TextCommandHandler(engine)
auth_manager = AuthManager()
license_manager = LicenseManager()
payment_gateway = PaymentGateway()
invoice_generator = InvoiceGenerator()
inventory_reconciler = InventoryReconciler()
from core.notifications import NotificationService
notifier = NotificationService()
platform_settings = PlatformSettingsManager()
building_manager = BuildingManager()
invoice_pdf_maker = InvoicePDF()
llm_processor = LLMProcessor()
voice_handler = VoiceToAccounting(model_size="base")
dashboard_service = DashboardService()
financial_reports = FinancialReports()
budget_manager = BudgetManager()
recurring_voucher_service = RecurringVoucherService()
audit_service = AuditService()
data_exporter = DataExporter()
ALLOWED_BUSINESS_TYPES = {"بازرگانی", "تولیدی", "خدماتی", "پیمانکاری", "مدیریت آپارتمان‌ها"}


def get_user_id(request: Request) -> Optional[int]:
    token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if token:
        return auth_manager.validate_session(token)
    return None


def _parse_report_date(value: str, end_of_day: bool = False) -> Optional[datetime]:
    """ورودی تاریخ گزارش را می‌پذیرد، چه شمسی (1404/04/01) و چه میلادی (2026-06-21)."""
    if not value:
        return None
    value = value.strip()
    dt = None
    try:
        dt = jdatetime.datetime.strptime(value, "%Y/%m/%d").togregorian()
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt

@app.get("/auth/me")
async def auth_me(request: Request) -> dict:
    user_id = get_user_id(request)
    return {"logged_in": bool(user_id), "user_id": user_id}


@app.get("/platform-info")
async def platform_info() -> dict:
    """اطلاعات عمومی پلتفرم (لوگو، اطلاعات پشتیبانی) - بدون نیاز به ورود."""
    settings = platform_settings.get_all()
    logo_path = settings.get("platform_logo_path", "")
    return {
        "logo_url": ("/" + logo_path.replace("\\", "/")) if logo_path else "",
        "support_technical_phone": settings.get("support_technical_phone", ""),
        "support_technical_telegram": settings.get("support_technical_telegram", ""),
        "support_sales_phone": settings.get("support_sales_phone", ""),
        "support_sales_telegram": settings.get("support_sales_telegram", ""),
    }

# پلن‌های قیمتی (برای شیت «اشتراک من» داخل مینی‌اپ - بدون نویگیشن واقعی صفحه)
@app.get("/pricing-plans-data")
async def pricing_plans_data() -> dict:
    return {"data": license_manager.get_pricing_plans()}

# سرویس وضعیت لایسنس
@app.get("/license_status")
async def license_status(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"is_valid": False, "message": "لطفاً وارد حساب خود شوید."}
    status = license_manager.check_license(user_id)
    return status

# صفحه اصلی
@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    with open("web_app/templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# ثبت سند متنی
@app.post("/create_voucher")
async def create_voucher(request: Request, description: str = Form(...),
                          income_account: Optional[str] = Form("4001"),
                          expense_account: Optional[str] = Form("5601")) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    rate_limit(f"voucher:{user_id}", max_requests=30, window_seconds=60)
    if not description or len(description.strip()) < 3 or len(description) > 500:
        return {"success": False, "message": "متن سند باید بین ۳ تا ۵۰۰ کاراکتر باشد."}
    license_status = license_manager.can_create_voucher(user_id)
    if not license_status["allowed"]:
        return {"success": False, "message": license_status["message"]}
    try:
        result = text_handler.parse_and_create_voucher(description, user_id=user_id,
                                                        income_account=income_account,
                                                        expense_account=expense_account)
        if not result["success"]:
            ai_result = try_ai_voucher(engine, description, user_id)
            if ai_result.get("success"):
                return {"success": True, "message": ai_result["message"]}
        return {"success": result["success"], "message": result["message"]}
    except Exception:
        logger.exception("create_voucher failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در ثبت سند. لطفاً دوباره تلاش کنید."}

# پردازش ویس
@app.post("/process_voice")
async def process_voice(request: Request, voice: UploadFile = File(...)) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    rate_limit(f"voice:{user_id}", max_requests=15, window_seconds=60)
    license_status = license_manager.can_create_voucher(user_id)
    if not license_status["allowed"]:
        return {"success": False, "message": license_status["message"]}
    try:
        safe_name = f"{user_id}_{secrets.token_hex(8)}.webm"
        temp_path = os.path.join("voice_temp", safe_name)
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(voice.file, buffer)

        try:
            data, transcript = await asyncio.to_thread(voice_handler.voice_to_voucher, temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        if data["type"] and data["amount"] > 0:
            entry_id = engine.create_voucher(
                date=datetime.now(),
                description=data["description"],
                lines=[
                    (data["debit_account"], data["amount"], 'debit'),
                    (data["credit_account"], data["amount"], 'credit')
                ],
                user_id=user_id
            )
            return {
                "success": True,
                "message": f"سند شماره {entry_id} ثبت شد",
                "amount": data["amount"],
                "type": data["type"]
            }

        ai_result = try_ai_voucher(engine, transcript, user_id)
        if ai_result.get("success"):
            return {
                "success": True,
                "message": ai_result["message"],
                "amount": ai_result["amount"],
                "type": ai_result["type"],
            }
        return {"success": False, "message": "اطلاعات ناقص است. لطفاً واضح‌تر صحبت کنید."}
    except Exception:
        logger.exception("process_voice failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در پردازش صدا. لطفاً دوباره تلاش کنید."}

# تراز آزمایشی
@app.get("/notifications/check")
async def notifications_check(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"messages": []}
    messages = []
    for msg in (
        notifier.check_renewal_reminder(user_id),
        notifier.get_voucher_limit_warning(user_id),
        notifier.get_inventory_deficit_reminder(user_id),
    ):
        if msg:
            messages.append(msg)
    return {"messages": messages}


CASH_ACCOUNTS = {
    "1001": "صندوق",
    "1002": "بانک",
    "1003": "تنخواه‌گردان",
}


@app.get("/bank_accounts")
async def list_bank_accounts(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    from database.models import BankAccount
    session = engine.Session()
    try:
        rows = session.query(BankAccount).filter_by(user_id=user_id).order_by(BankAccount.is_default.desc(), BankAccount.id).all()
        return {"success": True, "data": [{
            "id": r.id, "display_name": r.display_name, "account_type": r.account_type,
            "gl_code": r.gl_code, "bank_name": r.bank_name or "", "account_number": r.account_number or "",
            "iban": r.iban or "", "card_number": r.card_number or "", "is_default": r.is_default,
        } for r in rows]}
    finally:
        session.close()


@app.post("/bank_account")
async def add_bank_account(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    p = await request.json()
    display_name = (p.get("display_name") or "").strip()
    if not display_name:
        return {"success": False, "message": "نام نمایشی حساب را وارد کنید."}
    from database.models import BankAccount
    session = engine.Session()
    try:
        acc_type = p.get("account_type", "bank")
        gl_map = {"bank": "1002", "cash": "1001", "petty_cash": "1003"}
        gl_code = p.get("gl_code") or gl_map.get(acc_type, "1002")
        if p.get("is_default"):
            session.query(BankAccount).filter_by(user_id=user_id, account_type=acc_type).update({"is_default": False})
        row = BankAccount(
            user_id=user_id, display_name=display_name, account_type=acc_type, gl_code=gl_code,
            bank_name=p.get("bank_name") or "", account_number=p.get("account_number") or "",
            iban=p.get("iban") or "", card_number=p.get("card_number") or "",
            is_default=bool(p.get("is_default")),
        )
        session.add(row)
        session.commit()
        return {"success": True, "message": f"حساب «{display_name}» اضافه شد.", "id": row.id}
    finally:
        session.close()


@app.post("/bank_account/{account_id}/delete")
async def delete_bank_account(request: Request, account_id: int) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    from database.models import BankAccount
    session = engine.Session()
    try:
        row = session.query(BankAccount).filter_by(id=account_id, user_id=user_id).first()
        if not row:
            return {"success": False, "message": "یافت نشد."}
        session.delete(row)
        session.commit()
        return {"success": True}
    finally:
        session.close()


@app.get("/cash_balances")
async def cash_balances(request: Request) -> dict:
    """مانده‌ی فعلی صندوق، بانک و تنخواه برای کاربر جاری."""
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    balances = engine.get_trial_balance(user_id=user_id)
    data = []
    for acc in balances:
        if acc.code in CASH_ACCOUNTS:
            bal = round(acc.total_debit - acc.total_credit, 0)
            data.append({"code": acc.code, "name": CASH_ACCOUNTS[acc.code], "balance": bal})
    missing = [code for code in CASH_ACCOUNTS if not any(d["code"] == code for d in data)]
    for code in missing:
        data.append({"code": code, "name": CASH_ACCOUNTS[code], "balance": 0})
    data.sort(key=lambda x: x["code"])
    return {"success": True, "data": data}


@app.post("/cash_transaction")
async def cash_transaction(request: Request) -> dict:
    """ثبت سند ساده برای صندوق/بانک/تنخواه."""
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    payload = await request.json()
    tx_type = payload.get("type", "")
    amount = float(payload.get("amount") or 0)
    description = (payload.get("description") or "").strip()
    from_acc = payload.get("from_account", "")
    to_acc = payload.get("to_account", "")
    if amount <= 0:
        return {"success": False, "message": "مبلغ باید بیشتر از صفر باشد."}
    if not description:
        return {"success": False, "message": "شرح را وارد کنید."}
    bank_account_id = payload.get("bank_account_id")
    if bank_account_id:
        from database.models import BankAccount
        s = engine.Session()
        try:
            ba = s.query(BankAccount).filter_by(id=bank_account_id, user_id=user_id).first()
            if ba:
                to_acc = ba.gl_code
        finally:
            s.close()
    if not from_acc or not to_acc:
        return {"success": False, "message": "حساب مبدا و مقصد را انتخاب کنید."}
    try:
        entry_id = engine.create_voucher(
            date=datetime.now(),
            description=description,
            lines=[(to_acc, amount, "debit"), (from_acc, amount, "credit")],
            user_id=user_id,
        )
        return {"success": True, "message": f"سند شماره {entry_id} ثبت شد.", "entry_id": entry_id}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/trial_balance")
async def get_trial_balance(request: Request, date_from: str = "", date_to: str = "") -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"data": []}
    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to, end_of_day=True)
    balances = engine.get_trial_balance(user_id=user_id, date_from=df, date_to=dt)
    data = []
    for row in balances:
        if row.total_debit != 0 or row.total_credit != 0:
            data.append({
                "code": row.code,
                "name": row.name,
                "type": getattr(row, 'type', '') or '',
                "debit": row.total_debit,
                "credit": row.total_credit
            })
    return {"data": data}

# جزئیات تفصیلی یک حساب (آخرین گردش‌ها)
PARTY_ACCOUNT_CODES = {
    "1101": "customer", "1102": "customer", "1103": "customer", "1601": "customer",
    "2001": "vendor", "2002": "vendor",
}
INVENTORY_ACCOUNT_CODES = {"1201", "1202", "1203", "1204", "1301"}


def to_shamsi(dt) -> str:
    if not dt:
        return ""
    try:
        jd = jdatetime.datetime.fromgregorian(datetime=dt)
        return f"{jd.year}/{jd.month:02d}/{jd.day:02d}"
    except Exception:
        return dt.strftime("%Y/%m/%d")


@app.get("/sub_details")
async def sub_details(request: Request, code: str) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"items": []}
    from database.models import Account, Customer, JournalEntry, JournalLine, Vendor
    session = engine.Session()
    try:
        account = session.query(Account).filter_by(code=code).first()
        if not account:
            return {"items": []}

        if code in INVENTORY_ACCOUNT_CODES:
            from database.models import InvoiceItem, ProformaInvoice, PurchaseItem, PurchaseInvoice
            purchase_rows = session.query(PurchaseItem.description, PurchaseItem.quantity, PurchaseItem.unit).join(
                PurchaseInvoice, PurchaseItem.purchase_invoice_id == PurchaseInvoice.id
            ).filter(PurchaseInvoice.user_id == user_id).all()
            sale_rows = session.query(InvoiceItem.description, InvoiceItem.quantity, InvoiceItem.unit).join(
                ProformaInvoice, InvoiceItem.invoice_id == ProformaInvoice.id
            ).filter(ProformaInvoice.user_id == user_id, ProformaInvoice.document_type != "proforma").all()
            balances: dict = {}
            units: dict = {}
            for name, qty, unit in purchase_rows:
                if name:
                    balances[name] = balances.get(name, 0) + float(qty or 0)
                    units[name] = unit or "عدد"
            for name, qty, unit in sale_rows:
                if name:
                    balances[name] = balances.get(name, 0) - float(qty or 0)
                    if name not in units:
                        units[name] = unit or "عدد"
            def _fmt_qty(q):
                r = round(q, 3)
                return f"{int(r):,}" if r == int(r) else f"{r:,.3f}".rstrip('0').rstrip('.')
            items = [
                {"name": name, "qty": round(qty, 3), "unit": units.get(name, "عدد"),
                 "value": f"{_fmt_qty(qty)} {units.get(name, 'عدد')}"}
                for name, qty in sorted(balances.items(), key=lambda x: x[0])
            ]
            return {"is_product_list": True, "items": items}

        party_type = PARTY_ACCOUNT_CODES.get(code)
        if party_type:
            party_field = JournalEntry.customer_id if party_type == "customer" else JournalEntry.vendor_id
            rows = session.query(JournalLine, JournalEntry).join(
                JournalEntry, JournalEntry.id == JournalLine.entry_id
            ).filter(
                JournalLine.account_id == account.id,
                JournalEntry.user_id == user_id,
                party_field.isnot(None),
            ).all()
            balances: dict = {}
            for line, entry in rows:
                party_id = entry.customer_id if party_type == "customer" else entry.vendor_id
                delta = line.amount if line.side == "debit" else -line.amount
                balances[party_id] = balances.get(party_id, 0) + delta
            if balances:
                model = Customer if party_type == "customer" else Vendor
                parties = session.query(model).filter(model.id.in_(balances.keys())).all()
                items = [
                    {"id": p.id, "name": p.name, "value": f"{balances[p.id]:,.0f}"}
                    for p in parties if abs(balances[p.id]) > 0.01
                ]
                items.sort(key=lambda x: -abs(float(x["value"].replace(",", ""))))
                return {"is_party_list": True, "party_type": party_type, "items": items}

        rows = session.query(JournalLine, JournalEntry).join(
            JournalEntry, JournalEntry.id == JournalLine.entry_id
        ).filter(
            JournalLine.account_id == account.id,
            JournalEntry.user_id == user_id,
        ).order_by(JournalEntry.date.desc()).limit(30).all()
        items = []
        for line, entry in rows:
            sign = "+" if line.side == "debit" else "-"
            name = f"{to_shamsi(entry.date)} — {line.description or entry.description or ''}"
            items.append({"name": name, "value": f"{sign}{line.amount:,.0f}"})
        return {"items": items}
    finally:
        session.close()


@app.get("/party_statement")
async def party_statement(request: Request, party_id: int, party_type: str) -> dict:
    """صورت‌حساب کامل یک طرف‌حساب (مشتری/فروشنده) با مانده در گردش، به فرمت استاندارد حسابداری."""
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    if party_type not in ("customer", "vendor"):
        return {"success": False, "message": "نوع طرف‌حساب نامعتبر است."}
    from database.models import Account, Customer, JournalEntry, JournalLine, Vendor

    session = engine.Session()
    try:
        model = Customer if party_type == "customer" else Vendor
        party = session.query(model).filter_by(id=party_id, user_id=user_id).first()
        if not party:
            return {"success": False, "message": "طرف‌حساب یافت نشد."}

        account_codes = [c for c, t in PARTY_ACCOUNT_CODES.items() if t == party_type]
        party_field = JournalEntry.customer_id if party_type == "customer" else JournalEntry.vendor_id
        rows = session.query(JournalLine, JournalEntry).join(
            JournalEntry, JournalEntry.id == JournalLine.entry_id
        ).join(
            Account, Account.id == JournalLine.account_id
        ).filter(
            Account.code.in_(account_codes),
            JournalEntry.user_id == user_id,
            party_field == party_id,
        ).order_by(JournalEntry.date.asc(), JournalEntry.id.asc()).all()

        rows_out = []
        balance = 0.0
        total_debit = 0.0
        total_credit = 0.0
        for line, entry in rows:
            debit = line.amount if line.side == "debit" else 0
            credit = line.amount if line.side == "credit" else 0
            balance += debit - credit
            total_debit += debit
            total_credit += credit
            rows_out.append({
                "date": to_shamsi(entry.date),
                "description": line.description or entry.description or "",
                "debit": debit,
                "credit": credit,
                "balance": balance,
            })

        return {
            "success": True,
            "party_name": party.name,
            "party_mobile": getattr(party, "mobile", "") or getattr(party, "phone", "") or "",
            "rows": rows_out,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "closing_balance": balance,
        }
    finally:
        session.close()


@app.get("/product_statement")
async def product_statement(request: Request, product_name: str) -> dict:
    """گردش کالا: تمام خریدها و فروش‌های یک محصول خاص برای این کاربر، با مانده‌ی کمّی در گردش."""
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    from database.models import InvoiceItem, ProformaInvoice, PurchaseItem, PurchaseInvoice
    session = engine.Session()
    try:
        purchases = session.query(PurchaseItem, PurchaseInvoice).join(
            PurchaseInvoice, PurchaseItem.purchase_invoice_id == PurchaseInvoice.id
        ).filter(
            PurchaseInvoice.user_id == user_id,
            PurchaseItem.description == product_name,
        ).order_by(PurchaseInvoice.date.asc()).all()

        sales = session.query(InvoiceItem, ProformaInvoice).join(
            ProformaInvoice, InvoiceItem.invoice_id == ProformaInvoice.id
        ).filter(
            ProformaInvoice.user_id == user_id,
            ProformaInvoice.document_type != "proforma",
            InvoiceItem.description == product_name,
        ).order_by(ProformaInvoice.date.asc()).all()

        events = []
        for item, inv in purchases:
            events.append({"date": inv.date, "type": "خرید",
                           "description": inv.description or "",
                           "qty_in": float(item.quantity or 0), "qty_out": 0,
                           "unit": item.unit or "عدد", "unit_price": item.unit_price or 0})
        for item, inv in sales:
            events.append({"date": inv.date, "type": "فروش",
                           "description": getattr(inv, 'description', '') or "",
                           "qty_in": 0, "qty_out": float(item.quantity or 0),
                           "unit": item.unit or "عدد", "unit_price": item.unit_price or 0})

        events.sort(key=lambda e: (e["date"] or datetime.min))

        rows_out = []
        balance = 0.0
        total_in = total_out = 0.0
        for e in events:
            balance += e["qty_in"] - e["qty_out"]
            total_in += e["qty_in"]
            total_out += e["qty_out"]
            rows_out.append({
                "date": to_shamsi(e["date"]),
                "type": e["type"],
                "description": e["description"] or "",
                "qty_in": e["qty_in"],
                "qty_out": e["qty_out"],
                "unit": e["unit"],
                "unit_price": e["unit_price"],
                "balance": round(balance, 3),
            })
        unit = events[0]["unit"] if events else "عدد"
        return {
            "success": True, "product_name": product_name,
            "rows": rows_out, "unit": unit,
            "total_in": round(total_in, 3), "total_out": round(total_out, 3),
            "closing_balance": round(balance, 3),
        }
    finally:
        session.close()


# ========== NEW FEATURES: DASHBOARD, REPORTS, BUDGET, RECURRING, AUDIT, EXPORT ==========

@app.get("/dashboard/kpi")
async def dashboard_kpi(request: Request) -> dict:
    """KPI summary برای کارت بالای داشبورد."""
    user_id = get_user_id(request)
    if not user_id:
        return {}
    return dashboard_service.get_kpi_summary(user_id)

@app.get("/dashboard/monthly")
async def dashboard_monthly(request: Request, months: int = 12) -> dict:
    """داده‌های ماهانه درآمد/هزینه/سود برای نمودار خطی."""
    user_id = get_user_id(request)
    if not user_id:
        return {"labels": [], "income": [], "expense": [], "profit": []}
    return dashboard_service.get_monthly_income_expense(user_id, months)

@app.get("/dashboard/expenses")
async def dashboard_expenses(request: Request, months: int = 3) -> dict:
    """توزیع هزینه‌ها برای نمودار دایره‌ای."""
    user_id = get_user_id(request)
    if not user_id:
        return {"data": []}
    data = dashboard_service.get_expense_breakdown(user_id, months)
    return {"data": data}

@app.get("/dashboard/cashflow")
async def dashboard_cashflow(request: Request, days: int = 30) -> dict:
    """گردش نقدی روزانه."""
    user_id = get_user_id(request)
    if not user_id:
        return {"labels": [], "inflow": [], "outflow": [], "balance": []}
    return dashboard_service.get_cashflow(user_id, days)

@app.get("/dashboard/top-customers")
async def dashboard_top_customers(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"data": []}
    return {"data": dashboard_service.get_top_customers(user_id)}

@app.get("/dashboard/top-vendors")
async def dashboard_top_vendors(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"data": []}
    return {"data": dashboard_service.get_top_vendors(user_id)}

# ---- گزارش‌های مالی ----
@app.get("/reports/profit-loss")
async def report_profit_loss(request: Request, date_from: str = "", date_to: str = "") -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to, end_of_day=True)
    result = financial_reports.profit_loss(user_id, df, dt)
    return {"success": True, "data": result}

@app.get("/reports/balance-sheet")
async def report_balance_sheet(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    result = financial_reports.balance_sheet(user_id)
    return {"success": True, "data": result}

@app.get("/reports/account-statement")
async def report_account_statement(request: Request, code: str,
                                    date_from: str = "", date_to: str = "") -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to, end_of_day=True)
    return financial_reports.account_statement(user_id, code, df, dt)

@app.get("/reports/vat")
async def report_vat(request: Request, date_from: str = "", date_to: str = "") -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to, end_of_day=True)
    result = financial_reports.vat_report(user_id, df, dt)
    return {"success": True, "data": result}

# ---- بودجه ----
@app.get("/budgets")
async def get_budgets(request: Request, year: int = 0, month: int = 0) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    from datetime import datetime as dt
    y = year or dt.now().year
    m = month or dt.now().month
    data = budget_manager.get_budgets(user_id, y, m)
    return {"success": True, "data": data}

@app.post("/budgets/set")
async def set_budget(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    p = await request.json()
    return budget_manager.set_budget(
        user_id=user_id,
        account_code=p.get("account_code", ""),
        amount=float(p.get("amount", 0)),
        budget_type=p.get("budget_type", "monthly"),
        period_year=p.get("period_year"),
        period_month=p.get("period_month"),
        note=p.get("note", ""),
    )

@app.get("/budgets/vs-actual")
async def budget_vs_actual(request: Request, year: int = 0, month: int = 0) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    from datetime import datetime as dt
    y = year or dt.now().year
    m = month or dt.now().month
    data = budget_manager.get_budget_vs_actual(user_id, y, m)
    return {"success": True, "data": data}

@app.get("/budgets/alerts")
async def budget_alerts(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    data = budget_manager.get_alerts(user_id)
    return {"success": True, "data": data}

# ---- اسناد دوره‌ای ----
@app.get("/recurring")
async def get_recurring(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    data = recurring_voucher_service.get_all(user_id)
    return {"success": True, "data": data}

@app.post("/recurring/create")
async def create_recurring(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    p = await request.json()
    return recurring_voucher_service.create(
        user_id=user_id,
        title=p.get("title", ""),
        description=p.get("description", ""),
        frequency=p.get("frequency", "monthly"),
        debit_code=p.get("debit_code", ""),
        credit_code=p.get("credit_code", ""),
        amount=float(p.get("amount", 0)),
        next_run=p.get("next_run"),
        end_date=p.get("end_date"),
    )

@app.post("/recurring/{rec_id}/toggle")
async def toggle_recurring(request: Request, rec_id: int) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return recurring_voucher_service.toggle_active(rec_id, user_id)

@app.post("/recurring/{rec_id}/delete")
async def delete_recurring(request: Request, rec_id: int) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return recurring_voucher_service.delete(rec_id, user_id)

# ---- خروجی Excel/CSV ----
@app.get("/export/journal/csv")
async def export_journal_csv(request: Request, date_from: str = "", date_to: str = "") -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to, end_of_day=True)
    csv_content = data_exporter.export_journal_csv(user_id, df, dt)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=journal_entries.csv"},
    )

@app.get("/export/journal/excel")
async def export_journal_excel(request: Request, date_from: str = "", date_to: str = "") -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to, end_of_day=True)
    excel_bytes = data_exporter.export_journal_excel(user_id, df, dt)
    from fastapi.responses import StreamingResponse
    import io
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=journal_entries.xlsx"},
    )

@app.get("/export/customers/csv")
async def export_customers_csv(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    csv_content = data_exporter.export_customers_csv(user_id)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=customers.csv"},
    )

@app.get("/export/vendors/csv")
async def export_vendors_csv(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    csv_content = data_exporter.export_vendors_csv(user_id)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=vendors.csv"},
    )

@app.get("/export/trial-balance/csv")
async def export_trial_balance_csv(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    csv_content = data_exporter.export_trial_balance_csv(user_id)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=trial_balance.csv"},
    )


# تحلیل هوشمند یک حساب
@app.get("/ai_query")
async def ai_query(request: Request, code: str) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"explanation": "ابتدا وارد شوید."}
    balances = engine.get_trial_balance(user_id=user_id)
    row = next((r for r in balances if r.code == code), None)
    if not row:
        return {"explanation": "حسابی با این کد یافت نشد."}
    balance_text = (
        f"حساب «{row.name}» (کد {code}): گردش بدهکار {row.total_debit:,.0f} تومان، "
        f"گردش بستانکار {row.total_credit:,.0f} تومان، مانده {row.total_debit - row.total_credit:,.0f} تومان."
    )
    result = LLMProcessor().answer_account_query(balance_text)
    if result.get("success") and result.get("explanation"):
        return {"explanation": result["explanation"]}
    return {"explanation": f"{balance_text} (برای تحلیل هوشمند، سرویس هوش مصنوعی را در پنل ادمین تنظیم کنید.)"}


# لیست آخرین اسناد
@app.get("/vouchers")
async def get_vouchers(request: Request, limit: int = 20) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"data": []}
    session = engine.Session()
    try:
        from database.models import JournalEntry
        entries = session.query(JournalEntry).filter(
            JournalEntry.user_id == user_id
        ).order_by(
            JournalEntry.id.desc()
        ).limit(limit).all()
        data = []
        for e in entries:
            data.append({
                "id": e.id,
                "date": e.date.strftime("%Y-%m-%d %H:%M:%S"),
                "description": e.description
            })
        return {"data": data}
    finally:
        session.close()

# صفحه قیمت‌ها
@app.get("/pricing", response_class=HTMLResponse)
async def pricing() -> HTMLResponse:
    plans = license_manager.get_pricing_plans()
    html_content = """
    <!DOCTYPE html>
    <html dir="rtl" lang="fa">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>خرید اشتراک | حسابدار هوشمند</title>
        <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: inherit; }
            body {
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma, sans-serif;
                background: linear-gradient(135deg, #0f2b3d 0%, #1a4a6f 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 500px; margin: 0 auto; }
            .card {
                background: white;
                border-radius: 28px;
                padding: 20px;
                margin-bottom: 16px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            }
            .card h3 { color: #1a4a6f; margin-bottom: 12px; }
            .price { font-size: 24px; font-weight: bold; color: #1a4a6f; }
            button {
                background: linear-gradient(135deg, #1a4a6f 0%, #0f2b3d 100%);
                color: white;
                border: none;
                padding: 12px;
                border-radius: 40px;
                width: 100%;
                font-size: 14px;
                font-weight: bold;
                margin-top: 12px;
                cursor: pointer;
            }
            .back-btn { background: #6c757d; margin-bottom: 16px; }
            .discount-input {
                width: 100%; padding: 10px 14px; border-radius: 12px; border: 1px solid #ccc;
                font-size: 13px; margin-bottom: 6px; box-sizing: border-box; font-family: inherit;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <button class="back-btn" onclick="location.href='/'">← بازگشت به صفحه اصلی</button>
            <div class="card">
                <h3>🎁 پلن آزمایشی</h3>
                <div class="price">رایگان</div>
                <p>۵۰ سند اول رایگان - ۳۰ روز</p>
                <button onclick="alert('پلن آزمایشی فعال است')">فعال کردن</button>
            </div>
            <div class="card">
                <h3>🏷️ کد تخفیف (اختیاری)</h3>
                <input id="discountCodeInput" class="discount-input" type="text" placeholder="کد تخفیف خود را وارد کنید" dir="ltr">
            </div>
    """
    for key, plan in plans.items():
        if key != "free_trial":
            html_content += f"""
            <div class="card">
                <h3>💰 {plan['name']}</h3>
                <div class="price">{plan['price']:,} <small>تومان</small></div>
                <p>{plan['description']}</p>
                <button onclick="payPlan('{key}')">خرید اشتراک</button>
            </div>
            """
    html_content += """
        </div>
        <script>
            function payPlan(planKey) {
                const code = document.getElementById('discountCodeInput').value.trim();
                const url = code ? `/payment/${planKey}?discount_code=${encodeURIComponent(code)}` : `/payment/${planKey}`;
                location.href = url;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ========== PAYMENT ENDPOINTS ==========

@app.get("/payment/{plan_type}")
async def start_payment(request: Request, plan_type: str, discount_code: str = ""):
    user_id = get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/")
    plans = license_manager.get_pricing_plans()
    plan = plans.get(plan_type)
    if not plan or plan_type == "free_trial":
        return HTMLResponse("<h2>پلن نامعتبر است.</h2>", status_code=400)
    rate_limit(f"payment:{user_id}", max_requests=10, window_seconds=300)

    final_price = plan["price"]
    applied_code = ""
    if discount_code:
        discount_result = license_manager.validate_and_apply_discount(discount_code.strip(), plan_type, plan["price"])
        if not discount_result["success"]:
            return HTMLResponse(f"<h2>کد تخفیف نامعتبر است</h2><p>{html.escape(discount_result['message'])}</p><a href='/pricing'>بازگشت</a>", status_code=400)
        final_price = discount_result["final_price"]
        applied_code = discount_code.strip()

    try:
        result = payment_gateway.create_payment_request(user_id, final_price, plan_type, discount_code=applied_code)
    except Exception:
        logger.exception("create_payment_request failed for user_id=%s plan=%s", user_id, plan_type)
        return HTMLResponse("<h2>خطا در شروع پرداخت. لطفاً بعداً تلاش کنید.</h2>", status_code=502)
    if result["success"]:
        return RedirectResponse(url=result["payment_url"])
    logger.error("payment request failed for user_id=%s: %s", user_id, result["message"])
    return HTMLResponse(f"<h2>خطا در شروع پرداخت</h2><p>{html.escape(result['message'])}</p>", status_code=502)


@app.get("/verify_payment")
async def verify_payment_callback(Authority: str = "", Status: str = ""):
    try:
        result = payment_gateway.verify_payment(authority=Authority, status=Status)
    except Exception:
        logger.exception("verify_payment failed for authority=%s", Authority)
        return HTMLResponse("<h2>خطا در تایید پرداخت. با پشتیبانی تماس بگیرید.</h2>", status_code=502)
    if result["success"]:
        return HTMLResponse(
            f"<h2>پرداخت موفق ✅</h2>"
            f"<p>کد پیگیری: {html.escape(result['ref_id'])}</p>"
            f"<p>کلید لایسنس: {html.escape(result['license_key'])}</p>"
            f"<a href='/'>بازگشت به صفحه اصلی</a>"
        )
    return HTMLResponse(
        f"<h2>پرداخت ناموفق ❌</h2><p>{html.escape(result['message'])}</p><a href='/'>بازگشت</a>",
        status_code=400,
    )


# ========== AUTH ENDPOINTS ==========

@app.post("/auth/request-otp")
async def request_otp(request: Request, mobile: str = Form(...)) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    rate_limit(f"otp_req_ip:{client_ip}", max_requests=10, window_seconds=600)
    result = auth_manager.request_otp(mobile)
    payload = {"success": result["success"], "message": result["message"]}
    if "dev_code" in result:
        payload["dev_code"] = result["dev_code"]
    return JSONResponse(payload)


@app.post("/auth/verify-otp")
async def verify_otp(request: Request, mobile: str = Form(...), code: str = Form(...), name: Optional[str] = Form("")) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    rate_limit(f"otp_verify_ip:{client_ip}", max_requests=20, window_seconds=600)
    result = auth_manager.verify_otp(mobile, code, name or "")
    if result["success"]:
        resp = JSONResponse({"success": True, "message": result["message"], "user_id": result["user_id"], "is_new": result.get("is_new", False)})
        resp.set_cookie(key="auth_token", value=result["token"], httponly=True, samesite="lax", path="/")
        return resp
    return JSONResponse({"success": False, "message": result["message"]})


@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/")
    resp.set_cookie(key="auth_token", value="", expires=0, path="/")
    return resp


# ========== PROFILE / SETTINGS ENDPOINTS ==========

@app.get("/profile/me")
async def profile_me(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    profile = auth_manager.get_user_profile(user_id)
    if not profile:
        return {"success": False, "message": "پروفایل یافت نشد."}
    return {"success": True, "profile": profile}


@app.post("/profile/update")
async def profile_update(
    request: Request,
    name: Optional[str] = Form(None),
    business_name: Optional[str] = Form(None),
    business_type: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    phone_office: Optional[str] = Form(None),
    phone_mobile: Optional[str] = Form(None),
    economic_code: Optional[str] = Form(None),
    national_id: Optional[str] = Form(None),
    company_registration_number: Optional[str] = Form(None),
) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    if business_type is not None and business_type != "" and business_type not in ALLOWED_BUSINESS_TYPES:
        return {"success": False, "message": "نوع کسب‌وکار نامعتبر است."}
    fields = {
        "name": name, "business_name": business_name, "business_type": business_type,
        "address": address, "phone_office": phone_office, "phone_mobile": phone_mobile,
        "economic_code": economic_code, "national_id": national_id,
        "company_registration_number": company_registration_number,
    }
    updates = {k: v for k, v in fields.items() if v is not None}
    result = auth_manager.update_user_profile(user_id, **updates)
    return result


@app.post("/profile/logo")
async def profile_logo(request: Request, logo: UploadFile = File(...)) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    ext = os.path.splitext(logo.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return {"success": False, "message": "فرمت تصویر باید png، jpg یا webp باشد."}
    logos_dir = os.path.join("static", "logos")
    os.makedirs(logos_dir, exist_ok=True)
    dest_path = os.path.join(logos_dir, f"user_{user_id}{ext}")
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(logo.file, buffer)
    except Exception:
        logger.exception("profile_logo upload failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در ذخیره لوگو."}
    auth_manager.update_user_profile(user_id, logo_path=dest_path)
    return {"success": True, "message": "لوگو با موفقیت ذخیره شد.", "logo_path": "/" + dest_path.replace("\\", "/")}


@app.post("/profile/classify-business")
async def profile_classify_business(request: Request, description: str = Form(...)) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    rate_limit(f"classify:{user_id}", max_requests=10, window_seconds=300)
    if not description or len(description.strip()) < 5:
        return {"success": False, "message": "لطفاً کسب‌وکار خود را کمی واضح‌تر توضیح دهید."}
    try:
        result = llm_processor.classify_business_type(description.strip())
    except Exception:
        logger.exception("classify_business_type failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در تشخیص نوع کسب‌وکار."}
    return result


# ========== INVOICE ENDPOINTS (تشخیص هوشمند از متن/صدا) ==========

@app.post("/invoice/parse")
async def invoice_parse(request: Request, text: str = Form(...)) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    rate_limit(f"invoice_parse:{user_id}", max_requests=20, window_seconds=300)
    if not text or len(text.strip()) < 5:
        return {"success": False, "message": "لطفاً فاکتور را کمی واضح‌تر توضیح دهید."}
    try:
        result = llm_processor.extract_invoice(text.strip())
    except Exception:
        logger.exception("extract_invoice failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در تشخیص اطلاعات فاکتور."}
    return result


@app.post("/invoice/parse-voice")
async def invoice_parse_voice(request: Request, voice: UploadFile = File(...)) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    rate_limit(f"invoice_parse_voice:{user_id}", max_requests=15, window_seconds=300)
    safe_name = f"inv_{user_id}_{secrets.token_hex(8)}.webm"
    temp_path = os.path.join("voice_temp", safe_name)
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(voice.file, buffer)
        transcript = voice_handler.transcribe_voice(temp_path)
        result = llm_processor.extract_invoice(transcript)
        result["transcript"] = transcript
        return result
    except Exception:
        logger.exception("invoice_parse_voice failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در پردازش صدا."}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/invoice/confirm")
async def invoice_confirm(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    rate_limit(f"invoice_confirm:{user_id}", max_requests=20, window_seconds=300)
    try:
        payload = await request.json()
    except Exception:
        return {"success": False, "message": "درخواست نامعتبر است."}

    document_type = payload.get("document_type") if payload.get("document_type") in ("sale", "proforma", "purchase") else "sale"
    party_name = (payload.get("party_name") or "").strip()
    party_mobile = (payload.get("party_mobile") or "").strip()
    is_official = bool(payload.get("is_official", False))
    vat_rate = payload.get("vat_rate") or 0
    items = payload.get("items") or []
    description = (payload.get("description") or "").strip()
    buyer_national_id = (payload.get("buyer_national_id") or "").strip()
    buyer_economic_code = (payload.get("buyer_economic_code") or "").strip()
    party_address = (payload.get("party_address") or "").strip()

    if not party_name:
        return {"success": False, "message": "نام طرف حساب (مشتری/فروشنده) را وارد کنید."}
    cleaned_items = []
    for item in items:
        try:
            qty = float(item.get("quantity") or 0)
            price = float(item.get("unit_price") or 0)
            desc = str(item.get("description") or "").strip()
        except (TypeError, ValueError):
            continue
        if not desc or qty <= 0 or price <= 0:
            continue
        cleaned_items.append({"description": desc, "quantity": qty, "unit": str(item.get("unit") or "عدد"), "unit_price": price})
    if not cleaned_items:
        return {"success": False, "message": "حداقل یک قلم با تعداد و قیمت معتبر لازم است."}

    try:
        vat_rate = float(vat_rate)
    except (TypeError, ValueError):
        vat_rate = 0
    apply_vat = is_official and vat_rate > 0
    force = bool(payload.get("force", False))

    try:
        if document_type == "sale" and not force:
            warnings = inventory_reconciler.check_sale_items_general(user_id, cleaned_items)
            message = "موجودی این کالا(ها) کافی نیست. آیا مطمئنید می‌خواهید این فاکتور را ثبت کنید؟"
            if is_official:
                official_warnings = inventory_reconciler.check_sale_items(user_id, cleaned_items)
                if official_warnings:
                    warnings = warnings + official_warnings
                    message = "عدم تطبیق فروش رسمی با خرید رسمی ثبت‌شده برای این کالا(ها) شناسایی شد. آیا مطمئنید می‌خواهید این فاکتور را ثبت کنید؟"
            if warnings:
                return {
                    "success": False,
                    "warning": True,
                    "message": message,
                    "details": warnings,
                }

        if document_type == "purchase":
            party_id = invoice_generator.find_or_create_vendor(
                party_name, buyer_economic_code, user_id=user_id,
                mobile=party_mobile, national_id=buyer_national_id, address=party_address,
            )
            result = invoice_generator.create_purchase_invoice(
                vendor_id=party_id,
                items=cleaned_items,
                description=description,
                vat_rate=vat_rate,
                apply_vat=apply_vat,
                user_id=user_id,
                vendor_national_id=buyer_national_id,
                vendor_economic_code=buyer_economic_code,
            )
        else:
            party_id = invoice_generator.find_or_create_customer(
                party_name, party_mobile, user_id=user_id, national_id=buyer_national_id,
                economic_code=buyer_economic_code, address=party_address,
            )
            result = invoice_generator.create_invoice(
                customer_id=party_id,
                items=cleaned_items,
                description=description,
                vat_rate=vat_rate,
                apply_vat=apply_vat,
                user_id=user_id,
                document_type=document_type,
                buyer_national_id=buyer_national_id,
                buyer_economic_code=buyer_economic_code,
            )
        if not result["success"]:
            return result

        try:
            if document_type == "purchase":
                engine.create_voucher(
                    date=datetime.now(),
                    description=f"خرید فاکتور {result['invoice_number']} از {party_name}",
                    lines=[("1201", result["total"], "debit"), ("2001", result["total"], "credit")],
                    user_id=user_id,
                    vendor_id=party_id,
                )
            elif document_type == "sale":
                engine.create_voucher(
                    date=datetime.now(),
                    description=f"فروش فاکتور {result['invoice_number']} به {party_name}",
                    lines=[("1101", result["total"], "debit"), ("4001", result["total"], "credit")],
                    user_id=user_id,
                    customer_id=party_id,
                )
            # برای "proforma" سند حسابداری ثبت نمی‌شود، چون فقط پیش‌نویس/استعلام قیمت است، نه تراکنش قطعی.
        except Exception:
            logger.exception("posting accounting voucher for invoice failed, invoice_id=%s", result.get("invoice_id"))

        profile = auth_manager.get_user_profile(user_id) or {}
        seller = SimpleNamespace(
            company_name=profile.get("business_name") or profile.get("name") or "-",
            address=profile.get("address", ""),
            phone=profile.get("phone_office", ""),
            mobile=profile.get("phone_mobile", ""),
            national_id=profile.get("national_id", ""),
            economic_code=profile.get("economic_code", ""),
            company_registration_number=profile.get("company_registration_number", ""),
            logo_path=profile.get("logo_path", ""),
        )

        invoices_dir = os.path.join("static", "invoices")
        os.makedirs(invoices_dir, exist_ok=True)
        pdf_path = os.path.join(invoices_dir, f"{result['invoice_number']}.pdf")

        if document_type == "purchase":
            invoice_data = invoice_generator.get_purchase_invoice(result["invoice_id"], user_id=user_id)
            invoice_data["seller"] = seller
            invoice_pdf_maker.create_invoice_pdf(invoice_data, pdf_path, document_type="purchase")
            invoice_generator.set_purchase_pdf_path(result["invoice_id"], pdf_path)
            result["pdf_url"] = f"/invoice/{result['invoice_id']}/pdf?type=purchase"
        else:
            invoice_data = invoice_generator.get_invoice(result["invoice_id"], user_id=user_id)
            invoice_data["seller"] = seller
            invoice_pdf_maker.create_invoice_pdf(invoice_data, pdf_path, document_type=document_type)
            invoice_generator.set_pdf_path(result["invoice_id"], pdf_path)
            result["pdf_url"] = f"/invoice/{result['invoice_id']}/pdf"
        return result
    except Exception:
        logger.exception("invoice_confirm failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در ثبت فاکتور."}


_pdf_download_tokens: dict = {}  # token -> (invoice_id, type, user_id, expires_at). یک‌بارمصرف، فقط برای دانلود PDF.


@app.get("/invoice/{invoice_id}/pdf-token")
async def invoice_pdf_token(request: Request, invoice_id: int, type: str = "sale") -> dict:
    """توکن دانلود یک‌بارمصرف کوتاه‌مدت می‌سازد - چون مینی‌اپ تلگرام/بله لینک PDF را در یک
    مرورگر/وب‌ویوی خارج از نشست مینی‌اپ باز می‌کند که کوکی ورود را ندارد."""
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    token = secrets.token_urlsafe(24)
    _pdf_download_tokens[token] = (invoice_id, type, user_id, datetime.now() + timedelta(minutes=5))
    return {"success": True, "url": f"/invoice/{invoice_id}/pdf?type={type}&dl_token={token}"}


@app.get("/invoice/{invoice_id}/pdf")
async def invoice_get_pdf(request: Request, invoice_id: int, type: str = "sale", dl_token: Optional[str] = None):
    user_id = get_user_id(request)
    if not user_id and dl_token:
        entry = _pdf_download_tokens.get(dl_token)
        if entry and entry[0] == invoice_id and entry[1] == type and entry[3] > datetime.now():
            user_id = entry[2]
            del _pdf_download_tokens[dl_token]
    if not user_id:
        return JSONResponse({"success": False, "message": "لطفاً وارد حساب خود شوید."}, status_code=401)
    if type == "purchase":
        data = invoice_generator.get_purchase_invoice(invoice_id, user_id=user_id)
    else:
        data = invoice_generator.get_invoice(invoice_id, user_id=user_id)
    if not data or not data["invoice"].pdf_path or not os.path.exists(data["invoice"].pdf_path):
        return JSONResponse({"success": False, "message": "فاکتور یافت نشد."}, status_code=404)
    return FileResponse(data["invoice"].pdf_path, media_type="application/pdf", filename=f"{data['invoice'].invoice_number}.pdf")


@app.get("/invoice/party-lookup")
async def invoice_party_lookup(request: Request, name: str = "", party_type: str = "customer") -> dict:
    """جستجوی مشتری/فروشنده با نام مشابه، فقط در محدوده همین کاربر - برای پیشنهاد خودکار اطلاعات و هشدار تشابه اسمی."""
    user_id = get_user_id(request)
    name = (name or "").strip()
    if not user_id or len(name) < 2:
        return {"success": True, "data": []}
    from database.models import Customer, Vendor
    session = engine.Session()
    try:
        if party_type == "vendor":
            rows = session.query(Vendor).filter(Vendor.user_id == user_id, Vendor.name.like(f"%{name}%")).limit(5).all()
        else:
            rows = session.query(Customer).filter(Customer.user_id == user_id, Customer.name.like(f"%{name}%")).limit(5).all()
        data = [{
            "id": r.id, "name": r.name,
            "mobile": getattr(r, "mobile", "") or "",
            "national_id": r.national_id or "",
            "economic_code": r.economic_code or "",
            "address": getattr(r, "address", "") or "",
        } for r in rows]
        return {"success": True, "data": data}
    finally:
        session.close()


@app.get("/inventory/opening-balances")
async def list_opening_balances(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    from database.models import OpeningStockBalance
    session = engine.Session()
    try:
        rows = session.query(OpeningStockBalance).filter_by(user_id=user_id).order_by(OpeningStockBalance.product_name).all()
        return {"success": True, "data": [
            {"id": r.id, "product_name": r.product_name, "quantity": r.quantity, "unit": r.unit} for r in rows
        ]}
    finally:
        session.close()


@app.post("/inventory/opening-balance")
async def set_opening_balance(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    payload = await request.json()
    product_name = (payload.get("product_name") or "").strip()
    unit = (payload.get("unit") or "عدد").strip() or "عدد"
    try:
        quantity = float(payload.get("quantity") or 0)
    except (TypeError, ValueError):
        quantity = 0
    if not product_name:
        return {"success": False, "message": "نام کالا را وارد کنید."}
    if quantity <= 0:
        return {"success": False, "message": "مقدار موجودی باید بیشتر از صفر باشد."}

    from database.models import OpeningStockBalance
    session = engine.Session()
    try:
        row = session.query(OpeningStockBalance).filter_by(user_id=user_id, product_name=product_name).first()
        if row:
            row.quantity = quantity
            row.unit = unit
        else:
            row = OpeningStockBalance(user_id=user_id, product_name=product_name, quantity=quantity, unit=unit)
            session.add(row)
        session.commit()
        return {"success": True, "message": f"موجودی اول دوره‌ی «{product_name}» ثبت شد."}
    finally:
        session.close()


@app.post("/inventory/opening-balance/{balance_id}/delete")
async def delete_opening_balance(request: Request, balance_id: int) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    from database.models import OpeningStockBalance
    session = engine.Session()
    try:
        row = session.query(OpeningStockBalance).filter_by(id=balance_id, user_id=user_id).first()
        if not row:
            return {"success": False, "message": "یافت نشد."}
        session.delete(row)
        session.commit()
        return {"success": True}
    finally:
        session.close()


@app.get("/invoice/item-suggestions")
async def invoice_item_suggestions(request: Request) -> dict:
    """آخرین آیتم‌های فاکتور/خریدی که این کاربر قبلاً ثبت کرده - برای پیشنهاد خودکار شرح کالا/واحد/قیمت."""
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "data": []}
    from database.models import InvoiceItem, ProformaInvoice, PurchaseItem, PurchaseInvoice
    session = engine.Session()
    try:
        sale_rows = session.query(InvoiceItem).join(
            ProformaInvoice, InvoiceItem.invoice_id == ProformaInvoice.id
        ).filter(ProformaInvoice.user_id == user_id).order_by(InvoiceItem.id.desc()).limit(200).all()
        purchase_rows = session.query(PurchaseItem).join(
            PurchaseInvoice, PurchaseItem.purchase_invoice_id == PurchaseInvoice.id
        ).filter(PurchaseInvoice.user_id == user_id).order_by(PurchaseItem.id.desc()).limit(200).all()
        seen = {}
        for row in [*sale_rows, *purchase_rows]:
            if row.description not in seen:
                seen[row.description] = {"description": row.description, "unit": row.unit, "unit_price": row.unit_price}
        return {"success": True, "data": list(seen.values())[:100]}
    finally:
        session.close()


@app.get("/invoice/list")
async def invoice_list(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return {"success": True, "data": invoice_generator.list_invoices(user_id)}


@app.get("/invoice/purchases")
async def invoice_purchases_list(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return {"success": True, "data": invoice_generator.list_purchase_invoices(user_id)}


# ========== مدیریت آپارتمان‌ها (شارژ و هزینه‌های جاری ساختمان) ==========

@app.get("/buildings/list")
async def buildings_list(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    buildings = building_manager.get_all_buildings(user_id)
    return {"success": True, "data": [{"id": b.id, "name": b.name, "address": b.address or "", "total_units": b.total_units, "charge_method": b.charge_method, "vacant_unit_weight": b.vacant_unit_weight} for b in buildings]}


@app.post("/buildings/create")
async def buildings_create(
    request: Request, name: str = Form(...), address: str = Form(""), total_units: int = Form(0),
    charge_method: str = Form("area"), vacant_unit_weight: float = Form(0.5),
) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return building_manager.add_building(user_id, name, address, total_units, charge_method, vacant_unit_weight)


@app.post("/buildings/{building_id}/settings")
async def buildings_settings_update(
    request: Request, building_id: int, charge_method: str = Form(None), vacant_unit_weight: float = Form(None),
) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    owned = [b.id for b in building_manager.get_all_buildings(user_id)]
    if building_id not in owned:
        return {"success": False, "message": "دسترسی غیرمجاز."}
    return building_manager.update_building_settings(building_id, charge_method, vacant_unit_weight)


@app.get("/buildings/{building_id}/units")
async def buildings_units(request: Request, building_id: int) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    owned = [b.id for b in building_manager.get_all_buildings(user_id)]
    if building_id not in owned:
        return {"success": False, "message": "دسترسی غیرمجاز."}
    units = building_manager.get_all_units(building_id)
    return {"success": True, "data": [{"id": u.id, "unit_number": u.unit_number, "owner_name": u.owner_name or "", "owner_phone": u.owner_phone or "", "area": u.area or 0, "occupant_count": u.occupant_count or 0, "is_vacant": bool(u.is_vacant)} for u in units]}


@app.post("/buildings/units/create")
async def buildings_units_create(
    request: Request, building_id: int = Form(...), unit_number: str = Form(...),
    owner_name: str = Form(""), owner_phone: str = Form(""), area: float = Form(0),
    occupant_count: int = Form(0), is_vacant: bool = Form(False),
) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    owned = [b.id for b in building_manager.get_all_buildings(user_id)]
    if building_id not in owned:
        return {"success": False, "message": "دسترسی غیرمجاز."}
    return building_manager.add_unit(building_id, unit_number, owner_name, owner_phone, area, occupant_count, is_vacant)


@app.post("/buildings/expense")
async def buildings_expense(
    request: Request, building_id: int = Form(...), expense_type: str = Form(...),
    amount: float = Form(...), description: str = Form(""),
) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    owned = [b.id for b in building_manager.get_all_buildings(user_id)]
    if building_id not in owned:
        return {"success": False, "message": "دسترسی غیرمجاز."}
    return building_manager.add_expense(building_id, expense_type, amount, description)


@app.post("/buildings/issue-invoices")
async def buildings_issue_invoices(request: Request, building_id: int = Form(...), month: str = Form(...)) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    owned = [b.id for b in building_manager.get_all_buildings(user_id)]
    if building_id not in owned:
        return {"success": False, "message": "دسترسی غیرمجاز."}
    return building_manager.issue_invoices_for_month(building_id, month)


@app.get("/buildings/{building_id}/unpaid")
async def buildings_unpaid(request: Request, building_id: int) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    owned = [b.id for b in building_manager.get_all_buildings(user_id)]
    if building_id not in owned:
        return {"success": False, "message": "دسترسی غیرمجاز."}
    invoices = building_manager.get_unpaid_invoices(building_id)
    session = building_manager.Session()
    try:
        from database.building_models import BuildingUnit
        data = []
        for inv in invoices:
            unit = session.query(BuildingUnit).filter(BuildingUnit.id == inv.unit_id).first()
            data.append({"id": inv.id, "month": inv.month, "amount": inv.total_amount, "unit_number": unit.unit_number if unit else "-"})
        return {"success": True, "data": data}
    finally:
        session.close()


@app.post("/buildings/invoices/{invoice_id}/mark-paid")
async def buildings_mark_paid(request: Request, invoice_id: int) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    owned = [b.id for b in building_manager.get_all_buildings(user_id)]
    session = building_manager.Session()
    try:
        from database.building_models import BuildingInvoice, BuildingUnit
        invoice = session.query(BuildingInvoice).filter(BuildingInvoice.id == invoice_id).first()
        if not invoice:
            return {"success": False, "message": "قبض یافت نشد."}
        unit = session.query(BuildingUnit).filter(BuildingUnit.id == invoice.unit_id).first()
        if not unit or unit.building_id not in owned:
            return {"success": False, "message": "دسترسی غیرمجاز."}
    finally:
        session.close()
    return building_manager.mark_invoice_paid(invoice_id)


# ========== REPORT ENDPOINTS ==========

@app.get("/api/profit_loss")
async def api_profit_loss(request: Request, date_from: str = "", date_to: str = "") -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to, end_of_day=True)
    rows = engine.get_profit_loss(user_id=user_id, date_from=df, date_to=dt)
    data = [{"code": r.code, "name": r.name, "type": r.type, "balance": r.balance} for r in rows if r.balance]
    total_income = sum(r["balance"] for r in data if r["type"] == "income")
    total_expense = sum(r["balance"] for r in data if r["type"] == "expense")
    return {"success": True, "data": data, "total_income": total_income, "total_expense": total_expense, "net": total_income - total_expense}


@app.get("/api/monthly_summary")
async def api_monthly_summary(request: Request, months: int = 6) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return {"success": True, "data": engine.get_monthly_summary(user_id, months=min(max(months, 1), 24))}


@app.get("/api/balance_sheet")
async def api_balance_sheet(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return engine.get_balance_sheet(user_id=user_id)


@app.get("/api/journal")
async def api_journal(request: Request, limit: int = 50, offset: int = 0) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return {"data": engine.get_journal(limit, offset, user_id=user_id)}


# ========== بستن سال مالی ==========

@app.get("/accounting/fiscal-year-status")
async def fiscal_year_status(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    status = engine.get_open_fiscal_years(user_id)
    return {
        "success": True,
        "last_closed_until": status["last_closed_until"].strftime("%Y-%m-%d") if status["last_closed_until"] else None,
        "last_fiscal_year_label": status["last_fiscal_year_label"],
        "first_entry_date": status["first_entry_date"].strftime("%Y-%m-%d") if status["first_entry_date"] else None,
    }


@app.post("/accounting/close-fiscal-year")
async def close_fiscal_year(
    request: Request,
    period_start: str = Form(...),
    period_end: str = Form(...),
    fiscal_year_label: str = Form(...),
) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    rate_limit(f"close_fy:{user_id}", max_requests=5, window_seconds=600)
    try:
        start_dt = datetime.strptime(period_start, "%Y-%m-%d")
        end_dt = datetime.strptime(period_end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        return {"success": False, "message": "فرمت تاریخ نامعتبر است."}
    try:
        return engine.close_fiscal_year(user_id, start_dt, end_dt, fiscal_year_label.strip())
    except Exception:
        logger.exception("close_fiscal_year failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در بستن سال مالی."}


# ========== ADMIN ENDPOINTS ==========

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request) -> HTMLResponse:
    user_id = get_user_id(request)
    if not user_id or not auth_manager.is_user_admin(user_id):
        return HTMLResponse(content="<h2>دسترسی غیرمجاز</h2><p>شما دسترسی ادمین ندارید.</p>", status_code=403)
    with open("web_app/templates/admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/admin/stats")
async def admin_stats(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    session = license_manager.Session()
    try:
        from database.license_models import Transaction, License, User
        from sqlalchemy import func
        total_revenue = session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(Transaction.is_confirmed == True).scalar() or 0
        total_users = session.query(func.count(User.id)).scalar() or 0
        active_licenses = session.query(func.count(License.id)).filter(License.is_active == True).scalar() or 0
        by_plan = dict(
            session.query(License.plan_type, func.count(License.id))
            .filter(License.is_active == True)
            .group_by(License.plan_type).all()
        )
        thirty_days_ago = datetime.now() - timedelta(days=30)
        new_users_30d = session.query(func.count(User.id)).filter(User.created_at >= thirty_days_ago).scalar() or 0
        total_sale_invoices = session.query(func.count(ProformaInvoice.id)).scalar() or 0
        total_purchase_invoices = session.query(func.count(PurchaseInvoice.id)).scalar() or 0
        return {
            "success": True,
            "total_revenue": int(total_revenue),
            "total_users": total_users,
            "new_users_30d": new_users_30d,
            "active_licenses": active_licenses,
            "active_by_plan": by_plan,
            "total_sale_invoices": total_sale_invoices,
            "total_purchase_invoices": total_purchase_invoices,
        }
    finally:
        session.close()


@app.get("/admin/pricing")
async def admin_pricing_list(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    return {"success": True, "data": license_manager.get_pricing_plans(include_inactive=True)}


@app.post("/admin/pricing/update")
async def admin_pricing_update(
    request: Request,
    plan_key: str = Form(...),
    name: Optional[str] = Form(None),
    price: Optional[int] = Form(None),
    months: Optional[int] = Form(None),
    max_vouchers: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    fields = {"name": name, "price": price, "months": months, "max_vouchers": max_vouchers, "description": description, "is_active": is_active}
    return license_manager.update_pricing_plan(plan_key, **{k: v for k, v in fields.items() if v is not None})


@app.get("/admin/discounts")
async def admin_discounts_list(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    return {"success": True, "data": license_manager.list_discount_codes()}


@app.post("/admin/discounts/create")
async def admin_discounts_create(
    request: Request,
    code: Optional[str] = Form(""),
    title: str = Form(...),
    discount_type: str = Form("percent"),
    discount_value: float = Form(...),
    applicable_plan: Optional[str] = Form(""),
    start_date: Optional[str] = Form(""),
    end_date: Optional[str] = Form(""),
    max_uses: int = Form(0),
) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    if discount_type not in ("percent", "fixed"):
        return {"success": False, "message": "نوع تخفیف نامعتبر است."}
    sd = _parse_report_date(start_date)
    ed = _parse_report_date(end_date, end_of_day=True)
    return license_manager.create_discount_code(
        code=(code or "").strip().upper(), title=title, discount_type=discount_type,
        discount_value=discount_value, applicable_plan=(applicable_plan or "").strip(),
        start_date=sd, end_date=ed, max_uses=max_uses,
    )


@app.post("/admin/discounts/toggle/{code_id}")
async def admin_discounts_toggle(request: Request, code_id: int) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    return license_manager.toggle_discount_code(code_id)


@app.get("/admin/logs")
async def admin_logs(request: Request, lines: int = 200) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    log_path = os.path.join("logs", "app.log")
    if not os.path.exists(log_path):
        return {"success": True, "data": ""}
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    return {"success": True, "data": "".join(all_lines[-lines:])}


@app.get("/admin/platform-settings")
async def admin_platform_settings_get(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    settings = platform_settings.get_all()
    logo_path = settings.get("platform_logo_path", "")
    settings["platform_logo_url"] = ("/" + logo_path.replace("\\", "/")) if logo_path else ""
    return {"success": True, "data": settings}


@app.post("/admin/platform-settings/update")
async def admin_platform_settings_update(
    request: Request,
    support_technical_phone: Optional[str] = Form(None),
    support_technical_telegram: Optional[str] = Form(None),
    support_sales_phone: Optional[str] = Form(None),
    support_sales_telegram: Optional[str] = Form(None),
) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    platform_settings.update_many({
        "support_technical_phone": support_technical_phone,
        "support_technical_telegram": support_technical_telegram,
        "support_sales_phone": support_sales_phone,
        "support_sales_telegram": support_sales_telegram,
    })
    return {"success": True, "message": "تنظیمات پلتفرم ذخیره شد."}


@app.post("/admin/platform-logo")
async def admin_platform_logo(request: Request, logo: UploadFile = File(...)) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    ext = os.path.splitext(logo.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
        return {"success": False, "message": "فرمت تصویر باید png، jpg، webp یا svg باشد."}
    logos_dir = os.path.join("static", "platform")
    os.makedirs(logos_dir, exist_ok=True)
    dest_path = os.path.join(logos_dir, f"logo{ext}")
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(logo.file, buffer)
    except Exception:
        logger.exception("admin_platform_logo upload failed")
        return {"success": False, "message": "خطا در ذخیره لوگو."}
    platform_settings.set("platform_logo_path", dest_path)
    return {"success": True, "message": "لوگوی پلتفرم ذخیره شد.", "logo_url": "/" + dest_path.replace("\\", "/")}


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * (len(key) - 8) + key[-4:]


@app.get("/admin/ai-settings")
async def admin_ai_settings_get(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    settings = platform_settings.get_all()
    return {
        "success": True,
        "data": {
            "ai_provider": settings.get("ai_provider", ""),
            "ai_model": settings.get("ai_model", ""),
            "ai_api_key_masked": _mask_key(settings.get("ai_api_key", "")),
            "ai_api_key_set": bool(settings.get("ai_api_key")),
            "providers": SUPPORTED_PROVIDERS,
        },
    }


@app.post("/admin/ai-settings/update")
async def admin_ai_settings_update(
    request: Request,
    ai_provider: str = Form(...),
    ai_model: Optional[str] = Form(None),
    ai_api_key: Optional[str] = Form(None),
) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    if ai_provider not in SUPPORTED_PROVIDERS and ai_provider != "":
        return {"success": False, "message": "ارائه‌دهنده هوش مصنوعی نامعتبر است."}
    updates = {"ai_provider": ai_provider, "ai_model": ai_model or ""}
    if ai_api_key:
        updates["ai_api_key"] = ai_api_key
    platform_settings.update_many(updates)
    return {"success": True, "message": "تنظیمات هوش مصنوعی ذخیره شد."}


@app.post("/admin/ai-settings/test")
async def admin_ai_settings_test(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    fresh_processor = LLMProcessor()
    return fresh_processor.test_connection()


@app.get("/admin/sms-settings")
async def admin_sms_settings_get(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    settings = platform_settings.get_all()
    return {
        "success": True,
        "data": {
            "sms_username": settings.get("sms_username", ""),
            "sms_sender": settings.get("sms_sender", ""),
            "sms_password_masked": _mask_key(settings.get("sms_password", "")),
            "sms_password_set": bool(settings.get("sms_password")),
        },
    }


@app.post("/admin/sms-settings/update")
async def admin_sms_settings_update(
    request: Request,
    sms_username: Optional[str] = Form(None),
    sms_sender: Optional[str] = Form(None),
    sms_password: Optional[str] = Form(None),
) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    updates = {"sms_username": sms_username or "", "sms_sender": sms_sender or ""}
    if sms_password:
        updates["sms_password"] = sms_password
    platform_settings.update_many(updates)
    return {"success": True, "message": "تنظیمات پیامک ذخیره شد."}


@app.post("/admin/sms-settings/test")
async def admin_sms_settings_test(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    return test_sms_connection()


@app.get("/admin/payment-settings")
async def admin_payment_settings_get(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    settings = platform_settings.get_all()
    return {
        "success": True,
        "data": {
            "zarinpal_merchant_id_masked": _mask_key(settings.get("zarinpal_merchant_id", "")),
            "zarinpal_merchant_id_set": bool(settings.get("zarinpal_merchant_id")),
            "zarinpal_callback_url": settings.get("zarinpal_callback_url", ""),
        },
    }


@app.post("/admin/payment-settings/update")
async def admin_payment_settings_update(
    request: Request,
    zarinpal_merchant_id: Optional[str] = Form(None),
    zarinpal_callback_url: Optional[str] = Form(None),
) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    updates = {"zarinpal_callback_url": zarinpal_callback_url or ""}
    if zarinpal_merchant_id:
        updates["zarinpal_merchant_id"] = zarinpal_merchant_id
    platform_settings.update_many(updates)
    return {"success": True, "message": "تنظیمات درگاه پرداخت ذخیره شد."}


@app.post("/admin/payment-settings/test")
async def admin_payment_settings_test(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    return payment_gateway.test_connection()


@app.get("/admin/license/{user_id}")
async def admin_license(request: Request, user_id: int) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    return license_manager.check_license(user_id)

@app.get("/admin/users")
async def admin_users(request: Request) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    return {"data": auth_manager.get_all_users()}


@app.post("/admin/users/{user_id}/set-admin")
async def admin_set_user_admin(request: Request, user_id: int, is_admin: bool = Form(...)) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    if user_id == uid and not is_admin:
        return {"success": False, "message": "نمی‌توانید دسترسی ادمین خودتان را حذف کنید."}
    result = auth_manager.set_user_admin(user_id, is_admin)
    logger.info("Admin %s set is_admin=%s for user_id=%s", uid, is_admin, user_id)
    return result

ALLOWED_PLAN_TYPES = {"free_trial", "monthly", "quarterly", "semi_annual", "annual"}

@app.post("/admin/license/grant/{user_id}/{plan_type}")
async def admin_grant_license(request: Request, user_id: int, plan_type: str) -> dict:
    uid = get_user_id(request)
    if not uid or not auth_manager.is_user_admin(uid):
        return {"success": False, "message": "دسترسی غیرمجاز"}
    if plan_type not in ALLOWED_PLAN_TYPES:
        return {"success": False, "message": "نوع پلن نامعتبر است."}
    try:
        key = license_manager.generate_license_key(user_id, plan_type)
        logger.info("Admin %s granted license plan=%s to user_id=%s", uid, plan_type, user_id)
        return {"success": True, "license_key": key, "message": f"لایسنس {plan_type} برای کاربر {user_id} صادر شد."}
    except Exception:
        logger.exception("admin_grant_license failed for user_id=%s plan=%s", user_id, plan_type)
        return {"success": False, "message": "خطا در صدور لایسنس."}

# ========== MINI-APP (همان صفحه اصلی) ==========

@app.get("/app", response_class=HTMLResponse)
async def mini_app() -> HTMLResponse:
    with open("web_app/templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)