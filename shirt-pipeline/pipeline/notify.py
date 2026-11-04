"""Tell the user a shirt is ready: Windows pop-up, open the folder, optional email."""
import os
import smtplib
import subprocess
from email.message import EmailMessage
from pathlib import Path

from . import config


def _windows_popup(title: str, text: str):
    # Built-in Windows tray balloon via PowerShell; no extra installs needed.
    t = title.replace("'", "''")
    m = text.replace("'", "''")[:250]
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Information; "
        f"$n.Visible = $true; $n.ShowBalloonTip(10000, '{t}', '{m}', 'Info'); Start-Sleep -Seconds 10; $n.Dispose()"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _email(subject: str, body: str):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, config.GMAIL_ADDRESS, config.NOTIFY_EMAIL_TO
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        s.send_message(msg)


def shirt_ready(label: str, folder: Path, summary: str, log=print):
    title = f"Shirt ready: {label}"
    if os.name == "nt":
        try:
            _windows_popup(title, f"Files are in {folder}")
        except Exception as e:
            log(f"(pop-up failed: {e})")
        if config.OPEN_FOLDER:
            try:
                os.startfile(folder)  # opens the folder in File Explorer
            except Exception:
                pass
    if config.NOTIFY_EMAIL_TO and config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD:
        try:
            _email(title, f"{summary}\n\nFolder: {folder}\n\nWhen it looks right: python run.py approve \"{label}\"")
            log(f"Emailed {config.NOTIFY_EMAIL_TO}")
        except Exception as e:
            log(f"(email failed: {e})")
