"""One preview image of every layer, with its quality status, for a quick look on a phone."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TILE, PAD, LABEL, COLS = 360, 14, 54, 4
COLORS = {"ok": (40, 160, 90), "check": (225, 150, 20), "fail": (200, 50, 50), "unchecked": (120, 120, 120)}


def _font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _checker(size, step=18):
    img = Image.new("RGB", size, (235, 235, 235))
    d = ImageDraw.Draw(img)
    for y in range(0, size[1], step):
        for x in range(0, size[0], step):
            if (x // step + y // step) % 2:
                d.rectangle([x, y, x + step - 1, y + step - 1], fill=(205, 205, 205))
    return img


def make_sheet(items, out: Path, title: str = ""):
    """items: [{'path', 'label', 'status': ok|check|fail|unchecked, 'note'}]. Saves a JPEG and returns its path."""
    cols = min(COLS, max(1, len(items)))
    rows = (len(items) + cols - 1) // cols
    head = 60 if title else 0
    W = cols * (TILE + PAD) + PAD
    H = head + rows * (TILE + LABEL + PAD) + PAD
    sheet = Image.new("RGB", (W, H), (248, 248, 248))
    d = ImageDraw.Draw(sheet)
    if title:
        d.text((PAD, 16), title, fill=(30, 30, 30), font=_font(28))
    for i, it in enumerate(items):
        x = PAD + (i % cols) * (TILE + PAD)
        y = head + PAD + (i // cols) * (TILE + LABEL + PAD)
        tile = _checker((TILE, TILE))
        try:
            with Image.open(it["path"]) as im:
                im = im.convert("RGBA")
                im.thumbnail((TILE - 8, TILE - 8))
                tile.paste(im, ((TILE - im.width) // 2, (TILE - im.height) // 2), im)
        except Exception:
            ImageDraw.Draw(tile).text((20, TILE // 2), "missing", fill=(200, 0, 0), font=_font(24))
        sheet.paste(tile, (x, y))
        color = COLORS.get(it.get("status", "unchecked"), COLORS["unchecked"])
        d.rectangle([x, y + TILE, x + TILE, y + TILE + LABEL], fill=color)
        d.text((x + 8, y + TILE + 5), it["label"][:34], fill=(255, 255, 255), font=_font(19))
        d.text((x + 8, y + TILE + 29), (it.get("note") or it.get("status", "")).upper()[:44], fill=(255, 255, 255), font=_font(15))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=85)
    return out
