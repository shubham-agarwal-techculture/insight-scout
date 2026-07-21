"""Local JSON persistence for completed Insight Scout runs."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_HISTORY_FILE = Path(__file__).resolve().parent / "data" / "scout_history.json"


def _ensure_file() -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _HISTORY_FILE.exists():
        _HISTORY_FILE.write_text('{"runs":[]}', encoding="utf-8")


def _read() -> dict[str, list[dict[str, Any]]]:
    _ensure_file()
    try:
        data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {"runs": []}
    if not isinstance(data.get("runs"), list):
        data = {"runs": []}
    return data


def _write(data: dict[str, list[dict[str, Any]]]) -> None:
    _ensure_file()
    _HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_insights(markdown: str) -> list[dict[str, Any]]:
    """Parse scout markdown into structured insight dicts."""
    parts = re.split(r"^###\s+Insight\s+(\d+)\s*:\s*", markdown, flags=re.MULTILINE | re.IGNORECASE)
    items: list[dict[str, Any]] = []
    for i in range(1, len(parts), 2):
        n = int(parts[i])
        body = parts[i + 1] if i + 1 < len(parts) else ""
        title_match = re.match(r"^([^\n]+)", body)
        title = (title_match.group(1) if title_match else f"Insight {n}").strip()
        items.append(
            {
                "n": n,
                "title": title,
                "takeaway": _extract_field(body, "In short") or _extract_field(body, "The twist"),
                "how": _extract_field(body, "How it works") or _extract_field(body, "The twist"),
                "proof": _extract_field(body, "Proof") or _extract_field(body, "Why it's legit"),
                "miss": _extract_field(body, "Easy to miss because")
                or _extract_field(body, "Why you'd miss it"),
                "image": _extract_image_url(body),
                "raw": body.strip(),
            }
        )
    return items


def _extract_field(body: str, label: str) -> str:
    escaped = re.escape(label)
    pattern = (
        rf"\*\*{escaped}:\*\*\s*"
        r"([\s\S]*?)"
        r"(?=\n\s*-\s*\*\*|\n###|$)"
    )
    match = re.search(pattern, body, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_image_url(body: str) -> str:
    field = _extract_field(body, "Image")
    if field and not re.match(r"^none\b", field, flags=re.IGNORECASE):
        url_match = re.search(r"https?://[^\s)<>'\"]+", field)
        if url_match:
            return url_match.group(0).rstrip(".,;:")
    md_match = re.search(r"!\[[^\]]*]\(\s*(https?://[^)\s]+)\s*\)", body, flags=re.IGNORECASE)
    return md_match.group(1).rstrip(".,;:") if md_match else ""


def save_run(
    *,
    markdown: str,
    agent_id: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Persist a completed scout run and return the saved record."""
    insights = parse_insights(markdown)
    if not insights:
        raise ValueError("No insights found in markdown — run not saved.")

    record: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "run_id": run_id,
        "markdown": markdown,
        "insights": insights,
    }

    with _LOCK:
        data = _read()
        data["runs"].insert(0, record)
        _write(data)

    return record


def list_runs() -> list[dict[str, Any]]:
    """Return run summaries (newest first), without full markdown."""
    with _LOCK:
        data = _read()
    summaries = []
    for run in data["runs"]:
        insights = run.get("insights") or []
        summaries.append(
            {
                "id": run["id"],
                "created_at": run.get("created_at", ""),
                "agent_id": run.get("agent_id", ""),
                "run_id": run.get("run_id", ""),
                "insight_count": len(insights),
                "titles": [i.get("title", "") for i in insights[:5]],
            }
        )
    return summaries


def get_run(run_id: str) -> dict[str, Any] | None:
    """Return a full run record by id."""
    with _LOCK:
        data = _read()
    for run in data["runs"]:
        if run.get("id") == run_id:
            return run
    return None


def delete_run(run_id: str) -> bool:
    """Delete a run by id. Returns True if found and removed."""
    with _LOCK:
        data = _read()
        before = len(data["runs"])
        data["runs"] = [r for r in data["runs"] if r.get("id") != run_id]
        if len(data["runs"]) == before:
            return False
        _write(data)
    return True


def all_previous_insights() -> list[dict[str, str]]:
    """Collect title + takeaway from every past run for deduplication."""
    with _LOCK:
        data = _read()
    seen: set[str] = set()
    previous: list[dict[str, str]] = []
    for run in data["runs"]:
        for insight in run.get("insights") or []:
            title = (insight.get("title") or "").strip()
            takeaway = (insight.get("takeaway") or "").strip()
            if not title:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            previous.append({"title": title, "takeaway": takeaway})
    return previous
