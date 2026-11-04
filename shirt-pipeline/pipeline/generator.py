"""Step 2: generate each asset with the image API, in small batches (like typing 'continue')."""
import base64
import re
import time
from pathlib import Path

from openai import OpenAI

from . import config


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "asset"


def pick_size(print_inches) -> str:
    w, h = print_inches
    ratio = w / h if h else 1
    if ratio > 1.15:
        return "1536x1024"
    if ratio < 0.87:
        return "1024x1536"
    return "1024x1024"


def generate_asset(client, mockup: Path, asset: dict, out_dir: Path, retries: int = 2):
    out = out_dir / f"{asset['n']:02d}_{slug(asset['name'])}.png"
    refs = [open(mockup, "rb")]
    is_bg = asset.get("kind") == "background"
    if is_bg and config.PATTERN_REFERENCE.exists():
        refs.append(open(config.PATTERN_REFERENCE, "rb"))
    last = None
    try:
        for attempt in range(retries + 1):
            try:
                for f in refs:
                    f.seek(0)
                res = client.images.edit(
                    model=config.IMAGE_MODEL,
                    image=refs,
                    prompt=asset["prompt"],
                    size=pick_size(asset["print_inches"]),
                    quality=config.IMAGE_QUALITY,
                    background="transparent",
                    output_format="png",
                )
                out.write_bytes(base64.b64decode(res.data[0].b64_json))
                return out, None
            except Exception as e:  # content-policy refusals land here too
                last = str(e)
                time.sleep(3 * (attempt + 1))
    finally:
        for f in refs:
            f.close()
    return None, last


def generate_all(mockup: Path, assets: list, out_dir: Path, log=print):
    out_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    results = {}
    for i in range(0, len(assets), config.BATCH_SIZE):
        batch = assets[i : i + config.BATCH_SIZE]
        log(f"Batch {i // config.BATCH_SIZE + 1}: assets {batch[0]['n']}-{batch[-1]['n']}")
        for a in batch:
            path, err = generate_asset(client, mockup, a, out_dir)
            results[a["n"]] = {"path": str(path) if path else None, "error": err}
            log(f"  {a['n']:02d} {a['name']}: {'OK' if path else 'FAILED - ' + str(err)[:120]}")
    return results
