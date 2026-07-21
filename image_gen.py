"""AI image generation for insight cards missing a source image."""

from __future__ import annotations

import base64
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx

GENERATED_DIR_NAME = "generated"


def build_prompt(*, title: str, twist: str = "") -> str:
    """Build a concise illustration prompt from insight text."""
    twist_bit = re.sub(r"\s+", " ", (twist or "").strip())[:220]
    core = title.strip()
    if twist_bit:
        core = f"{core}. {twist_bit}"
    return (
        "Editorial technical illustration, clean modern diagram style, "
        "subtle teal and warm orange accents on soft paper tones, "
        "no text, no watermark, no logos, no people faces. "
        f"Subject: {core}"
    )


def image_provider() -> str:
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "openai"
    return "pollinations"


def generate_insight_image(
    *,
    title: str,
    twist: str = "",
    insight_n: int | None = None,
    output_dir: Path,
) -> dict[str, str]:
    """
    Generate (or reuse cached) an image for an insight.

    Returns dict with keys: url, provider, path (relative under /static/).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(title=title, twist=twist)
    cache_key = hashlib.sha256(
        f"{insight_n or 0}|{title}|{twist[:120]}".encode("utf-8")
    ).hexdigest()[:16]
    filename = f"insight-{insight_n or 0}-{cache_key}.png"
    dest = output_dir / filename
    rel = f"/static/{GENERATED_DIR_NAME}/{filename}"

    if dest.exists() and dest.stat().st_size > 0:
        return {"url": rel, "provider": "cache", "path": rel}

    provider = image_provider()
    if provider == "openai":
        _generate_openai(prompt=prompt, dest=dest)
    else:
        _generate_pollinations(prompt=prompt, dest=dest)

    return {"url": rel, "provider": provider, "path": rel}


def _generate_openai(*, prompt: str, dest: Path) -> None:
    api_key = os.environ["OPENAI_API_KEY"].strip()
    model = os.environ.get("OPENAI_IMAGE_MODEL", "dall-e-3").strip() or "dall-e-3"
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        b64 = data["data"][0]["b64_json"]
        dest.write_bytes(base64.b64decode(b64))


def _generate_pollinations(*, prompt: str, dest: Path) -> None:
    """Flux-backed Pollinations endpoint — no API key required."""
    url = (
        "https://image.pollinations.ai/prompt/"
        f"{quote(prompt)}"
        "?width=1024&height=576&nologo=true&enhance=true"
    )
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        if "image" not in content_type and not response.content.startswith(b"\x89PNG"):
            raise RuntimeError("Pollinations did not return an image")
        dest.write_bytes(response.content)
