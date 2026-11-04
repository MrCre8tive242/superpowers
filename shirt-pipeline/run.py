"""Shirt extraction pipeline.

  python run.py watch                 # watch Inbox/, process every new mockup, stop at review
  python run.py process Inbox\\x.png  # run one mockup (plan -> generate -> upscale)
  python run.py approve x             # upload Work\\x\\final to Drive, print the share link
  python run.py plan-only Inbox\\x.png  # just write plan.json (cheap test, no images)
  python run.py probe-topaz           # show Gigapixel CLI flags
"""
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

from pipeline import config, generator, planner, upscaler

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def process(mockup: Path, plan_only=False):
    name = generator.slug(mockup.stem)
    wd = config.WORK / name
    wd.mkdir(parents=True, exist_ok=True)
    log(f"Planning {name} ...")
    plan = planner.plan(mockup)
    (wd / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    log(f"Mode: {plan.get('mode')}  Assets: {len(plan['assets'])}")
    for note in plan.get("notes", []):
        log(f"NOTE: {note}")
    if plan_only:
        return
    results = generator.generate_all(mockup, plan["assets"], wd / "raw", log)
    final = wd / "final"
    failed = []
    log("Upscaling ...")
    for a in plan["assets"]:
        r = results[a["n"]]
        if not r["path"]:
            failed.append(a["name"])
            continue
        try:
            upscaler.upscale_asset(Path(r["path"]), a, final, log)
        except Exception as e:
            failed.append(a["name"])
            log(f"  UPSCALE FAILED {a['name']}: {e}")
    status = {"name": name, "failed": failed, "approved": False}
    (wd / "status.json").write_text(json.dumps(status), encoding="utf-8")
    log(f"DONE. Review the files in {final}")
    if failed:
        log(f"Failed assets (redo by hand or rerun): {failed}")
    log(f"When happy: python run.py approve {name}")


def approve(name: str):
    from pipeline import drive

    wd = config.WORK / name
    link = drive.upload_folder(wd / "final", name, log)
    with open(config.WORK / "links.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([dt.datetime.now().isoformat(timespec="seconds"), name, link])
    st = wd / "status.json"
    if st.exists():
        d = json.loads(st.read_text())
        d["approved"], d["link"] = True, link
        st.write_text(json.dumps(d))
    log(f"SHARE LINK for {name}: {link}")


def watch():
    config.INBOX.mkdir(parents=True, exist_ok=True)
    done = config.WORK / ".processed"
    done.parent.mkdir(parents=True, exist_ok=True)
    seen = set(done.read_text().splitlines()) if done.exists() else set()
    log(f"Watching {config.INBOX} ... drop a mockup in.")
    while True:
        for f in sorted(config.INBOX.iterdir()):
            if f.suffix.lower() in IMG_EXT and f.name not in seen:
                time.sleep(2)  # let the file finish copying
                try:
                    process(f)
                except Exception as e:
                    log(f"ERROR on {f.name}: {e}")
                seen.add(f.name)
                done.write_text("\n".join(sorted(seen)))
        time.sleep(5)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "watch":
        watch()
    elif cmd == "process":
        process(Path(sys.argv[2]))
    elif cmd == "plan-only":
        process(Path(sys.argv[2]), plan_only=True)
    elif cmd == "approve":
        approve(sys.argv[2])
    elif cmd == "probe-topaz":
        upscaler.probe()
    else:
        print(__doc__)
