from __future__ import annotations
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    secret_key: str
    pepper: str
    encryption_key: str
    admin_username: str
    admin_password: str
    environment: str = "production"

    class Config:
        env_file = ".env"


settings = Settings()
