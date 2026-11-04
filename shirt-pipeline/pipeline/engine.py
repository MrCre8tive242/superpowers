"""The whole job for one shirt, plus the queue that the folder watcher and the web page both feed.

mockup -> plan -> generate + check + retry -> Ready\\<shirt>\\ -> (hands-off) upload to Drive -> email + preview
"""
import csv
import datetime as dt
import json
import queue
import re
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path

from . import config, generator, llm, notify, planner, preview, upscaler

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_print_lock = threading.Lock()
_ctx = threading.local()  # lets log lines from a background job show up on the web page


# ---------------------------------------------------------------- logging / job state
def log(msg):
    line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
    try:
        with _print_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
    except Exception:  # no console (started hidden at login)
        pass
    sink = getattr(_ctx, "sink", None)
    if sink is not None:
        sink["lines"].append(line)
        del sink["lines"][:-400]


def set_phase(phase: str):
    sink = getattr(_ctx, "sink", None)
    if sink is not None:
        sink["phase"] = phase


# ---------------------------------------------------------------- names, hints, flags
def safe_label(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip(" .") or "shirt"


def split_name(stem: str):
    """'roots shirt -- 3D, moose on left'  ->  ('roots shirt', '3D, moose on left')"""
    if " -- " in stem:
        label, hint = stem.split(" -- ", 1)
        return safe_label(label), hint.strip()
    return safe_label(stem), ""


def parse_flags(hint: str):
    """--review / --auto switch hands-off mode for one shirt. Returns (hint without flags, set of flags)."""
    flags = set(re.findall(r"--(review|auto)\b", hint, re.I))
    return re.sub(r"\s*--(review|auto)\b", "", hint, flags=re.I).strip(), {f.lower() for f in flags}


def read_txt_hint(mockup: Path) -> str:
    txt = mockup.with_suffix(".txt")
    return txt.read_text(encoding="utf-8", errors="ignore").strip() if txt.exists() else ""


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def find_shirt(name: str):
    """Accept the shirt name ('roots shirt') or its work folder name ('roots_shirt')."""
    wd = config.WORK / generator.slug(safe_label(name))
    if not (wd / "plan.json").exists():
        raise FileNotFoundError(f"No shirt called '{name}' in {config.WORK}")
    return wd, _json(wd / "plan.json", {})


def ready_dir(plan) -> Path:
    return config.READY / plan["label"]


def show_plan(plan):
    log(f"Mode: {plan['mode']}  Assets: {len(plan['assets'])}")
    if plan.get("mode_reason"):
        log(f"  mode chosen because: {plan['mode_reason']}")
        log('  (wrong? add "3D" or "cut and sew" to the notes)')
    for a in plan["assets"]:
        w, h = a["print_inches"]
        hard = " *" if a.get("hard") else ""
        log(f"  {a['n']:02d} {a['name']} [{a['kind']}, {w:g}x{h:g} in]{hard} {a.get('what', '')[:110]}")
    for note in plan.get("notes", []):
        log(f"NOTE: {note}")


# ---------------------------------------------------------------- the pipeline
def process(mockup, plan_only=False, hint=""):
    mockup = Path(mockup)
    if not mockup.exists():
        raise FileNotFoundError(f"File not found: {mockup}\nTip: put the name in quotes, and check it with: dir Inbox")
    label, name_hint = split_name(mockup.stem)
    name = generator.slug(label)
    wd = config.WORK / name
    wd.mkdir(parents=True, exist_ok=True)
    hint, flags = parse_flags(" ".join(x for x in (hint, name_hint, read_txt_hint(mockup)) if x))
    local = wd / ("mockup" + mockup.suffix.lower())
    if mockup.resolve() != local.resolve():
        shutil.copy2(mockup, local)
    set_phase("planning")
    log(f"Planning '{label}' ..." + (f"  (notes: {hint})" if hint else ""))
    plan = planner.plan(local, hint, log)
    plan.update(mockup=str(local.resolve()), label=label, name=name, flags=sorted(flags))
    _save(wd / "plan.json", plan)
    show_plan(plan)
    if plan_only:
        log(f"Plan saved to {wd / 'plan.json'}. Run 'process' when it looks right.")
        return plan
    build(wd, plan, plan["assets"], full=True)
    return plan


def hands_off(plan) -> bool:
    flags = set(plan.get("flags", []))
    if "review" in flags:
        return False
    if "auto" in flags:
        return True
    return config.AUTO_APPROVE


def build(wd: Path, plan: dict, assets: list, full: bool = False):
    mockup = Path(plan["mockup"])
    if config.QA_ENABLED:
        llm.check_ready(config.QA_PROVIDER)  # a missing key should stop here, not after the images are paid for
    set_phase("generating")
    try:
        results = generator.generate_all(mockup, assets, wd / "raw", log)
    except generator.FatalImageError as e:
        raise RuntimeError(f"OpenAI image error that would hit every layer: {str(e)[:300]}\n"
                           "Run 'python run.py models' to see your image models, then set IMAGE_MODEL in .env.")
    set_phase("packaging")
    records = merge_qa(wd, assets, results)
    ready = ready_dir(plan)
    package(plan, assets, results, ready, full)
    summary, items, needs_look = build_summary(plan, ready, records)
    sheet = preview.make_sheet(items, wd / "preview.jpg", f"{plan['label']}  -  {plan['mode']}")
    for line in summary.splitlines():
        log(line)
    st = _json(wd / "status.json", {})
    st.update(name=wd.name, label=plan["label"], needs_look=needs_look, updated=dt.datetime.now().isoformat(timespec="seconds"))
    _save(wd / "status.json", st)

    link = None
    if hands_off(plan):
        set_phase("uploading")
        try:
            link = upload_or_sync(wd, plan, ready)
        except Exception as e:
            log(f"Drive upload failed: {e}")
            summary += f"\n\nDRIVE UPLOAD FAILED: {e}\nFix it, then run: python run.py approve \"{plan['label']}\""
            needs_look = True
    else:
        log(f'Waiting for your review. When happy: python run.py approve "{plan["label"]}"')
    images = sum(r.get("images", 0) for r in results.values())
    log_run(plan, len(assets), images, needs_look, link)
    notify.shirt_ready(plan["label"], ready, summary, log, link=link, preview=sheet, needs_look=needs_look)
    set_phase("done")


def merge_qa(wd: Path, assets, results):
    """Keep one quality record per layer in qa.json (so a redo of one layer keeps the others)."""
    records = _json(wd / "qa.json", {})
    for a in assets:
        r = results.get(a["n"], {})
        info = r.get("qa")
        if not r.get("path"):
            records[str(a["n"])] = {"name": a["name"], "status": "missing", "issues": [str(r.get("error") or "no image")[:200]]}
            continue
        records[str(a["n"])] = {"name": a["name"], "status": generator._status(info), "score": info.get("score"),
                                "issues": info.get("issues", []), "attempts": r.get("attempts", 1),
                                "images": r.get("images", 1)}
    _save(wd / "qa.json", records)
    return records


def package(plan, assets, results, ready: Path, full: bool):
    """Copy the generated layers into Ready\\<shirt>. The full numbered set is replaced on a new run."""
    ready.mkdir(parents=True, exist_ok=True)
    if full:
        keep = {a["n"] for a in plan["assets"]}
        for f in ready.glob("[0-9][0-9]_*"):
            if int(f.name[:2]) not in keep:
                f.unlink()
    for a in assets:
        path = results.get(a["n"], {}).get("path")
        if not path:
            continue
        for old in ready.glob(f"{a['n']:02d}_*"):
            old.unlink()
        shutil.copy2(path, ready / Path(path).name)


def build_summary(plan, ready: Path, records):
    label, lines, items, needs_look = plan["label"], [], [], False
    for a in plan["assets"]:
        n = a["n"]
        files = sorted(ready.glob(f"{n:02d}_*"), key=lambda p: p.stat().st_mtime)
        rec = records.get(str(n), {})
        if not files:
            lines.append(f'  MISSING      {a["name"]}  ->  python run.py redo "{label}" {n}')
            items.append({"path": ready / "none", "label": f"{n:02d} {a['name']}", "status": "fail", "note": "missing"})
            needs_look = True
            continue
        f = files[-1]
        status = rec.get("status", "unchecked")
        eff = max(upscaler.art_size(f)) / max(a["print_inches"])
        dpi = upscaler.target_dpi(a)
        up = f"upscale ~{dpi / eff:.1f}x" if eff < dpi * config.REVIEW_OK_RATIO else ""
        word = {"ok": "OK", "check": "CHECK EDGES", "fail": "LOOK AT THIS", "unchecked": "NOT CHECKED"}.get(status, status.upper())
        needs_look = needs_look or status == "fail"
        lines.append(f"  {word:12s} {f.name}" + (f"   [{up}]" if up else ""))
        for issue in rec.get("issues", [])[:3]:
            lines.append(f"      - {issue}")
        items.append({"path": f, "label": f"{n:02d} {a['name']}", "status": status if status != "missing" else "fail",
                      "note": up or word})
    good = sum(1 for i in items if i["status"] in ("ok", "check", "unchecked"))
    head = f"{label} ({plan['mode']}): {good} of {len(plan['assets'])} layers ready"
    if needs_look:
        head += "  -  SOME NEED A LOOK"
    up_n = sum(1 for i in items if "upscale" in str(i["note"]))
    foot = f"\n{up_n} layer(s) are below the print target and may need an upscale." if up_n else ""
    return head + "\n" + "\n".join(lines) + foot, items, needs_look


def pick_upload_files(folder: Path):
    """One file per asset number. If you saved an upscaled copy next to the original, the newest one wins."""
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT]
    groups = {}
    for p in files:
        groups.setdefault(p.name[:2] if p.name[:2].isdigit() else p.name, []).append(p)
    chosen, skipped = [], []
    for key in sorted(groups):
        ps = sorted(groups[key], key=lambda p: p.stat().st_mtime)
        chosen.append(ps[-1])
        skipped += ps[:-1]
    return chosen, skipped


