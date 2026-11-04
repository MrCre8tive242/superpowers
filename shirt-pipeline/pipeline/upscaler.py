"""Step 3: upscale only what needs it, using Topaz Gigapixel's command line."""
import math
import shlex
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from . import config


def passes_needed(current_px, print_inches, dpi, max_passes=None):
    """How many 2x passes are needed so the LONG side reaches print_inches*dpi."""
    max_passes = config.MAX_UPSCALE_PASSES if max_passes is None else max_passes
    cur_long = max(current_px)
    need_long = max(print_inches) * dpi
    if cur_long >= need_long:
        return 0
    return min(max_passes, math.ceil(math.log2(need_long / cur_long)))


def _run_gigapixel(src: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    args = config.GIGAPIXEL_ARGS.format(
        input=str(src), outdir=str(dst_dir), model=config.GIGAPIXEL_MODEL
    )
    cmd = [config.GIGAPIXEL_EXE] + shlex.split(args, posix=False)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Gigapixel failed ({proc.returncode}): {proc.stderr or proc.stdout}")
    # Gigapixel names outputs itself; take the newest image in the output dir.
    outs = sorted(dst_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
    if not outs:
        raise RuntimeError("Gigapixel produced no PNG output")
    return outs[-1]


def upscale_asset(src: Path, asset: dict, final_dir: Path, log=print) -> Path:
    final_dir.mkdir(parents=True, exist_ok=True)
    dpi = config.BACKGROUND_DPI if asset.get("kind") == "background" else config.ELEMENT_DPI
    with Image.open(src) as im:
        size = im.size
    n = passes_needed(size, asset["print_inches"], dpi)
    target = final_dir / src.name
    if n == 0:
        shutil.copy2(src, target)
        log(f"  {src.name}: {size[0]}px already enough for {dpi} DPI, no upscale")
        return target
    current = src
    for p in range(n):
        tmp = final_dir / f"_tmp_{src.stem}_{p}"
        current = _run_gigapixel(current, tmp)
    shutil.move(str(current), target)
    for d in final_dir.glob(f"_tmp_{src.stem}_*"):
        shutil.rmtree(d, ignore_errors=True)
    with Image.open(target) as im:
        log(f"  {src.name}: {n}x 2x pass -> {im.size[0]}x{im.size[1]}px")
    return target


def probe():
    """Print Gigapixel's own CLI help so we can confirm the right flags."""
    out = subprocess.run([config.GIGAPIXEL_EXE, "--cli", "--help"], capture_output=True, text=True)
    print(out.stdout or out.stderr)
