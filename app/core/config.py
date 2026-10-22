from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Acme Hospital Clinic Booking System"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "RESTful API for Acme Hospital Clinic appointment scheduling."
    API_V1_STR: str = "/api/v1"
    TIMEZONE: str = "Africa/Nairobi"
    
    # Database URL
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/acme_booking"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
