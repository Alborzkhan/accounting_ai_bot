from datetime import datetime, timedelta
import pytest
from core.auth import AuthManager
from core.license_manager import LicenseManager
from database.license_models import User


@pytest.fixture
def auth(db_path):
    return AuthManager(db_path)


class TestSetUserAdmin:
    def test_promote_user_to_admin(self, auth, monkeypatch):
        monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 111111)
        auth.request_otp("09120000001")
        result = auth.verify_otp("09120000001", "111111")
        user_id = result["user_id"]

        assert auth.is_user_admin(user_id) is False
        auth.set_user_admin(user_id, True)
        assert auth.is_user_admin(user_id) is True
        auth.set_user_admin(user_id, False)
        assert auth.is_user_admin(user_id) is False

    def test_set_admin_for_unknown_user_fails(self, auth):
        result = auth.set_user_admin(999999, True)
        assert result["success"] is False


class TestFreeTrialAutoIssuedOnSignup:
    def test_new_signup_gets_free_trial_in_same_db(self, auth, db_path, monkeypatch):
        """رگرسیون: verify_otp قبلاً LicenseManager() را بدون db_path می‌ساخت و همیشه روی
        accounting.db واقعی لایسنس صادر می‌کرد، نه روی دیتابیسی که AuthManager با آن کار می‌کند."""
        monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 222222)
        auth.request_otp("09120000002")
        result = auth.verify_otp("09120000002", "222222")
        assert result["is_new"] is True

        license_manager = LicenseManager(db_path)
        status = license_manager.check_license(result["user_id"])
        assert status["is_valid"] is True
        assert status["plan_type"] == "free_trial"

    def test_returning_user_does_not_get_another_free_trial(self, auth, db_path, monkeypatch):
        monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 333333)
        auth.request_otp("09120000003")
        first = auth.verify_otp("09120000003", "333333")
        assert first["is_new"] is True

        license_manager = LicenseManager(db_path)
        license_manager.generate_license_key(first["user_id"], "monthly")

        # شبیه‌سازی گذشت زمان از ثبت‌نام و آخرین درخواست کد، تا هم معیار is_new (کمتر از ۶۰ ثانیه)
        # واقع‌بینانه باشد و هم کول‌داون ارسال مجدد کد (۶۰ ثانیه) درخواست بعدی را رد نکند
        session = auth.Session()
        try:
            user = session.query(User).filter_by(id=first["user_id"]).first()
            user.created_at = datetime.now() - timedelta(minutes=5)
            user.otp_requested_at = datetime.now() - timedelta(minutes=5)
            session.commit()
        finally:
            session.close()

        monkeypatch.setattr("core.auth.secrets.randbelow", lambda n: 444444)
        auth.request_otp("09120000003")
        second = auth.verify_otp("09120000003", "444444")
        assert second["is_new"] is False

        status = license_manager.check_license(first["user_id"])
        assert status["plan_type"] == "monthly"
