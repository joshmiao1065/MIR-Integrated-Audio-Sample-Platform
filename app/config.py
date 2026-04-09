from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8")

    DATABASE_URL: str

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_STORAGE_BUCKET: str = "audio-previews"

    FREESOUND_API_KEY: str
    # OAuth client credentials — only required for user-delegated flows, not token-based scraping
    FREESOUND_CLIENT_ID: Optional[str] = None
    FREESOUND_CLIENT_SECRET: Optional[str] = None

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    # Google Drive storage — uses OAuth2 with your personal Google account so that
    # uploads count against your Google One quota (1 TB) rather than a service
    # account's separate 15 GB quota.
    #
    # To obtain these values, run once:
    #   python -m scripts.gdrive_auth --client-id <ID> --client-secret <SECRET>
    #
    # Create a folder in your personal Drive and paste its ID (from the URL) below.
    GDRIVE_FOLDER_ID: str = ""
    # OAuth2 "Desktop app" credentials from Google Cloud Console.
    GDRIVE_CLIENT_ID: Optional[str] = None
    GDRIVE_CLIENT_SECRET: Optional[str] = None
    # Refresh token produced by scripts/gdrive_auth.py — never expires unless revoked.
    GDRIVE_REFRESH_TOKEN: Optional[str] = None


settings = Settings()
