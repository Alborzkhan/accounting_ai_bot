import pytest
from core.platform_settings import PlatformSettingsManager
import core.sms_service as sms_service


@pytest.fixture
def settings(db_path):
    return PlatformSettingsManager(db_path)


class TestPlatformSettings:
    def test_unset_keys_default_to_empty_string(self, settings):
        all_settings = settings.get_all()
        assert all_settings["sms_username"] == ""
        assert all_settings["ai_api_key"] == ""

    def test_set_and_get_roundtrip(self, settings):
        settings.set("sms_username", "myuser")
        assert settings.get("sms_username") == "myuser"

    def test_update_many_only_touches_known_keys(self, settings):
        settings.update_many({"sms_username": "u", "sms_password": "p", "unknown_key": "x"})
        all_settings = settings.get_all()
        assert all_settings["sms_username"] == "u"
        assert all_settings["sms_password"] == "p"
        assert "unknown_key" not in all_settings

    def test_update_many_skips_none_values(self, settings):
        settings.set("sms_sender", "10001234")
        settings.update_many({"sms_sender": None})
        assert settings.get("sms_sender") == "10001234"


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._json_data


@pytest.fixture
def fresh_settings_for_sms(db_path, monkeypatch):
    """sms_service._load_credentials خودش PlatformSettingsManager پیش‌فرض (accounting.db) می‌سازد؛
    برای تست باید آن را به دیتابیس موقت همین تست هدایت کنیم."""
    def fake_load_credentials():
        mgr = PlatformSettingsManager(db_path)
        data = mgr.get_all()
        return {
            "username": data.get("sms_username") or "",
            "password": data.get("sms_password") or "",
            "sender": data.get("sms_sender") or "",
        }
    monkeypatch.setattr(sms_service, "_load_credentials", fake_load_credentials)
    return PlatformSettingsManager(db_path)


class TestSendOtpSms:
    def test_dev_mode_when_credentials_blank(self, fresh_settings_for_sms, monkeypatch):
        called = []
        monkeypatch.setattr(sms_service.requests, "post", lambda *a, **k: called.append(1))
        ok = sms_service.send_otp_sms("09121234567", "123456")
        assert ok is True
        assert called == []  # هیچ درخواست واقعی ارسال نشد

    def test_real_send_success(self, fresh_settings_for_sms, monkeypatch):
        fresh_settings_for_sms.update_many({"sms_username": "u", "sms_password": "p", "sms_sender": "1000"})
        monkeypatch.setattr(sms_service.requests, "post", lambda *a, **k: FakeResponse({"RetStatus": "1"}))
        ok = sms_service.send_otp_sms("09121234567", "123456")
        assert ok is True

    def test_real_send_failure_status(self, fresh_settings_for_sms, monkeypatch):
        fresh_settings_for_sms.update_many({"sms_username": "u", "sms_password": "p", "sms_sender": "1000"})
        monkeypatch.setattr(sms_service.requests, "post", lambda *a, **k: FakeResponse({"RetStatus": "-9"}))
        ok = sms_service.send_otp_sms("09121234567", "123456")
        assert ok is False

    def test_has_sms_credentials(self, fresh_settings_for_sms):
        assert sms_service.has_sms_credentials() is False
        fresh_settings_for_sms.update_many({"sms_username": "u", "sms_password": "p"})
        assert sms_service.has_sms_credentials() is True


class TestSmsConnectionTest:
    def test_blank_credentials_reports_not_configured(self, fresh_settings_for_sms):
        result = sms_service.test_sms_connection()
        assert result["success"] is False

    def test_successful_credit_check(self, fresh_settings_for_sms, monkeypatch):
        fresh_settings_for_sms.update_many({"sms_username": "u", "sms_password": "p"})
        monkeypatch.setattr(sms_service.requests, "post", lambda *a, **k: FakeResponse({"RetStatus": "1", "Value": "5000"}))
        result = sms_service.test_sms_connection()
        assert result["success"] is True
        assert "5000" in result["message"]

    def test_failed_credit_check(self, fresh_settings_for_sms, monkeypatch):
        fresh_settings_for_sms.update_many({"sms_username": "u", "sms_password": "wrong"})
        monkeypatch.setattr(sms_service.requests, "post", lambda *a, **k: FakeResponse({"RetStatus": "-1"}))
        result = sms_service.test_sms_connection()
        assert result["success"] is False
