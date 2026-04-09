"""Google Drive storage service for audio files.

Audio previews (150–300 KB MP3) are uploaded to a folder in the developer's
personal Google Drive and made publicly accessible via a direct-download link.
This conserves Supabase's free-tier Storage quota (1 GB) by keeping only vector
embeddings and relational metadata in Supabase.

Because a *personal* Google account is used (Google One 1 TB plan), OAuth2
credentials are required instead of a service account.  Service accounts have
their own separate 15 GB Drive quota and would NOT draw from Google One storage.

Setup
-----
1. In Google Cloud Console (console.cloud.google.com), create a free project.
2. Enable the Google Drive API for that project.
3. Under APIs & Services → Credentials, create an OAuth 2.0 Client ID.
   Application type: **Desktop app**.
4. Download the client JSON or note the Client ID and Client Secret.
5. Run the one-time authorisation script:
       python -m scripts.gdrive_auth --client-id <ID> --client-secret <SECRET>
   Follow the prompts: open the printed URL in your browser, log in with the
   Google account that has Google One, approve Drive access, then paste the
   authorisation code back into the terminal.
6. Copy the printed GDRIVE_REFRESH_TOKEN value into .env.
7. In your personal Google Drive, create a folder for audio previews.
   Copy the folder ID from the URL (/folders/<ID>) → set as GDRIVE_FOLDER_ID.

Environment variables (all required)
--------------------------------------
GDRIVE_CLIENT_ID       — OAuth2 client ID from Cloud Console
GDRIVE_CLIENT_SECRET   — OAuth2 client secret from Cloud Console
GDRIVE_REFRESH_TOKEN   — long-lived token from scripts/gdrive_auth.py
GDRIVE_FOLDER_ID       — Drive folder ID where audio files are uploaded

For Railway / cloud deployment, set the same four env vars in the Railway
dashboard.  No JSON key file is needed — the refresh token is the only secret
that must be stored.

Public access
-------------
After every upload, the file is granted 'anyone with link → reader' permission.
The stored file_url is a direct-download link that Wavesurfer.js can stream:
  https://drive.google.com/uc?export=download&id=<FILE_ID>
Google Drive redirects this to drive.usercontent.google.com which serves
Access-Control-Allow-Origin: * for publicly shared files, so browser-side
audio playback works without a backend proxy.

Token refresh
-------------
OAuth2 access tokens expire after 1 hour.  The google-api-python-client library
refreshes them automatically using the stored refresh token — no manual
intervention is required.  The refresh token itself does not expire unless:
  - You revoke it in your Google Account security settings, or
  - It is unused for 6 consecutive months.
"""
import logging
from functools import lru_cache

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

from app.config import settings

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Direct-download URL — final redirect target serves CORS: * for public files.
_DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={file_id}"


@lru_cache(maxsize=1)
def _service():
    """Lazy singleton: build the Drive v3 API client once per process.

    Uses OAuth2 credentials tied to the developer's personal Google account so
    that file storage counts against their Google One quota.  The access token
    is refreshed automatically by the google-auth library whenever it expires.
    """
    missing = [
        name
        for name, val in [
            ("GDRIVE_CLIENT_ID", settings.GDRIVE_CLIENT_ID),
            ("GDRIVE_CLIENT_SECRET", settings.GDRIVE_CLIENT_SECRET),
            ("GDRIVE_REFRESH_TOKEN", settings.GDRIVE_REFRESH_TOKEN),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Google Drive OAuth2 credentials not configured. "
            f"Missing .env vars: {', '.join(missing)}. "
            f"Run  python -m scripts.gdrive_auth  once to obtain a refresh token."
        )

    creds = Credentials(
        token=None,  # no cached access token — will be fetched on first API call
        refresh_token=settings.GDRIVE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GDRIVE_CLIENT_ID,
        client_secret=settings.GDRIVE_CLIENT_SECRET,
        scopes=_SCOPES,
    )

    # Eagerly refresh so that any misconfiguration surfaces at startup rather
    # than mid-upload.  This also populates creds.token for the first request.
    creds.refresh(Request())
    log.debug("Google Drive OAuth2 access token obtained successfully.")

    return build("drive", "v3", credentials=creds)


def upload_audio(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    """Upload audio bytes to the configured Google Drive folder.

    The file is immediately made publicly readable so the frontend can stream it.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio data (MP3 or any format supported by the Drive API).
    filename : str
        Destination filename in Drive (e.g. ``"freesound-12345.mp3"``).

    Returns
    -------
    (file_id, public_download_url)
        file_id              — Drive file ID; stored in samples.gdrive_file_id
                               for efficient deletion later.
        public_download_url  — stored in samples.file_url; used by the frontend
                               (Wavesurfer.js) and the MIR pipeline (httpx).
    """
    svc = _service()

    file_metadata: dict = {"name": filename}
    if settings.GDRIVE_FOLDER_ID:
        file_metadata["parents"] = [settings.GDRIVE_FOLDER_ID]

    media = MediaInMemoryUpload(audio_bytes, mimetype="audio/mpeg", resumable=False)
    uploaded = (
        svc.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
        )
        .execute()
    )
    file_id: str = uploaded["id"]

    # Grant public read so the browser can stream without authentication.
    svc.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    log.debug("GDrive uploaded %s → %s", filename, file_id)
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
