"""Google Drive storage service for audio files.

Audio previews (150–300 KB MP3) are uploaded to a shared Google Drive folder
and made publicly accessible via a direct-download link. This conserves
Supabase's free-tier Storage quota (1 GB) by keeping only vector embeddings
and relational metadata in Supabase.

Setup
-----
1. In Google Cloud Console, create a project and enable the Drive API.
2. Under IAM → Service Accounts, create a service account (no GCP roles needed).
3. Generate and download a JSON key for that service account.
4. In your Google Drive, create a folder for audio previews.
5. Share that folder with the service account's email address (Editor role).
6. Copy the folder ID from the Drive URL (the long alphanumeric string after
   /folders/) and set it as GDRIVE_FOLDER_ID in .env.
7. Set either:
   - GDRIVE_SERVICE_ACCOUNT_FILE  — path to the JSON key file (local dev)
   - GDRIVE_SERVICE_ACCOUNT_JSON  — the JSON key contents as a single-line
                                    string (Railway / cloud deployment)

Public access
-------------
After every upload, the file is granted 'anyone with link → reader' permission.
The stored file_url is a direct download link that Wavesurfer.js can stream:
  https://drive.google.com/uc?export=download&id=<FILE_ID>
Google Drive redirects this to drive.usercontent.google.com which serves
Access-Control-Allow-Origin: * for publicly shared files, so browser-side
audio playback works without a backend proxy.
"""
import json
import logging
from functools import lru_cache

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

from app.config import settings

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Direct-download pattern — final redirect target serves CORS: * for public files.
_DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={file_id}"


@lru_cache(maxsize=1)
def _service():
    """Lazy singleton: build the Drive v3 service once per process."""
    if settings.GDRIVE_SERVICE_ACCOUNT_JSON:
        info = json.loads(settings.GDRIVE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPES
        )
    elif settings.GDRIVE_SERVICE_ACCOUNT_FILE:
        creds = service_account.Credentials.from_service_account_file(
            settings.GDRIVE_SERVICE_ACCOUNT_FILE, scopes=_SCOPES
        )
    else:
        raise RuntimeError(
            "Google Drive credentials not configured. "
            "Set GDRIVE_SERVICE_ACCOUNT_JSON or GDRIVE_SERVICE_ACCOUNT_FILE in .env."
        )
    return build("drive", "v3", credentials=creds)


def upload_audio(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    """Upload audio bytes to the configured Google Drive folder.

    The file is immediately made publicly readable so the frontend can stream it.

    Returns
    -------
    (file_id, public_download_url)
        file_id  — the Drive file ID, stored in samples.gdrive_file_id for
                   efficient deletion later.
        public_download_url — stored in samples.file_url; used by both the
                   frontend (Wavesurfer.js) and the MIR pipeline (httpx download).
    """
    svc = _service()

    file_metadata: dict = {"name": filename}
    if settings.GDRIVE_FOLDER_ID:
        file_metadata["parents"] = [settings.GDRIVE_FOLDER_ID]

    media = MediaInMemoryUpload(audio_bytes, mimetype="audio/mpeg", resumable=False)
    uploaded = svc.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()
    file_id: str = uploaded["id"]

    # Grant public read so the browser can stream without auth.
    svc.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return file_id, _DOWNLOAD_URL.format(file_id=file_id)


def delete_file(file_id: str) -> None:
    """Permanently delete a file from Google Drive.

    Swallows exceptions and logs a warning — deletion failures should never
    block a prune run.
    """
    try:
        _service().files().delete(fileId=file_id).execute()
        log.debug("GDrive deleted file %s", file_id)
    except Exception as exc:
        log.warning("GDrive delete failed for %s: %s", file_id, exc)
