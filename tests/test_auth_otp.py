import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import pytest
from datetime import datetime, timedelta

from core.auth import AuthManager
from database.license_models import User


@pytest.fixture
def auth_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    yield path
    os.close(fd)
    try:
        os.unlink(path)
    except PermissionError:
        pass


@pytest.fixture
def auth(auth_db_path):
    return AuthManager(auth_db_path)


def test_request_otp_rejects_invalid_mobile(auth):
    result = auth.request_otp("12345")
    assert result["success"] is False


def test_request_otp_then_verify_with_wrong_code_fails(auth, monkeypatch):
    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 123456)
    req = auth.request_otp("09121234567")
    assert req["success"] is True

    bad = auth.verify_otp("09121234567", "000000")
    assert bad["success"] is False

    good = auth.verify_otp("09121234567", "123456")
    assert good["success"] is True
    assert good["user_id"] is not None
    assert good["is_new"] is True


def test_same_mobile_unifies_telegram_and_web_identity(auth, monkeypatch):
    """رگرسیون: کاربری که از تلگرام ثبت‌نام کرده، با همون موبایل وارد وب‌اپ هم بشه باید همون حساب باشه،
    نه یک کاربر جدید (قبلاً تلگرام/بله از موبایل ساختگی tg_/bale_ استفاده می‌کردند که این یکپارچگی را می‌شکست)."""
    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 111111)
    auth.request_otp("09121234567")
    tg_result = auth.verify_otp("09121234567", "111111", name="کاربر تلگرام")
    assert tg_result["success"] is True
    tg_user_id = tg_result["user_id"]

    link = auth.link_telegram(tg_user_id, "555000111")
    assert link["success"] is True

    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 222222)
    monkeypatch.setattr("core.auth.OTP_RESEND_COOLDOWN_SECONDS", 0)
    auth.request_otp("09121234567")
    web_result = auth.verify_otp("09121234567", "222222")
    assert web_result["success"] is True
    assert web_result["user_id"] == tg_user_id
    assert web_result["is_new"] is False

    assert auth.get_user_by_telegram("555000111") == tg_user_id


def test_link_telegram_rejects_id_already_used_by_another_user(auth, monkeypatch):
    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 333333)
    auth.request_otp("09121111111")
    user1 = auth.verify_otp("09121111111", "333333")["user_id"]
    auth.link_telegram(user1, "777000888")

    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 444444)
    auth.request_otp("09122222222")
    user2 = auth.verify_otp("09122222222", "444444")["user_id"]

    result = auth.link_telegram(user2, "777000888")
    assert result["success"] is False


def test_verify_otp_without_request_fails(auth):
    result = auth.verify_otp("09121234567", "123456")
    assert result["success"] is False


def test_otp_locks_after_max_attempts(auth, monkeypatch):
    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 654321)
    auth.request_otp("09129876543")
    for _ in range(5):
        result = auth.verify_otp("09129876543", "000000")
        assert result["success"] is False
    locked = auth.verify_otp("09129876543", "654321")
    assert locked["success"] is False
    assert "تلاش" in locked["message"]


def test_otp_expired_is_rejected(auth, monkeypatch):
    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 111111)
    auth.request_otp("09120001111")

    session = auth.Session()
    try:
        user = session.query(User).filter(User.mobile == "09120001111").first()
        user.otp_expires_at = datetime.now() - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    result = auth.verify_otp("09120001111", "111111")
    assert result["success"] is False
    assert "منقضی" in result["message"]


def test_otp_resend_cooldown(auth, monkeypatch):
    monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 222222)
    first = auth.request_otp("09123334444")
    assert first["success"] is True
    second = auth.request_otp("09123334444")
    assert second["success"] is False
