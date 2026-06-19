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
