from functools import lru_cache
import os

from pydantic import Field, ValidationError
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    from pydantic import BaseModel  # type: ignore

    SettingsConfigDict = dict  # type: ignore

    class BaseSettings(BaseModel):  # type: ignore
        def __init__(self, **data):
            annotations = getattr(self.__class__, '__annotations__', {})
            for field_name in annotations:
                if field_name not in data and field_name in os.environ:
                    data[field_name] = os.environ[field_name]
            super().__init__(**data)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore')

    PAPERLESS_BASE_URL: str
    PAPERLESS_TOKEN: str
    POOL_TAG_NAME: str = Field(default='Pool')
    SYNC_PAGE_SIZE: int = Field(default=100)
    SYNC_LOOKBACK_DAYS: int = Field(default=365)
    DATABASE_URL: str = Field(default='sqlite:////data/app.db')

    SCHEDULER_ENABLED: bool = Field(default=False)
    SCHEDULER_INTERVAL_MINUTES: int = Field(default=360)
    SCHEDULER_RUN_ON_STARTUP: bool = Field(default=True)


@lru_cache
def get_settings() -> Settings:
    try:
        settings = Settings()
    except ValidationError as exc:
        required = []
        for err in exc.errors():
            if err.get('type') == 'missing' and err.get('loc'):
                required.append(str(err['loc'][0]))
        missing = sorted(set(required))
        if missing:
            raise RuntimeError(
                'Fehlende Pflicht-ENV für API-Start: '
                + ', '.join(missing)
                + '. Bitte im Portainer Stack unter Environment setzen.'
            ) from exc
        raise RuntimeError(f'Ungültige API-Umgebungsvariablen: {exc}') from exc

    missing_empty = [
        key
        for key in ('PAPERLESS_BASE_URL', 'PAPERLESS_TOKEN')
        if not getattr(settings, key, '').strip()
    ]
    if missing_empty:
        raise RuntimeError(
            'Leere Pflicht-ENV für API-Start: '
            + ', '.join(missing_empty)
            + '. Bitte im Portainer Stack unter Environment setzen.'
        )
    return settings
