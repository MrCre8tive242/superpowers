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


class FatalImageError(RuntimeError):
    """An error that will hit every asset the same way (wrong model, no access, bad key)."""


def _is_fatal(err: str) -> bool:
    e = err.lower()
    return any(k in e for k in ("does not exist", "model_not_found", "must be verified", "invalid_api_key",
                                "incorrect api key", "insufficient_quota", "billing", "you do not have access"))


def resolve_model(client, log=print) -> str:
    """IMAGE_MODEL=auto picks the newest full (non-mini) gpt-image model your account can use."""
    if config.IMAGE_MODEL.lower() != "auto":
        return config.IMAGE_MODEL
    ids = [m.id for m in client.models.list()]
    imgs = [i for i in ids if i.startswith("gpt-image") or i.startswith("chatgpt-image")]
    if not imgs:
        raise FatalImageError("Your OpenAI account lists no gpt-image models. Image models may need organization "
                              "verification: platform.openai.com > Settings > Organization > General.")

    def rank(i):
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", i)] or [0]
        return ("mini" not in i, i.startswith("gpt-image"), nums)

    best = max(imgs, key=rank)
    log(f"Image model: {best}  (available: {', '.join(sorted(imgs))})")
    return best


def _is_refusal(err: str) -> bool:
    e = err.lower()
    return "moderation" in e or "safety" in e or "content_policy" in e or "rejected" in e


def generate_asset(client, model, mockup: Path, asset: dict, out_dir: Path, retries: int = 2):
    out = out_dir / f"{asset['n']:02d}_{slug(asset['name'])}.png"
    if out.exists():  # rerun after a crash: keep what is already made
        return out, None
    paths = [mockup]
    if asset.get("kind") == "background" and config.PATTERN_REFERENCE.exists() and "cut" in asset.get("mode", ""):
        paths.append(config.PATTERN_REFERENCE)
    opts = {"background": "transparent", "output_format": "png"}
    extra = {"input_fidelity": config.IMAGE_INPUT_FIDELITY} if config.IMAGE_INPUT_FIDELITY else None
    note, last, attempt = None, None, 0
    while attempt <= retries:
        refs = [open(p, "rb") for p in paths]
        try:
            res = client.images.edit(model=model, image=refs, prompt=asset["prompt"],
                                     size=pick_size(asset["print_inches"]), quality=config.IMAGE_QUALITY,
                                     extra_body=extra, **opts)
            out.write_bytes(base64.b64decode(res.data[0].b64_json))
            return out, note
        except Exception as e:
            last = str(e)
            low = last.lower()
            if _is_fatal(last):
                raise FatalImageError(last)
            if extra and "input_fidelity" in low:  # model doesn't support it: drop and retry
                extra = None
                continue
            if "background" in opts and ("background" in low or "transparen" in low):
                opts.pop("background")  # model can't do transparency: keep going, flag it
                note = "NO TRANSPARENCY (model does not support it) - remove the background by hand"
                continue
            if "output_format" in opts and "output_format" in low:
                opts.pop("output_format")
                continue
            if _is_refusal(last):  # retrying a refusal just costs money
                return None, "REFUSED by image API: " + last
            if "error code: 400" in low:  # other bad requests will not fix themselves
                return None, last
            time.sleep(3 * (attempt + 1))
            attempt += 1
        finally:
            for f in refs:
                f.close()
    return None, last


def generate_all(mockup: Path, assets: list, out_dir: Path, log=print):
    out_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    model = resolve_model(client, log)
    results = {}
    for i in range(0, len(assets), config.BATCH_SIZE):
        batch = assets[i : i + config.BATCH_SIZE]
        log(f"Batch {i // config.BATCH_SIZE + 1}: assets {batch[0]['n']}-{batch[-1]['n']}")
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            outs = list(pool.map(lambda a: generate_asset(client, model, mockup, a, out_dir), batch))
        for a, (path, msg) in zip(batch, outs):
            results[a["n"]] = {"path": str(path) if path else None, "error": None if path else msg}
            status = ("OK" + (f"  WARNING: {msg}" if msg else "")) if path else "FAILED - " + str(msg)[:160]
            log(f"  {a['n']:02d} {a['name']}: {status}")
    return results
