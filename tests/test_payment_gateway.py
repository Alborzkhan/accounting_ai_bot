import pytest
from core.payment_gateway import PaymentGateway
from core.platform_settings import PlatformSettingsManager


class FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data


@pytest.fixture
def gateway_with_db(db_path, monkeypatch):
    """PaymentGateway._load_config مستقیماً PlatformSettingsManager() پیش‌فرض (accounting.db) می‌سازد؛
    برای ایزوله‌بودن تست، آن را به دیتابیس موقت تست هدایت می‌کنیم."""
    class _ScopedManager(PlatformSettingsManager):
        def __init__(self):
            super().__init__(db_path)

    monkeypatch.setattr("core.platform_settings.PlatformSettingsManager", _ScopedManager)
    gateway = PaymentGateway(db_path)
    return gateway, PlatformSettingsManager(db_path)


class TestLoadConfig:
    def test_falls_back_to_env_when_db_empty(self, gateway_with_db, monkeypatch):
        monkeypatch.setattr("core.payment_gateway.ZARINPAL_MERCHANT_ID", "env-merchant")
        monkeypatch.setattr("core.payment_gateway.ZARINPAL_CALLBACK_URL", "https://env.example.com/cb")
        gateway, _ = gateway_with_db
        gateway._load_config()
        assert gateway.merchant_id == "env-merchant"
        assert gateway.callback_url == "https://env.example.com/cb"

    def test_db_settings_take_priority_over_env(self, gateway_with_db, monkeypatch):
        monkeypatch.setattr("core.payment_gateway.ZARINPAL_MERCHANT_ID", "env-merchant")
        gateway, settings = gateway_with_db
        settings.update_many({
            "zarinpal_merchant_id": "db-merchant",
            "zarinpal_callback_url": "https://db.example.com/cb",
        })
        gateway._load_config()
        assert gateway.merchant_id == "db-merchant"
        assert gateway.callback_url == "https://db.example.com/cb"


class TestConnectionTest:
    def test_blank_merchant_id_reports_not_configured(self, gateway_with_db, monkeypatch):
        monkeypatch.setattr("core.payment_gateway.ZARINPAL_MERCHANT_ID", "")
        gateway, _ = gateway_with_db
        result = gateway.test_connection()
        assert result["success"] is False

    def test_successful_request_reports_success(self, gateway_with_db, monkeypatch):
        gateway, settings = gateway_with_db
        settings.set("zarinpal_merchant_id", "db-merchant")
        monkeypatch.setattr(
            "core.payment_gateway.requests.post",
            lambda *a, **k: FakeResponse({"data": {"code": 100, "authority": "A123"}}),
        )
        result = gateway.test_connection()
        assert result["success"] is True

    def test_failed_request_reports_failure(self, gateway_with_db, monkeypatch):
        gateway, settings = gateway_with_db
        settings.set("zarinpal_merchant_id", "bad-merchant")
        monkeypatch.setattr(
            "core.payment_gateway.requests.post",
            lambda *a, **k: FakeResponse({"errors": {"message": "merchant نامعتبر"}}),
        )
        result = gateway.test_connection()
        assert result["success"] is False


class TestCreatePaymentRequestUsesConfiguredMerchant:
    def test_uses_db_configured_merchant_id(self, gateway_with_db, monkeypatch):
        gateway, settings = gateway_with_db
        settings.update_many({"zarinpal_merchant_id": "db-merchant", "zarinpal_callback_url": "https://db.example.com/cb"})
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured.update(json)
            return FakeResponse({"data": {"code": 100, "authority": "A999"}})

        monkeypatch.setattr("core.payment_gateway.requests.post", fake_post)
        result = gateway.create_payment_request(user_id=1, amount=5000000, plan_type="monthly")
        assert result["success"] is True
        assert captured["merchant_id"] == "db-merchant"
        assert captured["callback_url"] == "https://db.example.com/cb"
