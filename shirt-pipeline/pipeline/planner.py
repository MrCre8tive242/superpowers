"""Step 1: read the mockup + your rules, return one self-contained prompt per asset.

Three stages, so assets cannot be merged by accident:
  1. survey   - list every distinct visible object, then group them into numbered assets
  2. review   - a second look that splits any asset still bundling separate objects
  3. prompts  - one call PER asset, each writing a prompt for that single asset only
"""
import base64
import json
import mimetypes
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from . import config

AUTOMATION = """
AUTOMATION OVERRIDE (replaces the reply format, the batching and the "wait for continue" parts of the rules):
You are feeding a script, not a chat. Reply with JSON only. The script does its own batching, so never limit the
list to 3 or 4 and never mention "continue" or "Batch 2". If the user message contains a CORRECTION line,
it overrides your own reading of the mockup.
"""

SURVEY = """
TASK: survey the mockup. Do not write image prompts yet.
First list every distinct visible object one by one in "objects_seen" (each animal, character, person, prop,
moon, sun, vehicle, badge, flag, lettering group, sleeve graphic, edge decoration). Name animals precisely
(moose vs reindeer, snowy owl vs barn owl).
Then build "inventory" following the rules' numbering order. Splitting rules:
- The main focal graphic is ONLY the main subject (for example a pair of matching animals posed together).
- EVERY other animal, character, prop, moon or object is its OWN asset, even if it overlaps the focal graphic.
- Lettering groups in different places are separate assets. Attached flourishes stay with their lettering.
- Each sleeve graphic that differs from the body is its own asset.
- Only keep things together when they are one inseparable crest or emblem.
- The clean background file(s) are LAST. 3D = one background per printed side shown; cut and sew = 4 pieces.
Return JSON:
{"mode": "3D short sleeve | 3D long sleeve | cut and sew short sleeve | cut and sew long sleeve",
 "assumed_mode": true/false,
 "notes": ["short practical notes for the user, per the rules"],
 "objects_seen": ["..."],
 "inventory": [{"n": 1, "name": "short_slug", "kind": "element|background",
                "what": "exactly what this one asset contains and where it sits",
                "print_inches": [width, height]}]}
print_inches = realistic printed size. Elements: about 10 in on the longest side unless clearly smaller or larger.
Backgrounds: use the sizes in the rules.
"""

REVIEW = """
TASK: review this inventory against the mockup and the objects list. If any asset bundles more than one
separate object (for example "owl, moose and snowman" or "leopards with a snowman"), split it into separate
assets. Add any visible object that is missing. Fix wrong species or misspelled text. Do not merge anything.
In 3D mode the sleeves are part of each side's background: there is never a separate sleeve background, only one
background per printed side (front, and back if the back is shown). Renumber in the rules' order with the background(s) last. Return JSON: {"inventory": [ ...same entry shape... ]}
"""

ONE_PROMPT = """
TASK: write the finished image prompt for ONE asset only (given below). It is sent to the image model on its own
with the mockup attached, so it must be fully self-contained and follow the PROMPT STRUCTURE in the rules:
the opening sentence, PRODUCT line, a description of ONLY this asset (exact text, colors, shapes, style, what to
remove and keep), the RULES lines, LOOK CLOSELY AT for this asset, and the IF YOU CANNOT MATCH sentence.
Say clearly that everything else in the mockup (the other assets listed) must NOT appear in this image.
For a 3D background include the required continuous-design paragraph word for word.
Do NOT end with "create assets 1 to 3" or "wait for continue". Use none of the banned words.
Return JSON: {"prompt": "..."}
"""

# Words the rules ban inside image prompts, with safe replacements.
BANNED = {
    r"\bextraction\b": "recreation",
    r"\bextract(ed|ing|s)?\b": "recreate",
    r"\bisolat(e|ed|ing)\b": "redraw",
    r"\bcut[- ]out\b": "redrawn",
    r"\bmask(ed|ing|s)?\b": "cover",
    r"\btrac(e|ed|ing)\b": "redraw",
    r"\bpixel[- ](identical|accurate)\b": "faithful",
    r"\bverify\b": "make sure",
    r"\bcheck\b": "look closely at",
    r"\balpha channel\b": "transparent background",
    r"\bRGBA\b": "transparent",
    r"\bdimensions\b": "size",
    r"\baudit\b": "look over",
}


def _data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def clean_prompt(text: str) -> str:
    for pat, rep in BANNED.items():
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)create assets? \d+.*?(continue|wait)[^.]*\.?", "", text).strip()
    return text


