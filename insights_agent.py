"""
One-shot CLI for Insight Scout (same agent as the web UI).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from scout import iter_scout_events


def main() -> int:
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        print(
            "Set CURSOR_API_KEY (Dashboard → Integrations / API Keys).",
            file=sys.stderr,
        )
        return 1

    exit_code = 0
    for event in iter_scout_events(api_key=api_key):
        kind = event.get("type")
        if kind == "started":
            print(
                f"agent={event['agent_id']} run={event['run_id']}",
                file=sys.stderr,
            )
        elif kind == "text":
            print(event["text"], end="", flush=True)
        elif kind == "done":
            print()
        elif kind == "error":
            print(event.get("message", "error"), file=sys.stderr)
            exit_code = 1 if event.get("kind") == "startup" else 2

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
