"""Start Insight Scout and run scouts on startup, then every hour."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_INTERVAL_SEC = 3600
HEALTH_TIMEOUT_SEC = 90
HEALTH_POLL_SEC = 0.5


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{stamp}] {message}", flush=True)


def python_executable() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python)
    venv_python_unix = ROOT / ".venv" / "bin" / "python"
    if venv_python_unix.is_file():
        return str(venv_python_unix)
    return sys.executable


def base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def wait_for_server(client: httpx.Client, timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/health", timeout=5.0)
            if response.status_code == 200:
                payload = response.json()
                if not payload.get("api_key_configured"):
                    raise RuntimeError(
                        "CURSOR_API_KEY is not set. Add it to .env, then retry."
                    )
                log("Server is ready.")
                return
        except RuntimeError:
            raise
        except httpx.HTTPError:
            pass
        time.sleep(HEALTH_POLL_SEC)
    raise TimeoutError(f"Server did not become ready within {timeout_sec:.0f}s.")


def format_event(payload: dict) -> str | None:
    event_type = payload.get("type")
    if event_type == "phase":
        return f"phase · {payload.get('phase')} · {payload.get('detail', '')}".strip()
    if event_type == "started":
        return f"started · agent {payload.get('agent_id')} · run {payload.get('run_id')}"
    if event_type == "tool":
        return f"tool · {payload.get('name')} · {payload.get('status')}"
    if event_type == "status":
        message = payload.get("message")
        return f"status · {message}" if message else None
    if event_type == "done":
        skipped = payload.get("prior_insights_skipped")
        if skipped:
            return f"done · status {payload.get('status')} · skipped {skipped} past insights"
        return f"done · status {payload.get('status')}"
    if event_type == "error":
        return f"error · {payload.get('message', 'unknown error')}"
    return None


def run_scout(client: httpx.Client) -> bool:
    log("Starting scout run…")
    timeout = httpx.Timeout(None, connect=30.0)
    with client.stream("GET", "/api/scout/stream", timeout=timeout) as response:
        if response.status_code == 409:
            log("Scout skipped: another run is already in progress.")
            return False
        if response.status_code == 503:
            log("Scout failed: CURSOR_API_KEY is not configured.")
            return False
        response.raise_for_status()

        ok = True
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("event: end"):
                log("Scout stream finished.")
                break
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            message = format_event(payload)
            if message:
                log(message)
            if payload.get("type") == "error":
                ok = False
        return ok


def start_server_process(host: str, port: int) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["INSIGHT_SCOUT_HOST"] = host
    env["INSIGHT_SCOUT_PORT"] = str(port)
    return subprocess.Popen(
        [python_executable(), str(ROOT / "app.py")],
        cwd=str(ROOT),
        env=env,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Insight Scout and trigger scouts hourly."
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SEC,
        help="Seconds to wait between scout runs (default: 3600)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run only the initial scout, then exit (server keeps running until Ctrl+C)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval < 1:
        log("--interval must be at least 1 second.")
        return 2

    url = base_url(args.host, args.port)
    log(f"Launching Insight Scout at {url}")

    server = start_server_process(args.host, args.port)
    exit_code = 0

    try:
        with httpx.Client(base_url=url) as client:
            wait_for_server(client, HEALTH_TIMEOUT_SEC)

            run_number = 0
            while True:
                run_number += 1
                log(f"Scout #{run_number}")
                if not run_scout(client):
                    exit_code = 1

                if args.once:
                    log("Initial scout complete (--once). Press Ctrl+C to stop the server.")
                    while server.poll() is None:
                        time.sleep(1)
                    break

                log(f"Next scout in {args.interval} seconds.")
                deadline = time.monotonic() + args.interval
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise RuntimeError("Server process exited unexpectedly.")
                    time.sleep(min(HEALTH_POLL_SEC, deadline - time.monotonic()))

    except KeyboardInterrupt:
        log("Stopping.")
    except Exception as exc:  # noqa: BLE001
        log(f"Fatal error: {exc}")
        exit_code = 1
    finally:
        if server.poll() is None:
            log("Shutting down server…")
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
