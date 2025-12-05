from pydantic_settings import BaseSettings
from pydantic import SecretStr

class Settings(BaseSettings):
    bot_token: SecretStr
    gemini_api_key: SecretStr
    google_search_api_key: str = ""   # как в Render
    google_cse_id: str = ""
    port: int = 10_000
    max_history: int = 20
    webhook_secret: str = "change_me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # алиас для старого кода
    @property
    def google_api_key(self) -> str:
        return self.google_search_api_key

settings = Settings()