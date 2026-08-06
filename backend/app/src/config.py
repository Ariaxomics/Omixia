from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = Field("", validation_alias="FLASK_SECRET_KEY")
    SESSION_COOKIE_NAME: str = "session"
    DEBUG: bool = Field(False, validation_alias="FLASK_DEBUG")

    MONGO_URI: str = ""
    OMIXIA_DB_NAME: str = ""

    CACHE_REDIS_URL: str = ""
    REPORTS_BASE_PATH: str = ""

    DEVELOPMENT: bool = False
    TESTING: bool = False

    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_SECURE: bool = False
    ALLOWED_ORIGINS: str = ""
    SPA_BASE_URL: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
