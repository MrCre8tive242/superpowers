"""Step 2: generate every layer with the image API, check each one, and redo the ones that fail.

Per layer:  generate (1 candidate, or BEST_OF_HARD for lettering and the main graphic)
            -> quality check against the mockup -> if it fails, regenerate with the checker's feedback
            (up to QA_MAX_RETRIES times) -> keep the best attempt.
Cut and sew: the front body piece is made first and sent along as a reference for the other pieces, so the
             art flows across all four.
"""
import base64
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from . import config, edges, qa


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


def generate_once(client, model, mockup: Path, asset: dict, out: Path, prompt: str = None,
                  extra_refs=(), retries: int = 2):
    """One image-API call (with network retries). Returns (path or None, message)."""
    paths = [mockup]
    if asset.get("kind") == "background" and config.PATTERN_REFERENCE.exists() and "cut" in asset.get("mode", ""):
        paths.append(config.PATTERN_REFERENCE)
    paths += [Path(p) for p in extra_refs]
    opts = {"background": "transparent", "output_format": "png"}
    extra = {"input_fidelity": config.IMAGE_INPUT_FIDELITY} if config.IMAGE_INPUT_FIDELITY else None
    note, last, attempt = None, None, 0
    while attempt <= retries:
        refs = [open(p, "rb") for p in paths]
        try:
            res = client.images.edit(model=model, image=refs, prompt=prompt or asset["prompt"],
                                     size=pick_size(asset["print_inches"]), quality=config.IMAGE_QUALITY,
                                     extra_body=extra, **opts)
            out.parent.mkdir(parents=True, exist_ok=True)
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
                note = "NO TRANSPARENCY (model does not support it)"
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


def _status(info: dict) -> str:
    if not info.get("checked"):
        return "unchecked"
    if not info["passed"]:
        return "fail"
    return "check" if info.get("issues") else "ok"


def produce_asset(client, model, mockup: Path, asset: dict, out_dir: Path, extra_refs=(), log=print):
    """Generate -> check -> retry. Returns (final_path or None, result dict)."""
    final = out_dir / f"{asset['n']:02d}_{slug(asset['name'])}.png"
    tries_dir = out_dir / "_attempts"
    result = {"path": None, "error": None, "qa": None, "attempts": 0, "images": 0}
    if final.exists():  # rerun after a crash: keep what is already made
        result.update(path=str(final), qa={"passed": True, "checked": False, "issues": [], "score": 0, "flags": []})
        return final, result
    base_prompt = asset["prompt"]
    if extra_refs:
        base_prompt += ("\n\nThe finished front body piece is also attached as a reference image. Match its background "
                        "art, colors, scale and flow exactly so that all the pieces join seamlessly when sewn.")
    best = None  # (score, path, info)
    feedback = ""
    n_first = config.BEST_OF_HARD if (asset.get("hard") and config.QA_ENABLED and config.BEST_OF_HARD > 1) else 1
    attempt = 0
    while True:
        n = n_first if attempt == 0 else 1
        outs = []
        for k in range(n):
            attempt += 1
            tmp = tries_dir / f"{final.stem}.try{attempt}.png"
            prompt = base_prompt + (f"\n\nFIX THESE PROBLEMS FROM THE LAST ATTEMPT: {feedback}" if feedback else "")
            outs.append((tmp, prompt))
        with ThreadPoolExecutor(max_workers=len(outs)) as pool:
            gens = list(pool.map(lambda o: generate_once(client, model, mockup, asset, o[0], o[1], extra_refs), outs))
        for (tmp, _), (path, msg) in zip(outs, gens):
            result["images"] += 1
            if not path:
                result["error"] = msg
                continue
            if edges.analyze(path)["solid_backdrop"] and asset.get("kind") == "element":
                if edges.remove_flat_background(path):
                    msg = (msg or "") + " backdrop removed automatically"
            info = qa.check(mockup, asset, path, log)
            info["note"] = msg or ""
            if best is None or (info["passed"], info["score"]) > (best[2]["passed"], best[2]["score"]):
                best = (info["score"], path, info)
        result["attempts"] = attempt
        if best is None:  # every call failed or was refused: no point retrying
            break
        info = best[2]
        if info["passed"] or not config.QA_ENABLED or (attempt - n_first + 1) > config.QA_MAX_RETRIES:
            break
        feedback = info["fix_hint"] or "; ".join(info["issues"][:3])
        log(f"    {asset['name']}: failed check ({info['score']:.0f}/10: {'; '.join(info['issues'][:2])}) - retrying")
    if best is None:
        return None, result
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best[1], final)
    result.update(path=str(final), qa=best[2])
    return final, result


def generate_all(mockup: Path, assets: list, out_dir: Path, log=print):
    out_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    model = resolve_model(client, log)
    results = {}

    def run_batch(batch, extra_refs=()):
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            outs = list(pool.map(lambda a: produce_asset(client, model, mockup, a, out_dir, extra_refs, log), batch))
        for a, (path, res) in zip(batch, outs):
            results[a["n"]] = res
            if path:
                info = res["qa"]
                label = {"ok": "OK", "check": "OK (check edges)", "unchecked": "OK (not checked)",
                         "fail": f"NEEDS A LOOK ({'; '.join(info['issues'][:2])})"}[_status(info)]
                extra = f"  [{res['images']} images]" if res["images"] > 1 else ""
                log(f"  {a['n']:02d} {a['name']}: {label}{extra}")
            else:
                log(f"  {a['n']:02d} {a['name']}: FAILED - {str(res['error'])[:160]}")

    elements = [a for a in assets if a.get("kind") != "background"]
    backgrounds = [a for a in assets if a.get("kind") == "background"]
    for i in range(0, len(elements), config.BATCH_SIZE):
        batch = elements[i:i + config.BATCH_SIZE]
        log(f"Batch {i // config.BATCH_SIZE + 1}: assets {batch[0]['n']}-{batch[-1]['n']}")
        run_batch(batch)
    if backgrounds:
        cut = any("cut" in a.get("mode", "") for a in backgrounds)
        if cut and len(backgrounds) > 1:
            first, rest = backgrounds[0], backgrounds[1:]
            log(f"Background piece 1 (made first so the others can match it): asset {first['n']}")
            run_batch([first])
            ref = results[first["n"]]["path"]
            for i in range(0, len(rest), config.BATCH_SIZE):
                batch = rest[i:i + config.BATCH_SIZE]
                log(f"Matching pieces: assets {batch[0]['n']}-{batch[-1]['n']}")
                run_batch(batch, extra_refs=[ref] if ref else [])
        else:
            for i in range(0, len(backgrounds), config.BATCH_SIZE):
                batch = backgrounds[i:i + config.BATCH_SIZE]
                log(f"Background: assets {batch[0]['n']}-{batch[-1]['n']}")
                run_batch(batch)
    return results
