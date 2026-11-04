"""Quality check: a vision model compares each generated layer with the mockup."""
import difflib
import re
import tempfile
from pathlib import Path

from PIL import Image

from . import config, edges, llm

QA_SYSTEM = """You are a strict print-production quality checker for sublimation shirt artwork.
You are shown (1) the customer's mockup and (2) one generated artwork layer. Transparent areas of the layer are
shown as flat mid-gray. Judge the layer only against what it is supposed to contain. Be critical: a letter that is
wrong, a missing part or a stray element means a low score. Reply with JSON only."""

QA_TASK = """LAYER NAME: {name}
KIND: {kind}
THIS LAYER MUST CONTAIN ONLY: {what}
EXACT TEXT THAT MUST APPEAR (letter for letter): {text}
{extra}
Check, looking closely at image 2 next to image 1:
- text: transcribe every word and number visible in image 2 into "text_read" exactly as drawn, letter by letter.
- complete: nothing cut off or missing; parts hidden in the mockup were rebuilt sensibly.
- only_this: nothing from other parts of the mockup. No shirt, model, mannequin, collar, seams, wrinkles, shadows or
  backdrop. No collage, no duplicates, no extra copies.
- faithful: colors, shapes, style and proportions match the mockup.
- edges: clean cut edges, no leftover backdrop or fringe.
{kind_rule}
Return JSON: {{"score": 0-10, "text_read": "...", "issues": ["short, specific problems"],
"fix_hint": "one sentence telling the artist exactly what to change next time (empty if nothing)"}}
Score 9-10 = print-ready, 7-8 = minor flaws, below 7 = must be redone."""

KIND_RULES = {
    "element": "- element rule: only the single item above, on a transparent background.",
    "background": ("- background rule: ONLY the clean background art in the required shape, transparent outside the "
                   "shape. NO lettering, animals, props, snowmen, moons or other focal elements left in it."),
}


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def _on_gray(path: Path) -> Path:
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
    rgba.thumbnail((1400, 1400))
    bg = Image.new("RGBA", rgba.size, (128, 128, 128, 255))
    bg.alpha_composite(rgba)
    out = Path(tempfile.mkdtemp()) / "qa_view.png"
    bg.convert("RGB").save(out)
    return out


def check(mockup: Path, asset: dict, result: Path, log=print) -> dict:
    """Returns {passed, score, issues, fix_hint, flags, checked}. Never raises on a QA failure."""
    prog = edges.analyze(result)
    kind = asset.get("kind", "element")
    hard = []
    if kind == "element" and ("no transparent area" in prog["flags"] or prog["solid_backdrop"]):
        hard.append("the image has a solid backdrop instead of a transparent background")
    info = {"passed": False, "score": 0.0, "issues": [], "fix_hint": "", "flags": prog["flags"],
            "checked": False, "text_read": ""}
    if config.QA_ENABLED:
        try:
            expected = asset.get("text", "")
            data = llm.ask_json(
                config.QA_PROVIDER, config.QA_MODEL, QA_SYSTEM,
                QA_TASK.format(name=asset["name"], kind=kind, what=asset.get("what", ""),
                               text=expected or "(none)", extra="", kind_rule=KIND_RULES.get(kind, "")),
                images=[mockup, _on_gray(result)], max_tokens=1500)
            info["checked"] = True
            info["score"] = float(data.get("score", 0) or 0)
            info["issues"] = [str(i) for i in (data.get("issues") or [])][:6]
            info["fix_hint"] = str(data.get("fix_hint") or "")
            info["text_read"] = str(data.get("text_read") or "")
            if expected:
                exp, got = _norm(expected), _norm(info["text_read"])
                if exp != got and difflib.SequenceMatcher(None, exp, got).ratio() < 0.97:
                    info["issues"].insert(0, f'text reads "{info["text_read"]}" but must read exactly "{expected}"')
                    info["fix_hint"] = (f'The text must read exactly "{expected}", letter for letter. ' + info["fix_hint"]).strip()
                    info["score"] = min(info["score"], config.QA_MIN_SCORE - 1)
        except Exception as e:  # the check failing must not stop the shirt
            log(f"    (quality check could not run for {asset['name']}: {str(e)[:120]})")
    if hard:
        info["issues"] = hard + info["issues"]
        info["fix_hint"] = ("Draw the artwork on a fully transparent background. No solid, white or colored backdrop. "
                            + info["fix_hint"]).strip()
        info["score"] = min(info["score"], config.QA_MIN_SCORE - 1)
    if prog["halo"]:
        info["issues"].append("light halo around the edges (check the edges before printing)")
    info["passed"] = (not hard) and (info["score"] >= config.QA_MIN_SCORE if info["checked"] else True)
    return info
