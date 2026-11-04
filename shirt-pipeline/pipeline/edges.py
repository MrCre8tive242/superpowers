"""Programmatic checks and clean-up for transparent edges (no AI involved)."""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

SENTINEL = (1, 254, 2)


def analyze(path: Path) -> dict:
    """Transparency facts about one generated file."""
    with Image.open(path) as im:
        had_alpha = "A" in im.getbands()
        small = im.convert("RGBA")
        small.thumbnail((512, 512))
    w, h = small.size
    a = small.getchannel("A")
    hist = a.histogram()
    transparent_frac = sum(hist[:8]) / max(1, sum(hist))
    corners = [small.getpixel(xy) for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    opaque_corners = all(c[3] > 240 for c in corners)
    flat = max(abs(corners[i][k] - corners[0][k]) for i in range(4) for k in range(3)) < 20
    solid_backdrop = opaque_corners and flat
    # halo: the outermost edge pixels are much lighter than the artwork just inside them
    halo = False
    mask = a.point(lambda v: 255 if v > 16 else 0)
    if 0.02 < transparent_frac < 0.98:
        inner = mask.filter(ImageFilter.MinFilter(5))
        band = ImageChops.subtract(mask, inner)
        if ImageStat.Stat(band).mean[0] > 0.5 and ImageStat.Stat(inner).mean[0] > 0.5:
            rgb = small.convert("RGB")
            edge = sum(ImageStat.Stat(rgb, band).mean) / 3
            core = sum(ImageStat.Stat(rgb, inner).mean) / 3
            halo = edge > 215 and core < 170
    flags = []
    if not had_alpha or transparent_frac < 0.01:
        flags.append("no transparent area")
    if solid_backdrop:
        flags.append("solid backdrop behind the artwork")
    if halo:
        flags.append("light halo around the edges")
    return {"had_alpha": had_alpha, "transparent_frac": round(transparent_frac, 3),
            "solid_backdrop": solid_backdrop, "halo": halo, "flags": flags}


def remove_flat_background(path: Path, tol: int = 28) -> bool:
    """If the image has a flat colour backdrop touching the corners, make it transparent. Returns True if changed."""
    with Image.open(path) as im:
        if "A" in im.getbands():
            rgba = im.convert("RGBA")
            w0, h0 = rgba.size
            if any(rgba.getpixel(xy)[3] < 16 for xy in ((0, 0), (w0 - 1, 0), (0, h0 - 1), (w0 - 1, h0 - 1))):
                return False  # already has a transparent backdrop: leave it alone
        original = im.convert("RGB")
    work = original.copy()
    w, h = work.size
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if work.getpixel(xy) != SENTINEL:
            ImageDraw.floodfill(work, xy, SENTINEL, thresh=tol)
    r, g, b = work.split()
    hit = ImageChops.multiply(ImageChops.multiply(r.point(lambda v: 255 if v == SENTINEL[0] else 0),
                                                  g.point(lambda v: 255 if v == SENTINEL[1] else 0)),
                              b.point(lambda v: 255 if v == SENTINEL[2] else 0))
    if ImageStat.Stat(hit).mean[0] < 255 * 0.01:
        return False
    alpha = ImageChops.invert(hit).filter(ImageFilter.MinFilter(3))  # pull the edge in 1px to drop the fringe
    out = original.convert("RGBA")
    out.putalpha(alpha)
    out.save(path, "PNG")
    return True
