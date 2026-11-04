"""Step 4: upload the finished folder to Google Drive and make it link-shareable."""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from . import config

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _service():
    creds = None
    if config.GOOGLE_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(config.GOOGLE_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(config.GOOGLE_CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=0)  # sign in as Cre8tiveminds242@gmail.com once
        config.GOOGLE_TOKEN.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload_folder(local_dir: Path, folder_name: str, log=print) -> str:
    svc = _service()
    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if config.DRIVE_PARENT_FOLDER_ID:
        meta["parents"] = [config.DRIVE_PARENT_FOLDER_ID]
    folder = svc.files().create(body=meta, fields="id,webViewLink").execute()
    for f in sorted(local_dir.glob("*.png")):
        media = MediaFileUpload(str(f), mimetype="image/png", resumable=True)
        svc.files().create(
            body={"name": f.name, "parents": [folder["id"]]}, media_body=media, fields="id"
        ).execute()
        log(f"  uploaded {f.name}")
    svc.permissions().create(
        fileId=folder["id"], body={"type": "anyone", "role": "reader"}
    ).execute()
    return folder["webViewLink"]
