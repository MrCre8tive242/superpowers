"""Shirt extraction pipeline.

  python run.py serve                        MAIN COMMAND: watch the Inbox + open the web page (http://localhost:8765)
  python run.py process "Inbox\\x.jpg" [notes]    run one mockup right now
  python run.py plan-only "Inbox\\x.jpg" [notes]  only write the plan (cheap, no images)
  python run.py redo "x" 3 5                  regenerate layers 3 and 5 of shirt x (same Drive link)
  python run.py approve "x"                   upload Ready\\x to Drive (or sync your changes), email the link
  python run.py models                        list the OpenAI models your account can use
  python run.py test-email                    send yourself a test email
  python run.py install-autostart             start `serve` by itself when Windows starts (+ desktop shortcut)
  python run.py uninstall-autostart

Notes (corrections) go after the file name in quotes, or after " -- " in the file name itself, e.g.
    roots shirt -- the animal on the left is a moose.jpg
Style words in the notes always win: "3D", "cut and sew". Add --review to hold that shirt for your approval.
"""
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from pipeline import config, engine, notify  # noqa: E402


def _quiet_logging_if_hidden():
    """Started hidden at login (pythonw): there is no console, so write to Work\\pipeline.log."""
    if sys.stdout is None or sys.stderr is None:
        config.WORK.mkdir(parents=True, exist_ok=True)
        f = open(config.WORK / "pipeline.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = f


def serve():
    from pipeline import web

    _quiet_logging_if_hidden()
    engine.start_worker()
    threading.Thread(target=engine.watch_inbox, daemon=True, name="inbox-watcher").start()
    engine.log(f"Web page: http://localhost:{config.WEB_PORT}   (Inbox: {config.INBOX})")
    if config.WEB_HOST != "127.0.0.1" and not config.WEB_PASSWORD:
        engine.log("WARNING: WEB_HOST allows other devices but WEB_PASSWORD is empty. Set a password in .env.")
    web.app.run(host=config.WEB_HOST, port=config.WEB_PORT, threaded=True, use_reloader=False)


def startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_autostart():
    if os.name != "nt":
        sys.exit("Auto-start is for Windows.")
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    exe = pyw if pyw.exists() else py
    bat = startup_dir() / "ShirtPipeline.bat"
    bat.write_text(f'@echo off\r\ncd /d "{ROOT}"\r\nstart "" /min "{exe}" "{ROOT / "run.py"}" serve\r\n', encoding="utf-8")
    print(f"Installed: {bat}\nThe pipeline will now start by itself every time you log in to Windows.")
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if desktop.exists():
        (desktop / "Shirt Pipeline.url").write_text(f"[InternetShortcut]\r\nURL=http://localhost:{config.WEB_PORT}\r\n")
        print(f"Desktop shortcut created: {desktop / 'Shirt Pipeline.url'}")
    print("To start it right now without restarting, run:  python run.py serve")


def uninstall_autostart():
    bat = startup_dir() / "ShirtPipeline.bat"
    if bat.exists():
        bat.unlink()
        print("Removed auto-start.")
    else:
        print("Auto-start was not installed.")


def main(a):
    cmd = a[0] if a else ""
    if cmd == "serve":
        serve()
    elif cmd in ("process", "plan-only") and len(a) >= 2:
        engine.run_guarded(Path(a[1]).stem, lambda: engine.process(Path(a[1]), plan_only=(cmd == "plan-only"),
                                                                    hint=" ".join(a[2:])))
    elif cmd == "redo" and len(a) >= 3:
        engine.run_guarded(a[1], lambda: engine.redo(a[1], [int(x) for x in a[2:]]))
    elif cmd in ("approve", "sync") and len(a) >= 2:
        engine.run_guarded(a[1], lambda: engine.approve(a[1]))
    elif cmd == "models":
        from openai import OpenAI
        ids = sorted(m.id for m in OpenAI().models.list())
        print("Image models:", [i for i in ids if "image" in i] or "none")
        print("Vision/chat models (for PLANNER_MODEL):", [i for i in ids if i.startswith(("gpt-4", "gpt-5", "o"))])
    elif cmd == "test-email":
        notify.send_test(engine.log)
    elif cmd == "install-autostart":
        install_autostart()
    elif cmd == "uninstall-autostart":
        uninstall_autostart()
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        engine.log("Stopped.")
    except Exception as e:  # already announced by run_guarded; show a clean message instead of a traceback
        sys.exit(f"\nSTOPPED: {e}")
