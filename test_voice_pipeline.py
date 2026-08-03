import sys, os
sys.stdout.reconfigure(encoding="utf-8")
from ai_handlers.voice_to_accounting import VoiceToAccounting
from core.accounting_engine import AccountingEngine
from core.ai_voucher_fallback import try_ai_voucher

out = open("voice_pipeline_result.txt", "w", encoding="utf-8")
def log(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    out.write(line + "\n")
    out.flush()

vh = VoiceToAccounting(model_size="base")
engine = AccountingEngine()

files = ["01_simple_buy", "02_complex_verbose", "03_expense_words", "04_credit_sale", "05_receive_cash"]

for name in files:
    path = f"voice_temp/test_audio/{name}.mp3"
    log("=" * 66)
    log("FILE:", name)
    try:
        data, transcript = vh.voice_to_voucher(path)
        log("TRANSCRIPT :", transcript.strip())
        rule_ok = data.get("type") and data.get("amount", 0) > 0
        log("RULE RESULT:", {k: v for k, v in data.items() if k != "description"})
        if not rule_ok:
            log(">>> RULES FAILED -> trying AI (Ollama qwen2.5:3b)...")
            ai = try_ai_voucher(engine, transcript, user_id=1)
            if ai.get("success"):
                log("AI OK: amount=%s type=%s debit=%s credit=%s" % (ai.get("amount"), ai.get("type"), ai.get("debit_account"), ai.get("credit_account")))
                log("AI MSG:", ai.get("message"))
            else:
                log("AI FAILED:", ai)
        else:
            log("RULES OK (no AI needed)")
    except Exception as e:
        log("ERROR:", type(e).__name__, e)

out.close()
log("DONE")