def upload_or_sync(wd: Path, plan, ready: Path) -> str:
    """First time: create the Drive folder + share link. After that: sync changes so the link stays the same."""
    from . import drive

    files, skipped = pick_upload_files(ready)
    if not files:
        raise RuntimeError(f"No finished files in {ready}")
    for p in skipped:
        log(f"Skipping older copy {p.name} (a newer file with the same number is in the folder)")
    st = _json(wd / "status.json", {})
    if st.get("folder_id"):
        counts = drive.sync_folder(st["folder_id"], files, log)
        log(f"Drive updated (same link): {counts}")
        link = st["link"]
    else:
        link, folder_id = drive.upload_folder(files, plan["label"], log)
        st.update(link=link, folder_id=folder_id)
        _save(wd / "status.json", st)
    st = _json(wd / "status.json", {})
    st.update(approved=True, link=link)
    _save(wd / "status.json", st)
    (ready / "DRIVE LINK.txt").write_text(link, encoding="utf-8")
    log(f"SHARE LINK for {plan['label']}: {link}")
    return link


def approve(name: str):
    """python run.py approve "name"  - upload (or sync) the Ready folder to Drive and email the link."""
    wd, plan = find_shirt(name)
    ready = ready_dir(plan)
    if not ready.exists():
        raise FileNotFoundError(f"No finished files in {ready}")
    set_phase("uploading")
    link = upload_or_sync(wd, plan, ready)
    summary, _, needs_look = build_summary(plan, ready, _json(wd / "qa.json", {}))
    notify.shirt_ready(plan["label"], ready, summary, log, link=link, preview=wd / "preview.jpg", needs_look=needs_look)
    set_phase("done")
    return link


