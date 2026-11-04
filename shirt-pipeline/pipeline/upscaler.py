"""Step 3: upscale only what needs it, using Topaz Gigapixel's command line."""
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

from . import config

Image.MAX_IMAGE_PIXELS = None  # large print files are expected

IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")


def art_size(path: Path):
    """Size of the visible artwork, ignoring empty transparent margins."""
    with Image.open(path) as im:
        if im.mode in ("RGBA", "LA") or "transparency" in im.info:
            box = im.convert("RGBA").getchannel("A").getbbox()
            if box:
                return box[2] - box[0], box[3] - box[1]
        return im.size


def passes_needed(art_px, print_inches, dpi, max_passes=None):
    """How many 2x passes so the artwork's long side reaches print_inches * dpi."""
    max_passes = config.MAX_UPSCALE_PASSES if max_passes is None else max_passes
    cur_long = max(art_px)
    need_long = max(print_inches) * dpi
    if cur_long <= 0 or cur_long >= need_long:
        return 0
    return min(max_passes, math.ceil(math.log2(need_long / cur_long)))


def _command(src: Path, dst_dir: Path) -> str:
    args = config.GIGAPIXEL_ARGS.format(input=str(src), outdir=str(dst_dir), model=config.GIGAPIXEL_MODEL)
    # One command string: Windows parses the quotes itself, so paths with spaces stay intact.
    return f'"{config.GIGAPIXEL_EXE}" {args}'


def _run_gigapixel(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    proc = subprocess.run(_command(src, dst_dir), capture_output=True, text=True, shell=(os.name != "nt"))
    if proc.returncode != 0:
        raise RuntimeError(f"Gigapixel exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}")
    outs = [p for p in dst_dir.iterdir() if p.suffix.lower() in IMG_EXT and p.stat().st_mtime >= started - 1]
    if not outs:
        raise RuntimeError("Gigapixel ran but wrote no image. Check GIGAPIXEL_ARGS (run: python run.py probe-topaz)")
    return max(outs, key=lambda p: p.stat().st_mtime)


def upscale_asset(src: Path, asset: dict, final_dir: Path, log=print) -> Path:
    final_dir.mkdir(parents=True, exist_ok=True)
    dpi = target_dpi(asset)
    art = art_size(src)
    n = passes_needed(art, asset["print_inches"], dpi)
    target = final_dir / src.name
    if n == 0:
        shutil.copy2(src, target)
        log(f"  {src.name}: art {art[0]}x{art[1]}px already enough for {dpi} DPI")
        return target
    current, tmp_dirs = src, []
    try:
        for p in range(n):
            tmp = final_dir / f"_tmp_{src.stem}_{p}"
            tmp_dirs.append(tmp)
            current = _run_gigapixel(current, tmp)
        final = target.with_suffix(current.suffix)
        shutil.move(str(current), final)
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)
    finish_file(final, asset, log, note=f"{n} x 2x pass")
    return final


def target_dpi(asset) -> int:
    return config.BACKGROUND_DPI if asset.get("kind") == "background" else config.ELEMENT_DPI


def finish_file(path: Path, asset: dict, log=print, note="upscaled", trim=True):
    """Trim any overshoot back to the target DPI and report the result."""
    dpi = target_dpi(asset)
    new = art_size(path)
    eff = max(new) / max(asset["print_inches"])
    if trim and eff > dpi * 1.15:  # overshot: shrink back to the target DPI to keep files manageable
        factor = dpi / eff
        with Image.open(path) as im:
            im = im.resize((round(im.width * factor), round(im.height * factor)), Image.LANCZOS)
            im.save(path)
        new = art_size(path)
        eff = max(new) / max(asset["print_inches"])
    flag = "" if eff >= dpi * 0.9 else f"  <-- LOW, target is {dpi}"
    log(f"  {path.name}: {note} -> art {new[0]}x{new[1]}px (~{eff:.0f} DPI at print size){flag}")
    if path.suffix.lower() not in (".png", ".tif", ".tiff", ".webp"):
        log(f"  WARNING: {path.name} is {path.suffix}, transparency is lost. Export PNG from Gigapixel.")


def manual_bucket(src: Path, asset: dict):
    """For the drag-and-drop mode: which Gigapixel scale this file needs (None = no upscale)."""
    need = max(asset["print_inches"]) * target_dpi(asset) / max(1, max(art_size(src)))
    if need <= 1:
        return None
    for scale in (2, 4, 6):
        if need <= scale:
            return scale
    return 6


def probe():
    """Print Gigapixel's own CLI help so we can confirm the right flags."""
    exe = Path(config.GIGAPIXEL_EXE)
    if not exe.exists():
        print(f"Not found: {exe}\nSet GIGAPIXEL_EXE in .env to the real .exe path.")
        folder = exe.parent if exe.parent.exists() else Path(r"C:\Program Files\Topaz Labs LLC")
        if folder.exists():
            print("Executables found under", folder)
            for p in folder.rglob("*.exe"):
                print("  ", p)
        return
    for flag in ("--cli --help", "--help", "-h"):
        out = subprocess.run(f'"{exe}" {flag}', capture_output=True, text=True, timeout=60, shell=(os.name != "nt"))
        text = (out.stdout or "") + (out.stderr or "")
        print(f"=== {exe.name} {flag} (exit {out.returncode}) ===\n{text.strip() or '(no output)'}\n")
        if text.strip():
            break
    print("Other programs in", exe.parent, "(a separate command-line tool would be one of these):")
    for p in sorted(exe.parent.glob("*.exe")):
        print("  ", p.name)
