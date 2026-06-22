import pytest
from ai_handlers.llm_processor import LLMProcessor, SUPPORTED_PROVIDERS
from core.platform_settings import PlatformSettingsManager


class TestSupportedProviders:
    def test_every_provider_has_label_and_default_model(self):
        for key, info in SUPPORTED_PROVIDERS.items():
            assert info.get("label")
            assert info.get("default_model")

    def test_openai_compatible_providers_have_base_url(self):
        for key, info in SUPPORTED_PROVIDERS.items():
            if info.get("kind") == "openai_compatible":
                assert info.get("base_url", "").startswith("https://")

    def test_anthropic_is_registered(self):
        assert SUPPORTED_PROVIDERS["anthropic"]["kind"] == "anthropic"


@pytest.fixture
def processor_with_db(db_path, monkeypatch):
    """LLMProcessor._load_config مستقیماً PlatformSettingsManager() پیش‌فرض (accounting.db) می‌سازد؛
    برای ایزوله‌بودن تست، آن را به دیتابیس موقت تست هدایت می‌کنیم."""
    import ai_handlers.llm_processor as llm_module

    class _ScopedManager(PlatformSettingsManager):
        def __init__(self):
            super().__init__(db_path)

    monkeypatch.setattr("core.platform_settings.PlatformSettingsManager", _ScopedManager)
    processor = LLMProcessor()
    return processor, PlatformSettingsManager(db_path)


class TestLoadConfig:
    def test_no_config_means_no_api_key(self, processor_with_db, monkeypatch):
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_API_KEY", "")
        processor, _ = processor_with_db
        processor._load_config()
        assert processor.api_key == ""

    def test_db_settings_take_priority_over_env(self, processor_with_db, monkeypatch):
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_API_KEY", "env-key")
        processor, settings = processor_with_db
        settings.update_many({"ai_provider": "groq", "ai_api_key": "db-key", "ai_model": "llama-3.3-70b-versatile"})
        processor._load_config()
        assert processor.api_key == "db-key"
        assert processor.provider == "groq"
        assert processor.model == "llama-3.3-70b-versatile"

    def test_falls_back_to_env_when_db_empty(self, processor_with_db, monkeypatch):
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_API_KEY", "env-key")
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_MODEL", "gpt-4o-mini")
        processor, _ = processor_with_db
        processor._load_config()
        assert processor.api_key == "env-key"
        assert processor.provider == "openai"
        assert processor.model == "gpt-4o-mini"

    def test_model_defaults_to_provider_default_when_unset(self, processor_with_db):
        processor, settings = processor_with_db
        settings.update_many({"ai_provider": "groq", "ai_api_key": "db-key"})
        processor._load_config()
        assert processor.model == SUPPORTED_PROVIDERS["groq"]["default_model"]


class TestNoServiceConfigured:
    def test_process_fails_closed_without_api_key_or_ollama(self, processor_with_db, monkeypatch):
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_API_KEY", "")
        processor, _ = processor_with_db
        processor.use_ollama = False
        result = processor.process("سلام")
        assert result["success"] is False
        assert result["error"] == "no_api_key"

    def test_test_connection_reports_not_configured(self, processor_with_db, monkeypatch):
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_API_KEY", "")
        processor, _ = processor_with_db
        processor.use_ollama = False
        result = processor.test_connection()
        assert result["success"] is False

    def test_classify_business_type_fails_closed(self, processor_with_db, monkeypatch):
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_API_KEY", "")
        processor, _ = processor_with_db
        processor.use_ollama = False
        result = processor.classify_business_type("یک مغازه لباس فروشی")
        assert result["success"] is False

    def test_answer_account_query_fails_closed(self, processor_with_db, monkeypatch):
        monkeypatch.setattr("ai_handlers.llm_processor.OPENAI_API_KEY", "")
        processor, _ = processor_with_db
        processor.use_ollama = False
        result = processor.answer_account_query("مانده حساب صندوق ۱۰۰۰ تومان است.")
        assert result["success"] is False
