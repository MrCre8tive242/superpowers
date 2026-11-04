"""Decide HOW to extract a shirt (3D all-over vs cut and sew) and build the background files for it.

Order of authority:
  1. What you wrote in the hint ("3D", "all-over", "cut and sew", "panels", "long sleeve", "short sleeve")
  2. What the script sees in the mockup (sleeve length, seams, panels)
  3. Your standing policy in .env (LONG_SLEEVE_STYLE / SHORT_SLEEVE_STYLE)
"""
import re

from . import config

DETECT = """
TASK: look at the garment(s) in the mockup and describe how the shirt is built. Do NOT list assets.
Return JSON:
{"sleeve_length": "long|short|sleeveless|unknown",
 "panel_cues": ["visible seams, raglan or set-in sleeve seams, contrasting collar, cuffs or side panels, sleeves with a different design from the body, ..."],
 "continuous_print_cues": ["design flows across body, shoulders and sleeves with no break, ..."],
 "looks_cut_and_sew": true or false,
 "summary": "one short sentence"}
Long sleeve = sleeves reaching the wrist. Short sleeve = sleeves ending above the elbow.
"""

# Standard piece sizes from the extraction rules (width x height, inches).
BODY_INCHES = [22, 28]
SLEEVE_INCHES = {"long": [17, 25], "short": [17, 9]}
FLAT_3D_INCHES = [44, 36]

_CUT = re.compile(r"cut\s*(?:and|&|n|-)\s*sew|\bpanels?\b|pattern\s*pieces?", re.I)
_3D = re.compile(r"\b3d\b|all[- ]?over|sublimat", re.I)
_LONG = re.compile(r"long[- ]?sleeve", re.I)
_SHORT = re.compile(r"short[- ]?sleeve|\btee\b|t-shirt", re.I)


def decide_mode(hint: str, detected: dict):
    """Returns (mode_string, style, sleeve, reason). style is '3D' or 'cut and sew'; sleeve is 'long' or 'short'."""
    hint = hint or ""
    sleeve = (detected.get("sleeve_length") or "unknown").lower()
    sleeve_why = f"{sleeve} sleeves seen in the mockup"
    if _LONG.search(hint):
        sleeve, sleeve_why = "long", "long sleeve stated in your hint"
    elif _SHORT.search(hint):
        sleeve, sleeve_why = "short", "short sleeve stated in your hint"
    if sleeve not in ("long", "short"):
        sleeve, sleeve_why = "short", "sleeve length unclear, short sleeve assumed"

    if _CUT.search(hint):
        style, why = "cut and sew", "cut and sew stated in your hint"
    elif _3D.search(hint):
        style, why = "3D", "3D / all-over stated in your hint"
    else:
        policy = config.LONG_SLEEVE_STYLE if sleeve == "long" else config.SHORT_SLEEVE_STYLE
        if policy in ("cut and sew", "3d"):
            style = "cut and sew" if policy == "cut and sew" else "3D"
            why = f"{sleeve_why}; your policy for {sleeve} sleeves is {style}"
        else:  # auto: believe the mockup
            cues = detected.get("panel_cues") or []
            if detected.get("looks_cut_and_sew"):
                style = "cut and sew"
                why = "panel/seam construction seen in the mockup: " + "; ".join(map(str, cues[:3]))
            else:
                style = "3D"
                why = f"{sleeve_why}; no panel construction seen, so 3D all-over (the rules' default)"
    return f"{style} {sleeve} sleeve", style, sleeve, why


def decided_text(mode: str, style: str) -> str:
    if style == "cut and sew":
        return (f"\nMODE DECIDED BY THE SCRIPT: {mode}. Use exactly this mode.\n"
                "Cut and sew: do NOT list any background entries; the script adds the four background pieces "
                "(front body, back body, left sleeve, right sleeve). Describe in \"background_art\" what the "
                "clean background looks like with every element removed (colors, textures, motifs, flow).")
    return (f"\nMODE DECIDED BY THE SCRIPT: {mode}. Use exactly this mode.\n"
            "3D: one flat shirt-shaped background per printed side shown, sleeves attached, listed last.")


def cut_and_sew_backgrounds(sleeve: str, background_art: str, back_shown: bool = False):
    """The four separate background files the rules require for cut and sew."""
    art = (background_art or "the same background art, colors and style shown in the mockup").strip()
    sw = SLEEVE_INCHES.get(sleeve, SLEEVE_INCHES["short"])
    back_note = ("Use the back view of the mockup." if back_shown else
                 "The back may not be shown: continue the same background art, colors and flow onto the back.")
    return [
        {"name": "front_body_background", "kind": "background", "print_inches": list(BODY_INCHES),
         "what": f"Cut and sew FRONT BODY piece only (no sleeves), about {BODY_INCHES[0]} x {BODY_INCHES[1]} inches, "
                 f"sloped shoulders, rounded scoop neckline, curved armholes. Clean background with every "
                 f"lettering, graphic and element removed and hidden areas rebuilt. Background art: {art}"},
        {"name": "back_body_background", "kind": "background", "print_inches": list(BODY_INCHES),
         "what": f"Cut and sew BACK BODY piece only (no sleeves), about {BODY_INCHES[0]} x {BODY_INCHES[1]} inches, "
                 f"shallow, nearly straight neckline. Clean background, nothing but the background art. "
                 f"{back_note} Background art: {art}"},
        {"name": "left_sleeve_background", "kind": "background", "print_inches": list(sw),
         "what": f"Cut and sew {sleeve.upper()} SLEEVE piece for the wearer's LEFT sleeve, about {sw[0]} wide x "
                 f"{sw[1]} inches, rounded cap, following the pattern reference. Clean background only, with "
                 f"sleeve lettering and graphics removed. Background art: {art}"},
        {"name": "right_sleeve_background", "kind": "background", "print_inches": list(sw),
         "what": f"Cut and sew {sleeve.upper()} SLEEVE piece for the wearer's RIGHT sleeve, a mirror of the left "
                 f"sleeve, about {sw[0]} wide x {sw[1]} inches. Clean background only, with sleeve lettering and "
                 f"graphics removed. Background art: {art}"},
    ]
