from pydantic import BaseSettings, SecretStr

class Settings(BaseSettings):
    bot_token: SecretStr
    gemini_api_key: SecretStr
    google_api_key: str = ""
    google_cse_id: str = ""
    port: int = 10_000
    max_history: int = 20
    webhook_secret: str = "change_me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
