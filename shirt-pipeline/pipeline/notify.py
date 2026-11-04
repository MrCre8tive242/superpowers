"""Tell the user a shirt is ready (or failed): Windows pop-up, open the folder, optional email with the preview."""
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


def email_configured() -> bool:
    return bool(config.NOTIFY_EMAIL_TO and config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD)


def _email(subject: str, body: str, attachments=()):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, config.GMAIL_ADDRESS, config.NOTIFY_EMAIL_TO
    msg.set_content(body)
    for p in attachments:
        p = Path(p)
        if p.exists() and p.stat().st_size < 15_000_000:
            sub = "jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else p.suffix.lower().lstrip(".") or "octet-stream"
            msg.add_attachment(p.read_bytes(), maintype="image", subtype=sub, filename=p.name)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        s.send_message(msg)


def send_test(log=print) -> bool:
    """python run.py test-email"""
    if not email_configured():
        log("Email is not set up: fill NOTIFY_EMAIL_TO, GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env")
        return False
    try:
        _email("Shirt pipeline: test email", "If you can read this, email alerts work.")
        log(f"Test email sent to {config.NOTIFY_EMAIL_TO}")
        return True
    except Exception as e:
        log(f"Email failed: {e}")
        return False


def shirt_ready(label: str, folder: Path, summary: str, log=print, link: str = None, preview: Path = None,
                needs_look: bool = False):
    """Pop-up + (optionally) open the folder + email. `needs_look` = something failed its check."""
    title = ("CHECK NEEDED: " if needs_look else "Shirt ready: ") + label
    if os.name == "nt":
        try:
            _windows_popup(title, link or f"Files are in {folder}")
        except Exception as e:
            log(f"(pop-up failed: {e})")
        if config.OPEN_FOLDER and not link:
            try:
                os.startfile(folder)  # opens the folder in File Explorer
            except Exception:
                pass
    if email_configured():
        body = []
        if link:
            body += [f"Share link (send this to the customer once you're happy):", link, ""]
        body += [summary, "", f"Files on your PC: {folder}"]
        if not link:
            body.append(f'When it looks right: python run.py approve "{label}"')
        try:
            _email(title, "\n".join(body), [preview] if preview else [])
            log(f"Emailed {config.NOTIFY_EMAIL_TO}")
        except Exception as e:
            log(f"(email failed: {e})")


def failed(label: str, error: str, log=print):
    title = f"FAILED: {label}"
    if os.name == "nt":
        try:
            _windows_popup(title, error[:200])
        except Exception:
            pass
    if email_configured():
        try:
            _email(title, f"The shirt '{label}' could not be finished.\n\n{error}\n\nIt will not retry by itself. "
                          f"Fix the problem, then drop the mockup in again.")
            log(f"Emailed failure notice to {config.NOTIFY_EMAIL_TO}")
        except Exception as e:
            log(f"(email failed: {e})")
