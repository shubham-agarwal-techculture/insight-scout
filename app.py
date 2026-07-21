"""Web UI server for following Insight Scout runs live."""

from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from scout import iter_scout_events

load_dotenv()

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Insight Scout")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_run_lock = threading.Lock()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, bool | str]:
    has_key = bool(os.environ.get("CURSOR_API_KEY", "").strip())
    return {"ok": True, "api_key_configured": has_key}


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
        try:
            for event in iter_scout_events(api_key=api_key, cwd=str(ROOT)):
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

    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )


if __name__ == "__main__":
    main()
