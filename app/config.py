from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Metrics Monitor Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    DATABASE_URL: str = "sqlite+aiosqlite:///./metrics_monitor.db"
    
    CORS_ORIGINS: List[str] = ["*"]
    
    NOTIFICATION_EMAIL_ENABLED: bool = False
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    
    NOTIFICATION_WEBHOOK_ENABLED: bool = False
    
    SILENT_HOURS_START: int = 22
    SILENT_HOURS_END: int = 8
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()