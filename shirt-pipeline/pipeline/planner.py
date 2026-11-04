"""Step 1: read the mockup + your rules, return one self-contained prompt per asset."""
import base64
import json
import mimetypes
from pathlib import Path

from openai import OpenAI

from . import config

OVERRIDE = """
AUTOMATION OVERRIDE (this replaces the "reply format" and "Create Assets 1 to 3 first" parts of the rules):
You are feeding a script, not a chat. Return ONLY valid JSON, no prose, in this shape:
{
  "mode": "3D short sleeve | 3D long sleeve | cut and sew short sleeve | cut and sew long sleeve",
  "assumed_mode": true/false,
  "notes": ["practical notes for the user, e.g. place real photos by hand"],
  "assets": [
    {
      "n": 1,
      "name": "short_slug_like_front_title",
      "kind": "element" or "background",
      "print_inches": [width, height],
      "prompt": "a COMPLETE standalone image prompt for THIS ONE asset only"
    }
  ]
}
Each asset's "prompt" must be fully self-contained because it is sent to the image model on its own with the
mockup attached: include the opening sentence, the PRODUCT line, the exact text/colors/shapes for this asset,
the RULES, the LOOK CLOSELY AT list and the IF YOU CANNOT MATCH sentence from the rules. Describe ONLY this asset.
Do not write "wait for continue".
IMPORTANT: the "3 or 4 assets per message" limit does NOT apply here. The script does its own batching, so
list EVERY asset from your full inventory in this one JSON (all lettering, the focal graphic, every supporting
element, every sleeve element, edge decorations, and the clean background file(s) last). Never stop at 3 and
never write "continue with the rest" or "Batch 2" in the notes: return the complete list now.
SPLIT RULE: never merge supporting elements into the focal graphic. The focal graphic is ONLY the main subject.
Every other animal, character, prop, moon, snowman, owl, badge, flower or similar object is its OWN asset, and each
sleeve graphic (snowflake clusters, trees, stripes that differ from the body) is its OWN asset. Typical shirts have
6 to 10 assets. Identify animals precisely (for example moose versus reindeer, owl species) by looking closely.
If the user gives a hint line after the word "extraction", treat it as a correction that overrides your reading.
Keep every banned word out of the prompts exactly as the rules require.
print_inches: realistic printed size of the asset on the garment (background per the rules' sizes; elements
default to about 10 inches on the longest side unless clearly smaller or larger). Background assets go LAST.
"""


INVENTORY_MODE = """
INVENTORY MODE: do NOT write image prompts yet. Only list the assets, following the numbering order in the rules.
Return ONLY JSON: {"inventory": [{"n": 1, "name": "short_slug", "kind": "element" or "background",
"what": "one short sentence describing exactly this one item and where it sits"}]}
Be strict about splitting: the focal graphic is only the main subject. EVERY other animal, character, prop, moon,
snowman, owl, badge or object is its OWN entry. Each sleeve graphic that differs from the body is its OWN entry.
Lettering groups in different places are separate entries. The clean background is the LAST entry.
Identify animals precisely (moose versus reindeer, etc). A shirt like a scene with 6 distinct things has 6+ entries.
If the user gave a correction hint, it overrides your reading.
"""


def _data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def plan(mockup: Path, hint: str = "") -> dict:
    rules = config.RULES_FILE.read_text(encoding="utf-8")
    user_text = "extraction" + (f"\n{hint}" if hint else "")
    client = OpenAI()
    image_url = _data_url(mockup)

    def ask(system, text):
        resp = client.chat.completions.create(
            model=config.PLANNER_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        )
        return json.loads(resp.choices[0].message.content)

    # Pass 1: inventory only. A short list is much harder to merge by accident.
    inv = ask(rules + "\n\n" + INVENTORY_MODE, user_text)
    inventory = inv.get("inventory", [])
    # Pass 2: one prompt per inventory entry, no merging allowed.
    forced = (
        user_text
        + "\n\nFINAL INVENTORY (you MUST produce exactly one asset per entry, same order, same n and name, "
        + "no merging and no extra assets; the background stays last):\n"
        + json.dumps(inventory, indent=1)
    )
    data = ask(rules + "\n\n" + OVERRIDE, forced)
    assets = data.get("assets", [])
    if not assets:
        raise RuntimeError("Planner returned no assets")
    for i, a in enumerate(assets, 1):
        a.setdefault("n", i)
        a.setdefault("kind", "element")
        a.setdefault("print_inches", [config.DEFAULT_ELEMENT_INCHES] * 2)
    return data
