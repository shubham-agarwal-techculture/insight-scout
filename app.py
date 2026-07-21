"""Web UI server for following Insight Scout runs live."""

from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from history_store import all_previous_insights, delete_run, get_run, list_runs, save_run
from image_gen import GENERATED_DIR_NAME, generate_insight_image, image_provider
from scout import iter_scout_events

load_dotenv()

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
GENERATED = STATIC / GENERATED_DIR_NAME
GENERATED.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Insight Scout")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_run_lock = threading.Lock()


class ImageRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    twist: str = Field(default="", max_length=1200)
    insight_n: int | None = Field(default=None, ge=1, le=5)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, bool | str]:
    has_key = bool(os.environ.get("CURSOR_API_KEY", "").strip())
    return {
        "ok": True,
        "api_key_configured": has_key,
        "image_provider": image_provider(),
    }


@app.get("/api/history")
def history_list() -> list[dict]:
    return list_runs()


@app.get("/api/history/{run_id}")
def history_get(run_id: str) -> dict:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@app.delete("/api/history/{run_id}")
def history_delete(run_id: str) -> dict[str, bool]:
    if not delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"ok": True}


@app.post("/api/insights/image")
def create_insight_image(body: ImageRequest) -> dict[str, str]:
    try:
        return generate_insight_image(
            title=body.title.strip(),
            twist=body.twist.strip(),
            insight_n=body.insight_n,
            output_dir=GENERATED,
        )
    except httpx.HTTPStatusError as err:
        detail = f"Image provider HTTP {err.response.status_code}"
        try:
            payload = err.response.json()
            if isinstance(payload, dict) and payload.get("error"):
                detail = str(payload["error"])
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=502, detail=detail) from err
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/scout/stream")
def scout_stream() -> StreamingResponse:
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="CURSOR_API_KEY is not set. Add it to .env or the environment.",
        )

    if not _run_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="A scout run is already in progress. Follow it or wait.",
        )

    event_q: queue.Queue[dict | None] = queue.Queue()

    def worker() -> None:
        markdown_buffer = ""
        agent_id = ""
        run_id = ""
        previous = all_previous_insights()
        try:
            for event in iter_scout_events(
                api_key=api_key,
                cwd=str(ROOT),
                previous_insights=previous or None,
            ):
                if event.get("type") == "text":
                    markdown_buffer += event.get("text", "")
                elif event.get("type") == "started":
                    agent_id = event.get("agent_id", "")
                    run_id = event.get("run_id", "")
                elif event.get("type") == "done" and markdown_buffer.strip():
                    try:
                        saved = save_run(
                            markdown=markdown_buffer,
                            agent_id=agent_id,
                            run_id=run_id or event.get("run_id", ""),
                        )
                        event = {
                            **event,
                            "history_id": saved["id"],
                            "prior_insights_skipped": len(previous),
                        }
                    except ValueError:
                        pass
                event_q.put(event)
        except Exception as exc:  # noqa: BLE001
            event_q.put(
                {
                    "type": "error",
                    "kind": "internal",
                    "message": str(exc),
                }
            )
        finally:
            event_q.put(None)
            _run_lock.release()

    threading.Thread(target=worker, name="insight-scout", daemon=True).start()

    def sse() -> object:
        while True:
            item = event_q.get()
            if item is None:
                yield "event: end\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def main() -> None:
    import uvicorn

    host = os.environ.get("INSIGHT_SCOUT_HOST", "127.0.0.1")
    port = int(os.environ.get("INSIGHT_SCOUT_PORT", "8765"))
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
