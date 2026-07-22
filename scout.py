"""Shared prompt and Cursor agent event stream for Insight Scout."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import win_bridge_patch

win_bridge_patch.apply()

from cursor_sdk import Agent, CursorAgentError, LocalAgentOptions

BASE_PROMPT = """
You are a technical insight scout. Your only job is to find and deliver exactly
5 insights about NEW or emerging technologies that would make a sharp reader
stop and say: "I never expected that — and that's amazing."

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

## Writing for effortless reading (non-negotiable)
Follow web-writing research (plain language, inverted pyramid, scannable text):
- Lead with the conclusion. First line = the surprising fact.
- Use everyday words. If a technical term is required, explain it in the same
  sentence in plain English.
- Keep sentences short (aim under 22 words). One idea per sentence or bullet.
- Keep every real number, name, and mechanism — just say them simply.
- No academic throat-clearing, no stacked jargon, no marketing hype.
- Prefer bullets over long paragraphs. Never write a wall of text.

## Headlines (the insight title — non-negotiable)
Each insight title is a headline. Write it in the simplest words possible so a
sharp reader notices — but never sounds like clickbait or marketing.
- Plain and specific: name the thing and the surprising angle in everyday
  language (e.g. "Heat flows one way in graphite", not "Graphite's thermal
  asymmetry via hydrodynamic phonon transport").
- Subtle pull: interest comes from a true, concrete fact — not from hype words,
  exclamation marks, or breathless tone.
- No false exaggeration: do not use superlatives ("fastest", "first ever",
  "revolutionary") unless the cited sources literally support that exact claim.
- Never use clickbait patterns: no "you won't believe", "game-changer",
  "everything changes", "scientists shocked", "secret", "breakthrough that…",
  question hooks, or stacked adjectives.
- Max 8 words. If two titles work, pick the shorter and simpler one.

## Output format
Return exactly 5 insights. For each, use this exact shape:

### Insight N: <headline — simple, specific, max 8 words>
- **In short:** One sentence. The surprising fact in plain words. A smart
  non-specialist should get it on first read.
- **How it works:** Exactly 3 bullets. Each bullet is one short sentence.
  Bullet 1 = what happened / the result (include the key number if any).
  Bullet 2 = the simple mechanism (how/why, in plain English).
  Bullet 3 = why that mechanism is surprising or elegant.
- **Proof:** Exactly 2 lines, each: `[Source title](https://url)` — one line
  per independent source that agrees on the core claim.
- **Easy to miss because:** One short sentence on the popular narrative this
  quietly breaks.
- **Image:** a single direct https URL to a relevant figure, diagram, photo, or
  illustration (PNG/JPG/WebP/GIF/SVG). Prefer an image from one of the cited
  sources (press kit, paper figure, lab photo). Never invent a URL. If no
  trustworthy direct image URL exists, write `none` — the UI will generate an
  AI illustration automatically.

Do not pad with fluff. Do not write a preamble or closing essay. Start with
Insight 1.
""".strip()

PROMPT = BASE_PROMPT


def build_prompt(
    previous_insights: list[dict[str, str]] | None = None,
) -> str:
    """Build the scout prompt, optionally excluding past discoveries."""
    if not previous_insights:
        return BASE_PROMPT

    lines = [
        "",
        "## Previously delivered insights (DO NOT repeat)",
        "These insights were already produced in earlier scout runs. You MUST",
        "find entirely different topics, mechanisms, technologies, and sources.",
        "Do not rephrase, lightly vary, or revisit the same underlying fact.",
        "Cross-reference this list before finalizing each insight and discard",
        "anything that overlaps in topic or core claim.",
        "",
    ]
    for idx, item in enumerate(previous_insights, start=1):
        title = (item.get("title") or "").strip()
        takeaway = (item.get("takeaway") or "").strip()
        if not title:
            continue
        line = f"{idx}. **{title}**"
        if takeaway:
            line += f" — {takeaway}"
        lines.append(line)

    lines.append("")
    return BASE_PROMPT + "\n".join(lines)


def iter_scout_events(
    *,
    api_key: str,
    cwd: str | None = None,
    previous_insights: list[dict[str, str]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield JSON-serializable events while a scout run executes."""
    workspace = cwd or os.getcwd()
    prompt = build_prompt(previous_insights)
    prior_count = len(previous_insights or [])
    if prior_count:
        detail = f"Launching local agent · avoiding {prior_count} past insights"
    else:
        detail = "Launching local agent"
    yield {"type": "phase", "phase": "starting", "detail": detail}

    try:
        with Agent.create(
            model="composer-2.5",
            api_key=api_key,
            local=LocalAgentOptions(cwd=workspace),
        ) as agent:
            run = agent.send(prompt)
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
