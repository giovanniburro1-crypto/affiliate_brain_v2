import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/db")
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", 8001))
    debug: bool = False
    cors_origins: str = "*"
    
    @property
    def cors_origins_list(self) -> List[str]:
        return self.cors_origins.split(",")
    
    class Config:
        env_file = ".env"

settings = Settings()
