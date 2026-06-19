# web_app/main_simple.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from core.accounting_engine import AccountingEngine
from core.text_command_handler import TextCommandHandler
from ai_handlers.voice_to_accounting import VoiceToAccounting
from datetime import datetime
import shutil

app = FastAPI(title="مینی‌اپ حسابداری")

engine = AccountingEngine()
text_handler = TextCommandHandler(engine)
voice_handler = VoiceToAccounting(model_size="base")

os.makedirs("voice_temp", exist_ok=True)

HTML_PAGE = """
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>حسابدار من</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .card {
            background: white;
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        .header { text-align: center; color: white; margin-bottom: 20px; }
        .header h1 { font-size: 24px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 8px; font-weight: bold; color: #333; }
        textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 12px;
            font-family: inherit;
            font-size: 14px;
            resize: vertical;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            width: 100%;
            margin-top: 10px;
        }
        .voice-btn {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            margin-top: 5px;
        }
        .result {
            margin-top: 15px;
            padding: 12px;
            border-radius: 12px;
            display: none;
        }
        .result.success { background: #d4edda; color: #155724; display: block; }
        .result.error { background: #f8d7da; color: #721c24; display: block; }
        .result.info { background: #d1ecf1; color: #0c5460; display: block; }
        .menu {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .menu-btn {
            flex: 1;
            background: white;
            color: #667eea;
            border: 1px solid white;
        }
        .section { display: none; }
        .section.active { display: block; }
        .balance-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        .debit { color: #28a745; }
        .credit { color: #dc3545; }
        .recording {
            background: #ff4757;
            animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        audio { width: 100%; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 حسابدار من</h1>
            <p>سیستم حسابداری هوشمند بازرگانی</p>
        </div>

        <div class="menu">
            <button class="menu-btn" onclick="showSection('voucher')">📝 ثبت سند</button>
            <button class="menu-btn" onclick="showSection('voice')">🎤 ویس</button>
            <button class="menu-btn" onclick="showSection('balance')">📊 تراز</button>
        </div>

        <!-- بخش ثبت متن -->
        <div id="voucher-section" class="card section active">
            <h3>ثبت سند با متن</h3>
            <div class="form-group">
                <label>شرح سند:</label>
                <textarea id="description" rows="3" placeholder="مثال: خرید 100 عدد خودکار 5000 تومان"></textarea>
            </div>
            <button onclick="createVoucher()">📝 ثبت سند</button>
            <div id="voucher-result" class="result"></div>
        </div>

        <!-- بخش ویس -->
        <div id="voice-section" class="card section">
            <h3>🎤 ثبت سند با ویس</h3>
            <div class="form-group">
                <label>ضبط صدا:</label>
                <button id="recordBtn" class="voice-btn" onclick="startRecording()">🎙️ شروع ضبط</button>
                <button id="stopBtn" class="voice-btn" style="display:none; background:#ff4757;" onclick="stopRecording()">⏹️ توقف ضبط</button>
                <audio id="audioPlayback" controls style="display:none;"></audio>
            </div>
            <button id="sendVoiceBtn" style="display:none;" onclick="sendVoice()">📤 ارسال و ثبت سند</button>
            <div id="voice-result" class="result"></div>
            <p style="font-size:12px; color:#666; margin-top:10px;">💡 نکته: واضح صحبت کنید. مثال: "خرید 100 عدد خودکار 5000 تومان"</p>
        </div>

        <!-- بخش تراز -->
        <div id="balance-section" class="card section">
            <h3>📊 تراز آزمایشی</h3>
            <div id="balance-list"></div>
            <button onclick="loadBalance()" style="margin-top: 15px;">🔄 بروزرسانی</button>
        </div>
    </div>

    <script>
        let mediaRecorder;
        let audioChunks = [];

        function showSection(section) {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            if (section === 'voucher') document.getElementById('voucher-section').classList.add('active');
            if (section === 'voice') document.getElementById('voice-section').classList.add('active');
            if (section === 'balance') document.getElementById('balance-section').classList.add('active');
            if (section === 'balance') loadBalance();
        }

        async function createVoucher() {
            const desc = document.getElementById('description').value;
            const resultDiv = document.getElementById('voucher-result');
            
            if (!desc.trim()) {
                resultDiv.className = 'result error';
                resultDiv.innerHTML = '❌ لطفاً شرح سند را وارد کنید.';
                return;
            }
            
            try {
                const response = await fetch('/create_voucher', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'description=' + encodeURIComponent(desc)
                });
                const data = await response.json();
                
                if (data.success) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = '✅ ' + data.message;
                    document.getElementById('description').value = '';
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = '❌ ' + data.message;
                }
            } catch (e) {
                resultDiv.className = 'result error';
                resultDiv.innerHTML = '❌ خطا در ارتباط با سرور';
            }
        }

        async function startRecording() {
            audioChunks = [];
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                
                mediaRecorder.ondataavailable = event => {
                    audioChunks.push(event.data);
                };
                
                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const audioUrl = URL.createObjectURL(audioBlob);
                    const audioPlayback = document.getElementById('audioPlayback');
                    audioPlayback.src = audioUrl;
                    audioPlayback.style.display = 'block';
                    document.getElementById('sendVoiceBtn').style.display = 'block';
                    document.getElementById('voice-result').className = 'result info';
                    document.getElementById('voice-result').innerHTML = '✅ صدای شما ضبط شد. حالا دکمه ارسال را بزنید.';
                    
                    window.voiceBlob = audioBlob;
                };
                
                mediaRecorder.start();
                document.getElementById('recordBtn').style.display = 'none';
                document.getElementById('stopBtn').style.display = 'block';
                document.getElementById('voice-result').className = 'result info';
                document.getElementById('voice-result').innerHTML = '🔴 در حال ضبط... دکمه توقف را بزنید.';
            } catch (err) {
                document.getElementById('voice-result').className = 'result error';
                document.getElementById('voice-result').innerHTML = '❌ دسترسی به میکروفون امکان‌پذیر نیست.';
            }
        }

        function stopRecording() {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
                mediaRecorder.stream.getTracks().forEach(track => track.stop());
                document.getElementById('recordBtn').style.display = 'block';
                document.getElementById('stopBtn').style.display = 'none';
            }
        }

        async function sendVoice() {
            if (!window.voiceBlob) {
                document.getElementById('voice-result').className = 'result error';
                document.getElementById('voice-result').innerHTML = '❌ ابتدا صدایی ضبط کنید.';
                return;
            }
            
            const formData = new FormData();
            formData.append('voice', window.voiceBlob, 'recording.webm');
            
            document.getElementById('voice-result').className = 'result info';
            document.getElementById('voice-result').innerHTML = '⏳ در حال پردازش ویس...';
            
            try {
                const response = await fetch('/process_voice', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('voice-result').className = 'result success';
                    document.getElementById('voice-result').innerHTML = '✅ ' + data.message + '<br>💰 مبلغ: ' + data.amount + ' تومان';
                    document.getElementById('audioPlayback').style.display = 'none';
                    document.getElementById('sendVoiceBtn').style.display = 'none';
                    window.voiceBlob = null;
                } else {
                    document.getElementById('voice-result').className = 'result error';
                    document.getElementById('voice-result').innerHTML = '❌ ' + data.message;
                }
            } catch (e) {
                document.getElementById('voice-result').className = 'result error';
                document.getElementById('voice-result').innerHTML = '❌ خطا در ارتباط با سرور';
            }
        }

        async function loadBalance() {
            const container = document.getElementById('balance-list');
            container.innerHTML = '<div style="text-align:center;">⏳ در حال بارگذاری...</div>';
            
            try {
                const response = await fetch('/trial_balance');
                const data = await response.json();
                
                if (data.data.length === 0) {
                    container.innerHTML = '<div style="text-align:center;">📭 هیچ داده‌ای یافت نشد</div>';
                    return;
                }
                
                let html = '<div class="balance-item"><strong>حساب</strong><span><strong>بدهکار</strong> | <strong>بستانکار</strong></span></div>';
                for (const item of data.data) {
                    html += `<div class="balance-item">
                        <span>${item.name}</span>
                        <span><span class="debit">${item.debit.toLocaleString()}</span> | <span class="credit">${item.credit.toLocaleString()}</span></span>
                    </div>`;
                }
                container.innerHTML = html;
            } catch (e) {
                container.innerHTML = '<div style="text-align:center;">❌ خطا در بارگذاری</div>';
            }
        }

        loadBalance();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    return HTML_PAGE

@app.post("/create_voucher")
async def create_voucher(description: str = Form(...)) -> dict:
    try:
        result = text_handler.parse_and_create_voucher(description)
        return {"success": result["success"], "message": result["message"]}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/process_voice")
async def process_voice(voice: UploadFile = File(...)) -> dict:
    try:
        # ذخیره فایل موقت
        temp_path = f"voice_temp/{voice.filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(voice.file, buffer)
        
        # تبدیل ویس به سند
        data, transcript = voice_handler.voice_to_voucher(temp_path)
        
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
            return {
                "success": False,
                "message": "اطلاعات ناقص است. لطفاً واضح‌تر صحبت کنید."
            }
    except Exception as e:
        return {"success": False, "message": str(e)}

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9000)