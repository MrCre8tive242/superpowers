"""Shirt extraction pipeline.

  python run.py watch                       watch Inbox, process every new mockup, stop at review
  python run.py process "Inbox\\x.jpg" [hint]   plan -> generate -> upscale one mockup
  python run.py plan-only "Inbox\\x.jpg" [hint] only write the plan (cheap, no images)
  python run.py redo x 3 5                  regenerate assets 3 and 5 of shirt x, then upscale them
  python run.py approve x                   upload Work\\x\\final to Drive, print the share link
  python run.py probe-topaz                 show Gigapixel's command-line options

Hints: put corrections after the file name in quotes, or save a text file next to the mockup with the
same name (Inbox\\x.txt). Example: "The animal on the left is a moose. CRUSADERS is on the left sleeve."
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


def read_hint(mockup: Path, hint: str) -> str:
    txt = mockup.with_suffix(".txt")
    if txt.exists():
        hint = (hint + " " + txt.read_text(encoding="utf-8")).strip()
    return hint


def show_plan(plan):
    log(f"Mode: {plan['mode']}{' (assumed)' if plan.get('assumed_mode') else ''}  Assets: {len(plan['assets'])}")
    for a in plan["assets"]:
        w, h = a["print_inches"]
        log(f"  {a['n']:02d} {a['name']} [{a['kind']}, {w:g}x{h:g} in] {a.get('what', '')}")
    for note in plan.get("notes", []):
        log(f"NOTE: {note}")


def process(mockup: Path, plan_only=False, hint=""):
    if not mockup.exists():
        sys.exit(f"File not found: {mockup}\nTip: put the name in quotes, and check it with: dir Inbox")
    name = generator.slug(mockup.stem)
    wd = config.WORK / name
    wd.mkdir(parents=True, exist_ok=True)
    hint = read_hint(mockup, hint)
    log(f"Planning {name} ..." + (f"  (hint: {hint})" if hint else ""))
    plan = planner.plan(mockup, hint, log)
    plan["mockup"] = str(mockup.resolve())
    plan["label"] = mockup.stem
    (wd / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    show_plan(plan)
    if plan_only:
        log(f"Plan saved to {wd / 'plan.json'}. Run 'process' when it looks right.")
        return
    build(wd, plan, plan["assets"])


def build(wd: Path, plan: dict, assets: list):
    mockup = Path(plan["mockup"])
    results = generator.generate_all(mockup, assets, wd / "raw", log)
    final = wd / "final"
    status_file = wd / "status.json"
    status = json.loads(status_file.read_text()) if status_file.exists() else {"failed": []}
    failed = set(status.get("failed", []))
    log("Upscaling ...")
    for a in assets:
        r = results[a["n"]]
        if not r["path"]:
            failed.add(a["name"])
            continue
        try:
            for old in final.glob(Path(r["path"]).stem + ".*"):
                old.unlink()  # replace an older version of this asset
            upscaler.upscale_asset(Path(r["path"]), a, final, log)
            failed.discard(a["name"])
        except Exception as e:
            failed.add(a["name"])
            log(f"  UPSCALE FAILED {a['name']}: {e}")
    status.update(name=wd.name, label=plan.get("label", wd.name), failed=sorted(failed), approved=False)
    status_file.write_text(json.dumps(status, indent=2), encoding="utf-8")
    log(f"DONE. Review the files in {final}")
    if failed:
        log(f"Failed assets: {sorted(failed)}  ->  python run.py redo {wd.name} <numbers>")
    log(f"When happy: python run.py approve {wd.name}")


def redo(name: str, numbers):
    wd = config.WORK / name
    plan = json.loads((wd / "plan.json").read_text(encoding="utf-8"))
    picked = [a for a in plan["assets"] if a["n"] in numbers]
    if not picked:
        sys.exit(f"No assets numbered {numbers} in {name}")
    for a in picked:  # delete old raw file so it is generated fresh
        for f in (wd / "raw").glob(f"{a['n']:02d}_*"):
            f.unlink()
    build(wd, plan, picked)


def approve(name: str):
    from pipeline import drive

    wd = config.WORK / name
    files = sorted(p for p in (wd / "final").glob("*") if p.suffix.lower() in upscaler.IMG_EXT)
    if not files:
        sys.exit(f"No finished files in {wd / 'final'}")
    st_file = wd / "status.json"
    st = json.loads(st_file.read_text()) if st_file.exists() else {}
    if st.get("failed"):
        log(f"WARNING: these assets failed and are missing: {st['failed']}")
    label = st.get("label", name)
    link = drive.upload_folder(files, label, log)
    with open(config.WORK / "links.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([dt.datetime.now().isoformat(timespec="seconds"), label, link])
    st.update(approved=True, link=link)
    st_file.write_text(json.dumps(st, indent=2), encoding="utf-8")
    log(f"SHARE LINK for {label}: {link}")


def watch():
    config.INBOX.mkdir(parents=True, exist_ok=True)
    config.WORK.mkdir(parents=True, exist_ok=True)
    done = config.WORK / ".processed"
    seen = set(done.read_text().splitlines()) if done.exists() else set()
    log(f"Watching {config.INBOX} ... drop a mockup in (Ctrl+C to stop).")
    while True:
        for f in sorted(config.INBOX.iterdir()):
            if f.suffix.lower() in IMG_EXT and f.name not in seen:
                size = -1
                while size != f.stat().st_size:  # wait until the file finishes copying
                    size = f.stat().st_size
                    time.sleep(2)
                try:
                    process(f)
                except Exception as e:
                    log(f"ERROR on {f.name}: {e}")
                seen.add(f.name)
                done.write_text("\n".join(sorted(seen)))
        time.sleep(5)


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    try:
        if cmd == "watch":
            watch()
        elif cmd in ("process", "plan-only") and len(a) >= 2:
            process(Path(a[1]), plan_only=(cmd == "plan-only"), hint=" ".join(a[2:]))
        elif cmd == "redo" and len(a) >= 3:
            redo(a[1], [int(x) for x in a[2:]])
        elif cmd == "approve" and len(a) >= 2:
            approve(a[1])
        elif cmd == "probe-topaz":
            upscaler.probe()
        else:
            print(__doc__)
    except KeyboardInterrupt:
        log("Stopped.")
