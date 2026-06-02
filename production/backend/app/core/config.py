from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./hr_system.db"
    SECRET_KEY: str = "super-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    HR_USERNAME: str = "admin"
    HR_PASSWORD: str = "TravelGate2026!"

    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    HR_MANAGER_EMAIL: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()