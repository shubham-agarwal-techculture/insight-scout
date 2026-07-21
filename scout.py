"""Shared prompt and Cursor agent event stream for Insight Scout."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import win_bridge_patch

win_bridge_patch.apply()

from cursor_sdk import Agent, CursorAgentError, LocalAgentOptions

PROMPT = """
You are a technical insight scout. Your only job is to find and deliver exactly
5 insights about NEW or emerging technologies that would make a sharp technical
reader stop and say: "I never expected that — and that's amazing."

## What "astonishing" means here
- Unexpected: the reader would not have guessed this from common headlines.
- Positive: wonder, capability, elegance, or a surprising upside — not doom,
  scams, or "everything is broken" takes.
- Concrete: a specific mechanism, result, measurement, or architectural twist —
  not a vague "AI is changing everything" claim.

## Research and legitimacy rules (non-negotiable)
1. Prefer primary or near-primary sources: peer-reviewed papers, conference
   proceedings, official lab/company technical blogs, standards docs, patents
   with demonstrated prototypes, reputable scientific press summarizing those.
2. Require redundancy: every insight must be cross-checked against at least TWO
   independent sources that agree on the core claim. If you cannot find a second
   independent confirmation, discard the insight and find another.
3. Explicitly reject: unverified social posts, single-blog rumor, marketing
   copy with no technical backing, and claims that only one outlet is pushing.
4. Prefer recent developments (roughly last 24 months) unless an older result
   suddenly became practically relevant in a surprising way.
5. Use web search / browsing freely. Cite sources with titles and URLs.

## Output format
Return exactly 5 insights. For each:

### Insight N: <short punchy title>
- **The twist:** 2–4 sentences. Lead with the counterintuitive fact, then the
  technical why. Write so a senior engineer feels the "wait — really?" moment.
- **Why it's legit:** name the independent sources that agree (title + URL).
- **Why you'd miss it:** one sentence on what popular narrative this breaks.
- **Image:** a single direct https URL to a relevant figure, diagram, photo, or
  illustration (PNG/JPG/WebP/GIF/SVG). Prefer an image from one of the cited
  sources (press kit, paper figure, lab photo). Never invent a URL. If no
  trustworthy direct image URL exists, write `none` — the UI will generate an
  AI illustration automatically.

Do not pad with fluff. Do not write a preamble or closing essay. Start with
Insight 1.
""".strip()


def iter_scout_events(
    *,
    api_key: str,
    cwd: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield JSON-serializable events while a scout run executes."""
    workspace = cwd or os.getcwd()
    yield {"type": "phase", "phase": "starting", "detail": "Launching local agent"}

    try:
        with Agent.create(
            model="composer-2.5",
            api_key=api_key,
            local=LocalAgentOptions(cwd=workspace),
        ) as agent:
            run = agent.send(PROMPT)
            yield {
                "type": "started",
                "agent_id": agent.agent_id,
                "run_id": run.id,
            }
            yield {
                "type": "phase",
                "phase": "researching",
                "detail": "Verifying claims across redundant sources",
            }

            for message in run.stream():
                msg_type = getattr(message, "type", "")

                if msg_type == "tool_call":
                    yield {
                        "type": "tool",
                        "name": getattr(message, "name", "tool"),
                        "status": getattr(message, "status", ""),
                        "call_id": getattr(message, "call_id", ""),
                    }
                elif msg_type == "thinking":
                    text = (getattr(message, "text", "") or "").strip()
                    if text:
                        yield {
                            "type": "thinking",
                            "text": text[:280] + ("…" if len(text) > 280 else ""),
                        }
                elif msg_type == "status":
                    yield {
                        "type": "status",
                        "status": getattr(message, "status", ""),
                        "message": getattr(message, "message", ""),
                    }
                elif msg_type == "assistant":
                    content = getattr(getattr(message, "message", None), "content", ())
                    for block in content:
                        if getattr(block, "type", "") == "text":
                            chunk = getattr(block, "text", "") or ""
                            if chunk:
                                yield {"type": "text", "text": chunk}

            result = run.wait()
            if result.status == "error":
                yield {
                    "type": "error",
                    "kind": "run",
                    "message": f"Run failed: {result.id}",
                }
                return

            yield {
                "type": "done",
                "status": result.status,
                "run_id": result.id,
            }

    except CursorAgentError as err:
        yield {
            "type": "error",
            "kind": "startup",
            "message": err.message,
            "retryable": bool(getattr(err, "is_retryable", False)),
        }
