"""One place that talks to a vision model (Claude or OpenAI) and returns JSON."""
import base64
import json
import mimetypes
import re
from pathlib import Path

from . import config


class LLMSetupError(RuntimeError):
    """Missing key / wrong provider: nothing will work until the user fixes settings."""


def check_ready(provider: str):
    provider = provider.lower()
    if provider == "claude":
        if not config.ANTHROPIC_API_KEY:
            raise LLMSetupError("PLANNER_PROVIDER=claude but ANTHROPIC_API_KEY is empty. Add it to your .env file "
                                "(get one at console.anthropic.com > API keys).")
    elif provider != "openai":
        raise LLMSetupError(f"Unknown provider '{provider}'. Use claude or openai.")


def _b64(path: Path):
    """Downsize to a safe size (Claude rejects very large images) and return (mime, base64)."""
    import io

    from PIL import Image

    with Image.open(path) as im:
        im.load()
        im.thumbnail((1568, 1568))
        buf = io.BytesIO()
        if im.mode in ("RGBA", "LA", "P"):
            im.convert("RGBA").save(buf, "PNG", optimize=True)
            mime = "image/png"
        else:
            im.convert("RGB").save(buf, "JPEG", quality=90)
            mime = "image/jpeg"
    return mime, base64.b64encode(buf.getvalue()).decode()


def parse_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or code fences. Pull the JSON object out."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b > a:
        return json.loads(text[a:b + 1])
    raise ValueError("Model did not return JSON: " + text[:200])


def ask_json(provider: str, model: str, system: str, text: str, images=(), max_tokens: int = 8000) -> dict:
    """images: list of file paths, sent in order after the text. Returns the parsed JSON object."""
    provider = provider.lower()
    if provider == "claude":
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        content = []
        for p in images:
            mime, data = _b64(Path(p))
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
        content.append({"type": "text", "text": text + "\n\nReply with a single JSON object and nothing else."})
        resp = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                      messages=[{"role": "user", "content": content}])
        return parse_json("".join(b.text for b in resp.content if getattr(b, "type", "") == "text"))

    from openai import OpenAI

    client = OpenAI()
    content = [{"type": "text", "text": text}]
    for p in images:
        mime, data = _b64(Path(p))
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
    resp = client.chat.completions.create(
        model=model, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}])
    return parse_json(resp.choices[0].message.content)
