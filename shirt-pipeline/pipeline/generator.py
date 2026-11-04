"""Step 2: generate each asset with the image API, in small batches (like typing 'continue')."""
import base64
import re
import time
from concurrent.futures import ThreadPoolExecutor
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


def _is_refusal(err: str) -> bool:
    e = err.lower()
    return "moderation" in e or "safety" in e or "content_policy" in e or "rejected" in e


def generate_asset(client, mockup: Path, asset: dict, out_dir: Path, retries: int = 2):
    out = out_dir / f"{asset['n']:02d}_{slug(asset['name'])}.png"
    if out.exists():  # rerun after a crash: keep what is already made
        return out, None
    paths = [mockup]
    if asset.get("kind") == "background" and config.PATTERN_REFERENCE.exists() and "cut" in asset.get("mode", ""):
        paths.append(config.PATTERN_REFERENCE)
    extra = {"input_fidelity": config.IMAGE_INPUT_FIDELITY} if config.IMAGE_INPUT_FIDELITY else None
    last = None
    for attempt in range(retries + 1):
        refs = [open(p, "rb") for p in paths]
        try:
            res = client.images.edit(
                model=config.IMAGE_MODEL,
                image=refs,
                prompt=asset["prompt"],
                size=pick_size(asset["print_inches"]),
                quality=config.IMAGE_QUALITY,
                background="transparent",
                output_format="png",
                extra_body=extra,
            )
            out.write_bytes(base64.b64decode(res.data[0].b64_json))
            return out, None
        except Exception as e:
            last = str(e)
            if extra and "input_fidelity" in last:  # model doesn't support it: drop and retry
                extra = None
                continue
            if _is_refusal(last):  # retrying a refusal just costs money
                return None, "REFUSED by image API: " + last
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
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            outs = list(pool.map(lambda a: generate_asset(client, mockup, a, out_dir), batch))
        for a, (path, err) in zip(batch, outs):
            results[a["n"]] = {"path": str(path) if path else None, "error": err}
            log(f"  {a['n']:02d} {a['name']}: {'OK' if path else 'FAILED - ' + str(err)[:160]}")
    return results