def redo(name: str, numbers):
    wd, plan = find_shirt(name)
    picked = [a for a in plan["assets"] if a["n"] in numbers]
    if not picked:
        raise ValueError(f"No layers numbered {list(numbers)} in '{plan['label']}'")
    for a in picked:  # delete the old image so it is generated fresh
        for f in (wd / "raw").glob(f"{a['n']:02d}_*"):
            f.unlink()
    build(wd, plan, picked, full=False)


def log_run(plan, n_assets, images, needs_look, link):
    path = config.WORK / "log.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "shirt", "mode", "layers", "images_made", "est_image_cost_usd", "needs_a_look", "link"])
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), plan["label"], plan["mode"], n_assets, images,
                    round(images * config.IMAGE_COST_ESTIMATE, 2), "yes" if needs_look else "no", link or ""])


# ---------------------------------------------------------------- job queue (watcher + web page)
JOBS = {}          # id -> state dict (newest last)
_queue = queue.Queue()
_started = False


def submit(kind: str, label: str, fn, after=None) -> str:
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"id": jid, "kind": kind, "label": label, "phase": "queued", "lines": [], "error": None,
                 "started": dt.datetime.now().isoformat(timespec="seconds"), "finished": None}
    for old in list(JOBS)[:-40]:
        JOBS.pop(old, None)
    _queue.put((jid, fn, after))
    return jid


