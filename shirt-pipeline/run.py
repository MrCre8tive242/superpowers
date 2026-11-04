"""Shirt extraction pipeline.

  python run.py watch                       watch Inbox, process every new mockup, stop at review
  python run.py process "Inbox\\x.jpg" [hint]   plan -> generate -> Ready\\<name> folder + alert
  python run.py plan-only "Inbox\\x.jpg" [hint] only write the plan (cheap, no images)
  python run.py redo x 3 5                  regenerate assets 3 and 5 of shirt x
  python run.py approve "x"                 upload Ready\\x to Drive (shareable), print the link
  python run.py models                      list the OpenAI models your account can use
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

from pipeline import config, generator, notify, planner, upscaler

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def read_hint(mockup: Path, hint: str) -> str:
    txt = mockup.with_suffix(".txt")
    if txt.exists():
        hint = (hint + " " + txt.read_text(encoding="utf-8")).strip()
    return hint


def show_plan(plan):
    log(f"Mode: {plan['mode']}  Assets: {len(plan['assets'])}")
    if plan.get("mode_reason"):
        log(f"  mode chosen because: {plan['mode_reason']}")
        log("  (wrong? add \"3D\" or \"cut and sew\" to the hint)")
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
    try:
        results = generator.generate_all(mockup, assets, wd / "raw", log)
    except generator.FatalImageError as e:
        log(f"STOPPED - OpenAI image error that would hit every asset: {str(e)[:300]}")
        log("Run 'python run.py models' to see which image models your account has, then set IMAGE_MODEL in .env.")
        log("Your plan is saved; once fixed, rerun 'process' (finished images are kept).")
        return
    final = wd / "final"
    status_file = wd / "status.json"
    status = json.loads(status_file.read_text()) if status_file.exists() else {"failed": []}
    failed = set(status.get("failed", []))
    if config.UPSCALE_MODE == "off":
        failed = package_ready(wd, plan, assets, results, failed)
        status.update(name=wd.name, label=plan.get("label", wd.name), failed=sorted(failed), approved=False)
        status_file.write_text(json.dumps(status, indent=2), encoding="utf-8")
        return
    if config.UPSCALE_MODE != "cli":
        failed = sort_for_manual_upscale(wd, assets, results, failed)
        status.update(name=wd.name, label=plan.get("label", wd.name), failed=sorted(failed), approved=False)
        status_file.write_text(json.dumps(status, indent=2), encoding="utf-8")
        return
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


def ready_dir(plan_or_label) -> Path:
    label = plan_or_label.get("label") if isinstance(plan_or_label, dict) else plan_or_label
    return config.READY / label


def package_ready(wd: Path, plan: dict, assets, results, failed):
    """Copy the generated files into Ready\\<shirt name>, list what may need upscaling, alert the user."""
    import shutil

    label = plan.get("label", wd.name)
    out = ready_dir(plan)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for a in assets:
        r = results[a["n"]]
        if not r["path"]:
            failed.add(a["name"])
            continue
        failed.discard(a["name"])
        src = Path(r["path"])
        for old in out.glob(f"{a['n']:02d}_*"):
            old.unlink()  # replace the older version of this asset (redo)
        shutil.copy2(src, out / src.name)
        dpi = upscaler.target_dpi(a)
        art = upscaler.art_size(src)
        eff = max(art) / max(a["print_inches"])
        w, h = a["print_inches"]
        if eff >= dpi * config.REVIEW_OK_RATIO:
            lines.append(f"  OK        {src.name}  (~{eff:.0f} DPI at {w:g}x{h:g} in)")
        else:
            lines.append(f"  UPSCALE?  {src.name}  (~{eff:.0f} DPI at {w:g}x{h:g} in, target {dpi}, "
                         f"needs about {dpi / eff:.1f}x)")
    # summary of every file currently in the folder
    plan_names = {f"{a['n']:02d}" for a in plan["assets"]}
    have = {p.name[:2] for p in out.iterdir() if p.suffix.lower() in upscaler.IMG_EXT}
    missing = sorted(a["name"] for a in plan["assets"] if f"{a['n']:02d}" not in have)
    summary = "\n".join([f"{label}: {len(have & plan_names)} of {len(plan['assets'])} files ready"] + lines
                         + ([f"  MISSING: {', '.join(missing)}  ->  python run.py redo {wd.name} <numbers>"]
                            if missing else []))
    (wd / "review.txt").write_text(summary, encoding="utf-8")
    log(f"READY: {out}")
    for line in summary.splitlines():
        log(line)
    log("Upscale any file you want in Gigapixel, save it into the same folder (delete or overwrite the original).")
    log(f'When happy: python run.py approve "{label}"')
    notify.shirt_ready(label, out, summary, log)
    return failed


def sort_for_manual_upscale(wd: Path, assets, results, failed):
    """Copy files that need no upscale to final, and sort the rest into to_upscale\\2x, 4x, 6x."""
    import shutil

    final, todo = wd / "final", wd / "to_upscale"
    (wd / "upscaled").mkdir(parents=True, exist_ok=True)
    final.mkdir(parents=True, exist_ok=True)
    buckets = {}
    for a in assets:
        r = results[a["n"]]
        if not r["path"]:
            failed.add(a["name"])
            continue
        failed.discard(a["name"])
        src = Path(r["path"])
        for old in list(final.glob(src.stem + ".*")) + list(todo.glob(f"*/{src.stem}.*")):
            old.unlink()  # replace an older version of this asset
        scale = upscaler.manual_bucket(src, a)
        if scale is None:
            shutil.copy2(src, final / src.name)
            upscaler.finish_file(final / src.name, a, log, note="no upscale needed", trim=False)
        else:
            (todo / f"{scale}x").mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, todo / f"{scale}x" / src.name)
            buckets.setdefault(scale, []).append(src.name)
    log(f"Images ready in {wd / 'raw'}")
    if failed:
        log(f"Failed assets: {sorted(failed)}  ->  python run.py redo {wd.name} <numbers>")
    if buckets:
        log("UPSCALE IN GIGAPIXEL (Wonder 3.5, cloud render, export PNG):")
        for scale in sorted(buckets):
            log(f"  {todo / f'{scale}x'}  ->  set scale {scale}x  ({', '.join(buckets[scale])})")
        log(f"  Save the results into: {wd / 'upscaled'}")
        log(f"  Then run: python run.py finish {wd.name}")
    else:
        log(f"Nothing needs upscaling. When happy: python run.py approve {wd.name}")
    return failed


def finish(name: str):
    """Pick up Gigapixel results from Work\\<shirt>\\upscaled, trim to target DPI, move to final."""
    import shutil

    wd = config.WORK / name
    plan = json.loads((wd / "plan.json").read_text(encoding="utf-8"))
    by_n = {a["n"]: a for a in plan["assets"]}
    final = wd / "final"
    final.mkdir(parents=True, exist_ok=True)
    done = set()
    for f in sorted((wd / "upscaled").iterdir()):
        if f.suffix.lower() not in upscaler.IMG_EXT or not f.name[:2].isdigit():
            continue
        a = by_n.get(int(f.name[:2]))
        if not a:
            continue
        stem = f"{a['n']:02d}_{generator.slug(a['name'])}"
        for old in final.glob(stem + ".*"):
            old.unlink()
        dest = final / (stem + f.suffix.lower())
        shutil.copy2(f, dest)
        upscaler.finish_file(dest, a, log, note=f"from Gigapixel ({f.name})")
        done.add(stem)
    waiting = [p.stem for p in (wd / "to_upscale").glob("*/*") if p.stem not in done]
    if waiting:
        log(f"Still missing from 'upscaled': {waiting}")
    log(f"Review {final}. When happy: python run.py approve {name}")


def redo(name: str, numbers):
    wd, plan = find_shirt(name)
    picked = [a for a in plan["assets"] if a["n"] in numbers]
    if not picked:
        sys.exit(f"No assets numbered {numbers} in {name}")
    for a in picked:  # delete old raw file so it is generated fresh
        for f in (wd / "raw").glob(f"{a['n']:02d}_*"):
            f.unlink()
    build(wd, plan, picked)


def find_shirt(name: str):
    """Accept either the shirt name ('roots shirt') or its work folder name ('roots_shirt')."""
    wd = config.WORK / generator.slug(name)
    if not wd.exists():
        sys.exit(f"No shirt called '{name}' in {config.WORK}")
    plan = json.loads((wd / "plan.json").read_text(encoding="utf-8"))
    return wd, plan


def pick_upload_files(folder: Path):
    """One file per asset number. If you saved an upscaled copy next to the original, the newest one wins."""
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in upscaler.IMG_EXT]
    groups = {}
    for p in files:
        key = p.name[:2] if p.name[:2].isdigit() else p.name
        groups.setdefault(key, []).append(p)
    chosen, skipped = [], []
    for key in sorted(groups):
        ps = sorted(groups[key], key=lambda p: p.stat().st_mtime)
        chosen.append(ps[-1])
        skipped += ps[:-1]
    return chosen, skipped


def approve(name: str):
    from pipeline import drive

    wd, plan = find_shirt(name)
    label = plan.get("label", wd.name)
    folder = ready_dir(plan) if config.UPSCALE_MODE == "off" else wd / "final"
    if not folder.exists():
        sys.exit(f"No finished files in {folder}")
    files, skipped = pick_upload_files(folder)
    if not files:
        sys.exit(f"No finished files in {folder}")
    for p in skipped:
        log(f"Skipping older copy {p.name} (a newer file with the same number is in the folder)")
    missing = [a["name"] for a in plan["assets"] if f"{a['n']:02d}" not in {p.name[:2] for p in files}]
    if missing:
        log(f"WARNING: these assets are missing and will not be uploaded: {missing}")
    link = drive.upload_folder(files, label, log)
    with open(config.WORK / "links.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([dt.datetime.now().isoformat(timespec="seconds"), label, link])
    st_file = wd / "status.json"
    st = json.loads(st_file.read_text()) if st_file.exists() else {}
    st.update(approved=True, link=link)
    st_file.write_text(json.dumps(st, indent=2), encoding="utf-8")
    (folder / "DRIVE LINK.txt").write_text(link, encoding="utf-8")
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
        elif cmd == "finish" and len(a) >= 2:
            finish(a[1])
        elif cmd == "approve" and len(a) >= 2:
            approve(a[1])
        elif cmd == "models":
            from openai import OpenAI
            ids = sorted(m.id for m in OpenAI().models.list())
            print("Image models:", [i for i in ids if "image" in i] or "none")
            print("Vision/chat models (for PLANNER_MODEL):", [i for i in ids if i.startswith(("gpt-4", "gpt-5", "o"))])
        elif cmd == "probe-topaz":
            upscaler.probe()
        else:
            print(__doc__)
    except KeyboardInterrupt:
        log("Stopped.")