def _norm_entry(e: dict, i: int) -> dict:
    kind = "background" if str(e.get("kind", "")).lower().startswith("back") else "element"
    inches = e.get("print_inches") or [config.DEFAULT_ELEMENT_INCHES] * 2
    try:
        inches = [float(inches[0]), float(inches[1])]
    except (TypeError, ValueError, IndexError):
        inches = [config.DEFAULT_ELEMENT_INCHES] * 2
    name = re.sub(r"[^a-z0-9]+", "_", str(e.get("name") or f"asset_{i}").lower()).strip("_")
    return {"n": i, "name": name or f"asset_{i}", "kind": kind,
            "what": e.get("what", ""), "print_inches": inches}


def plan(mockup: Path, hint: str = "", log=print) -> dict:
    rules = config.RULES_FILE.read_text(encoding="utf-8")
    system = rules + "\n\n" + AUTOMATION
    correction = f"\nCORRECTION FROM THE USER: {hint}" if hint else ""
    client = OpenAI()
    image_url = _data_url(mockup)

    def ask(task: str) -> dict:
        resp = client.chat.completions.create(
            model=config.PLANNER_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": "extraction" + correction + "\n\n" + task},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]},
            ],
        )
        return json.loads(resp.choices[0].message.content)

    # 1. survey
    survey = ask(SURVEY)
    inventory = survey.get("inventory", [])
    log(f"Survey found {len(inventory)} assets from {len(survey.get('objects_seen', []))} objects")

    # 2. review / split
    reviewed = ask(REVIEW + "\nOBJECTS SEEN:\n" + json.dumps(survey.get("objects_seen", []))
                   + "\nINVENTORY:\n" + json.dumps(inventory, indent=1)).get("inventory")
    if reviewed and len(reviewed) >= len(inventory):  # a review may only split, never merge
        inventory = reviewed
    # keep elements first, backgrounds last, then renumber
    inventory = [e for e in inventory if not str(e.get("kind", "")).lower().startswith("back")] + \
                [e for e in inventory if str(e.get("kind", "")).lower().startswith("back")]
    mode = survey.get("mode", "3D short sleeve")
    if "3d" in mode.lower():  # 3D: sleeves belong to each side's background, never their own file
        bgs = [e for e in inventory if str(e.get("kind", "")).lower().startswith("back")]
        sleeve_bgs = [e for e in bgs if "sleeve" in (str(e.get("name", "")) + " " + str(e.get("what", ""))).lower()
                      and not any(w in str(e.get("name", "")).lower() for w in ("front", "back_", "rear"))]
        if len(sleeve_bgs) < len(bgs):
            inventory = [e for e in inventory if e not in sleeve_bgs]
            for e in sleeve_bgs:
                log(f"Dropped '{e.get('name')}': in 3D mode the sleeves are part of the main background")
    inventory = [_norm_entry(e, i) for i, e in enumerate(inventory, 1)]
    for e in inventory:  # never plan an element smaller than you might print it
        if e["kind"] == "element" and max(e["print_inches"]) < config.MIN_ELEMENT_INCHES:
            k = config.MIN_ELEMENT_INCHES / max(e["print_inches"])
            e["print_inches"] = [round(v * k, 1) for v in e["print_inches"]]
    if not inventory:
        raise RuntimeError("Planner found no assets")

    # 3. one prompt per asset, in parallel
    listing = "\n".join(f"{e['n']}. {e['name']}: {e['what']}" for e in inventory)

    def write(e):
        task = (ONE_PROMPT + f"\nPRODUCT MODE: {mode}\nALL ASSETS (for context only):\n{listing}\n\n"
                f"WRITE THE PROMPT FOR ASSET {e['n']} ONLY: {e['name']} - {e['what']}")
        e = dict(e, mode=mode)
        e["prompt"] = clean_prompt(ask(task).get("prompt", ""))
        return e

    with ThreadPoolExecutor(max_workers=4) as pool:
        assets = list(pool.map(write, inventory))
    empty = [a["name"] for a in assets if not a["prompt"]]
    if empty:
        raise RuntimeError(f"Planner wrote no prompt for: {empty}")

    return {
        "mode": mode,
        "assumed_mode": survey.get("assumed_mode", False),
        "notes": survey.get("notes", []),
        "objects_seen": survey.get("objects_seen", []),
        "hint": hint,
        "assets": assets,
    }
