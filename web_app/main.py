# web_app/main.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import html
import logging
import secrets
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
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
from ai_handlers.voice_to_accounting import VoiceToAccounting
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

# ========== MOUNT STATIC FILES ==========
os.makedirs("static", exist_ok=True)
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
voice_handler = VoiceToAccounting(model_size="base")


def get_user_id(request: Request) -> Optional[int]:
    token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if token:
        return auth_manager.validate_session(token)
    return None

@app.get("/auth/me")
async def auth_me(request: Request) -> dict:
    user_id = get_user_id(request)
    return {"logged_in": bool(user_id), "user_id": user_id}

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
async def create_voucher(request: Request, description: str = Form(...)) -> dict:
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
        result = text_handler.parse_and_create_voucher(description)
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
            data, transcript = voice_handler.voice_to_voucher(temp_path)
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
                ]
            )
            return {
                "success": True,
                "message": f"سند شماره {entry_id} ثبت شد",
                "amount": data["amount"],
                "type": data["type"]
            }
        else:
            return {"success": False, "message": "اطلاعات ناقص است. لطفاً واضح‌تر صحبت کنید."}
    except Exception:
        logger.exception("process_voice failed for user_id=%s", user_id)
        return {"success": False, "message": "خطا در پردازش صدا. لطفاً دوباره تلاش کنید."}

# تراز آزمایشی
@app.get("/trial_balance")
async def get_trial_balance() -> dict:
    balances = engine.get_trial_balance()
    data = []
    for row in balances:
        if row.total_debit != 0 or row.total_credit != 0:
            data.append({
                "code": row.code,
                "name": row.name,
                "debit": row.total_debit,
                "credit": row.total_credit
            })
    return {"data": data}

# لیست آخرین اسناد
@app.get("/vouchers")
async def get_vouchers(limit: int = 20) -> dict:
    session = engine.Session()
    try:
        from database.models import JournalEntry
        entries = session.query(JournalEntry).order_by(
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
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
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
    """
    for key, plan in plans.items():
        if key != "free_trial":
            html_content += f"""
            <div class="card">
                <h3>💰 {plan['name']}</h3>
                <div class="price">{plan['price']:,} <small>تومان</small></div>
                <p>{plan['description']}</p>
                <button onclick="location.href='/payment/{key}'">خرید اشتراک</button>
            </div>
            """
    html_content += """
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ========== PAYMENT ENDPOINTS ==========

@app.get("/payment/{plan_type}")
async def start_payment(request: Request, plan_type: str):
    user_id = get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/")
    plans = license_manager.get_pricing_plans()
    plan = plans.get(plan_type)
    if not plan or plan_type == "free_trial":
        return HTMLResponse("<h2>پلن نامعتبر است.</h2>", status_code=400)
    rate_limit(f"payment:{user_id}", max_requests=10, window_seconds=300)
    try:
        result = payment_gateway.create_payment_request(user_id, plan["price"], plan_type)
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
    return JSONResponse({"success": result["success"], "message": result["message"]})


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


# ========== REPORT ENDPOINTS ==========

@app.get("/api/profit_loss")
async def api_profit_loss(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return engine.get_profit_loss()


@app.get("/api/balance_sheet")
async def api_balance_sheet(request: Request) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return engine.get_balance_sheet()


@app.get("/api/journal")
async def api_journal(request: Request, limit: int = 50, offset: int = 0) -> dict:
    user_id = get_user_id(request)
    if not user_id:
        return {"success": False, "message": "لطفاً وارد حساب خود شوید."}
    return {"data": engine.get_journal(limit, offset)}


# ========== ADMIN ENDPOINTS ==========

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request) -> HTMLResponse:
    user_id = get_user_id(request)
    if not user_id or not auth_manager.is_user_admin(user_id):
        return HTMLResponse(content="<h2>دسترسی غیرمجاز</h2><p>شما دسترسی ادمین ندارید.</p>", status_code=403)
    users = auth_manager.get_all_users()
    html_out = """<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>پنل مدیریت | حسابدار هوشمند</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',Tahoma,sans-serif; background:#f5f5f5; padding:20px; }
.header { background:linear-gradient(135deg,#1a4a6f,#0f2b3d); color:white; padding:20px; border-radius:12px; margin-bottom:20px; }
table { width:100%; border-collapse:collapse; background:white; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,0.1); }
th { background:#1a4a6f; color:white; padding:12px; text-align:right; }
td { padding:10px 12px; border-bottom:1px solid #eee; }
tr:hover { background:#f0f7ff; }
.badge { display:inline-block; padding:2px 8px; border-radius:20px; font-size:12px; }
.badge-admin { background:#ffc107; color:#333; }
.badge-user { background:#e9ecef; color:#555; }
</style></head>
<body>
<div class="header"><h2>پنل مدیریت</h2><p>لیست کاربران سیستم</p></div>
<table><tr><th>نام</th><th>موبایل</th><th>کسب‌وکار</th><th>نوع</th><th>دسترسی</th><th>تاریخ ثبت</th></tr>"""
    for u in users:
        role = "ادمین" if u["is_admin"] else "کاربر"
        name = html.escape(u['name'])
        mobile = html.escape(u['mobile'])
        business_name = html.escape(u['business_name'])
        business_type = html.escape(u['business_type'])
        created_at = html.escape(u['created_at'])
        badge_class = 'admin' if u['is_admin'] else 'user'
        html_out += f"<tr><td>{name}</td><td>{mobile}</td><td>{business_name}</td><td>{business_type}</td><td><span class='badge badge-{badge_class}'>{role}</span></td><td>{created_at}</td></tr>"
    html_out += "</table><br><a href='/' style='color:#1a4a6f;'>بازگشت به صفحه اصلی</a></body></html>"
    return HTMLResponse(content=html_out)

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