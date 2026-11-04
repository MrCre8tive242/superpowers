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


def _md5(path: Path) -> str:
    import hashlib

    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _upload_file(svc, folder_id: str, f: Path, log=print):
    import mimetypes

    mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    media = MediaFileUpload(str(f), mimetype=mime, resumable=True)
    svc.files().create(body={"name": f.name, "parents": [folder_id]}, media_body=media, fields="id").execute()
    log(f"  uploaded {f.name}")


def upload_folder(files, folder_name: str, log=print):
    """Create a Drive folder, upload the files, share it with anyone who has the link. Returns (link, folder_id)."""
    svc = _service()
    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if config.DRIVE_PARENT_FOLDER_ID:
        meta["parents"] = [config.DRIVE_PARENT_FOLDER_ID]
    folder = svc.files().create(body=meta, fields="id,webViewLink").execute()
    for f in files:
        _upload_file(svc, folder["id"], f, log)
    svc.permissions().create(fileId=folder["id"], body={"type": "anyone", "role": "reader"}).execute()
    return folder["webViewLink"], folder["id"]


def sync_folder(folder_id: str, files, log=print) -> dict:
    """Make an existing Drive folder match the local files (same link). New or changed files are uploaded; a file
    with the same asset number but a different name or content (e.g. your upscaled version) replaces the old one."""
    svc = _service()
    remote, token = [], None
    while True:
        res = svc.files().list(q=f"'{folder_id}' in parents and trashed=false",
                               fields="nextPageToken, files(id,name,md5Checksum)", pageToken=token).execute()
        remote += res.get("files", [])
        token = res.get("nextPageToken")
        if not token:
            break
    by_name = {r["name"]: r for r in remote}
    counts = {"uploaded": 0, "replaced": 0, "unchanged": 0}
    local_numbers = {f.name[:2] for f in files if f.name[:2].isdigit()}
    for f in files:
        same = by_name.get(f.name)
        if same and same.get("md5Checksum") == _md5(f):
            counts["unchanged"] += 1
            continue
        if same:
            svc.files().update(fileId=same["id"], body={"trashed": True}).execute()
        _upload_file(svc, folder_id, f, log)
        counts["replaced" if same else "uploaded"] += 1
    local_names = {f.name for f in files}
    for r in remote:  # an older copy of an asset that now has a different file name
        if r["name"] not in local_names and r["name"][:2] in local_numbers:
            svc.files().update(fileId=r["id"], body={"trashed": True}).execute()
            log(f"  removed old {r['name']}")
    return counts


def upload_file(folder_id: str, f: Path, log=print):
    _upload_file(_service(), folder_id, f, log)
