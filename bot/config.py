from pydantic_settings import BaseSettings
from pydantic import SecretStr


class Settings(BaseSettings):
    bot_token: SecretStr
    gemini_api_key: SecretStr
    google_search_api_key: str = ""
    google_cse_id: str = ""
    webhook_secret: str = "change_me"
    port: int = 10000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()