def run_guarded(label: str, fn):
    """Run fn; on any error tell the user (pop-up + email) instead of dying silently."""
    try:
        return fn()
    except Exception as e:
        msg = str(e) or e.__class__.__name__
        log(f"ERROR on '{label}': {msg}")
        if not isinstance(e, (FileNotFoundError, ValueError)):  # typos at the keyboard don't need an email
            notify.failed(label, msg, log)
        raise


def _worker():
    while True:
        jid, fn, after = _queue.get()
        state = JOBS.get(jid)
        _ctx.sink = state
        ok = False
        try:
            run_guarded(state["label"] if state else "job", fn)
            ok = True
        except Exception as e:
            if state is not None:
                state["error"] = str(e) or e.__class__.__name__
                state["phase"] = "error"
        finally:
            if state is not None:
                state["finished"] = dt.datetime.now().isoformat(timespec="seconds")
                if ok and state["phase"] != "done":
                    state["phase"] = "done"
            _ctx.sink = None
            if after:
                try:
                    after(ok)
                except Exception:
                    pass
            _queue.task_done()


def start_worker():
    global _started
    if not _started:
        threading.Thread(target=_worker, daemon=True, name="shirt-worker").start()
        _started = True


def submit_mockup(path: Path, hint: str = ""):
    """Queue a mockup. When finished, the file moves to Inbox\\Done (or Inbox\\Failed) so it is never run twice."""
    path = Path(path)
    label, _ = split_name(path.stem)

    def after(ok):
        _archive(path, "Done" if ok else "Failed")

    return submit("shirt", label, lambda: process(path, hint=hint), after)


def _archive(path: Path, folder: str):
    dest = path.parent / folder
    dest.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in (path, path.with_suffix(".txt")):
        if f.exists():
            try:
                shutil.move(str(f), str(dest / f"{stamp}_{f.name}"))
            except Exception:
                pass


def _inbox_ready(f: Path) -> bool:
    """A file is ready when it is an image and its size has stopped changing (phone uploads / Drive sync)."""
    if f.suffix.lower() not in IMG_EXT or f.name.startswith((".", "~")):
        return False
    try:
        s1 = f.stat().st_size
        time.sleep(2)
        return s1 > 0 and s1 == f.stat().st_size
    except OSError:
        return False


def watch_inbox(stop: threading.Event = None):
    config.INBOX.mkdir(parents=True, exist_ok=True)
    queued = set()
    log(f"Watching {config.INBOX} ... drop a mockup in.")
    while not (stop and stop.is_set()):
        for f in sorted(config.INBOX.iterdir()):
            if f.is_file() and f not in queued and _inbox_ready(f):
                queued.add(f)
                log(f"New mockup: {f.name}")
                submit_mockup(f)
        for f in list(queued):
            if not f.exists():
                queued.discard(f)
        time.sleep(5)
