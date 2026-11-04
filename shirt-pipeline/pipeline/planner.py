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


def _data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def plan(mockup: Path, hint: str = "") -> dict:
    rules = config.RULES_FILE.read_text(encoding="utf-8")
    user_text = "extraction" + (f"\n{hint}" if hint else "")
    client = OpenAI()
    resp = client.chat.completions.create(
        model=config.PLANNER_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": rules + "\n\n" + OVERRIDE},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": _data_url(mockup)}},
                ],
            },
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    assets = data.get("assets", [])
    if not assets:
        raise RuntimeError("Planner returned no assets")
    for i, a in enumerate(assets, 1):
        a.setdefault("n", i)
        a.setdefault("kind", "element")
        a.setdefault("print_inches", [config.DEFAULT_ELEMENT_INCHES] * 2)
    return data
