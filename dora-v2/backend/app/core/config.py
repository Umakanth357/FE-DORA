from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    mysql_host:     str = "localhost"
    mysql_port:     int = 3306
    mysql_user:     str = "root"
    mysql_password: str = "dora_secret"
    mysql_database: str = "dora_platform"

    # App
    secret_key:               str = "change_me_in_production"
    max_upload_mb:            int = 50
    incident_link_window_hrs: int = 24
    dora_window_days:         int = 90

    # Frontend CORS
    cors_origins: str = "*"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
