import os

import pytest

os.environ.setdefault('PAPERLESS_TOKEN', 'test-token')
os.environ.setdefault('PAPERLESS_BASE_URL', 'http://paperless.local:8000')

from api.app.settings import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_defaults_to_project_values(monkeypatch):
    monkeypatch.delenv('PROJECT_NAME', raising=False)
    monkeypatch.delenv('PROJECT_TAG_NAME', raising=False)
    monkeypatch.delenv('POOL_TAG_NAME', raising=False)
    monkeypatch.setenv('PAPERLESS_BASE_URL', 'http://paperless.local:8000')
    monkeypatch.setenv('PAPERLESS_TOKEN', 'test-token')

    settings = get_settings()

    assert settings.PROJECT_NAME == 'Pool'
    assert settings.PROJECT_TAG_NAME == 'Pool'
    assert settings.POOL_TAG_NAME == 'Pool'
    assert settings.DEFAULT_CURRENCY == 'EUR'
    assert settings.PROJECT_TIMEZONE == 'Europe/Berlin'
    assert settings.PROJECT_CATEGORY_PRESETS == ''


def test_settings_uses_legacy_pool_tag_when_project_tag_missing(monkeypatch):
    monkeypatch.setenv('PAPERLESS_BASE_URL', 'http://paperless.local:8000')
    monkeypatch.setenv('PAPERLESS_TOKEN', 'test-token')
    monkeypatch.setenv('PROJECT_NAME', 'Gartenhaus')
    monkeypatch.delenv('PROJECT_TAG_NAME', raising=False)
    monkeypatch.setenv('POOL_TAG_NAME', 'LegacyGartenhaus')

    settings = get_settings()

    assert settings.PROJECT_NAME == 'Gartenhaus'
    assert settings.PROJECT_TAG_NAME == 'LegacyGartenhaus'
    assert settings.POOL_TAG_NAME == 'LegacyGartenhaus'


def test_project_tag_name_takes_priority_over_legacy_pool_tag(monkeypatch):
    monkeypatch.setenv('PAPERLESS_BASE_URL', 'http://paperless.local:8000')
    monkeypatch.setenv('PAPERLESS_TOKEN', 'test-token')
    monkeypatch.setenv('PROJECT_TAG_NAME', 'NeuesTag')
    monkeypatch.setenv('POOL_TAG_NAME', 'LegacyTag')

    settings = get_settings()

    assert settings.PROJECT_TAG_NAME == 'NeuesTag'
    assert settings.POOL_TAG_NAME == 'NeuesTag'


def test_settings_parse_project_defaults_and_normalize_timezone(monkeypatch):
    monkeypatch.setenv('PAPERLESS_BASE_URL', 'http://paperless.local:8000')
    monkeypatch.setenv('PAPERLESS_TOKEN', 'test-token')
    monkeypatch.setenv('DEFAULT_CURRENCY', 'usd')
    monkeypatch.setenv('PROJECT_TIMEZONE', 'Invalid/Timezone')
    monkeypatch.setenv('PROJECT_CATEGORY_PRESETS', 'Material, Reparatur , , Wartung')

    settings = get_settings()

    assert settings.DEFAULT_CURRENCY == 'USD'
    assert settings.PROJECT_TIMEZONE == 'Europe/Berlin'
    assert settings.PROJECT_CATEGORY_PRESETS == 'Material, Reparatur, Wartung'
