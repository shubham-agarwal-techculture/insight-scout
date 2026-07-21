"""Windows workarounds for cursor-sdk local bridge launch.

The bundled bridge discovery path uses selectors.DefaultSelector on a
subprocess pipe. On Windows, select() only accepts sockets, which raises
WinError 10038. This module replaces discovery with a threaded line reader.

Also avoids callback auth tokens that start with '-', which the bridge argv
parser rejects as missing flag values.
"""

from __future__ import annotations

import queue
import secrets
import sys
import threading
import time
from typing import Any, Mapping

from cursor_sdk import _bridge, _store_callback, _tool_callback
from cursor_sdk.errors import CursorSDKError


def _safe_auth_token() -> str:
    token = secrets.token_urlsafe(32)
    while token.startswith("-"):
        token = secrets.token_urlsafe(32)
    return token


def _read_discovery_windows(
    process: Any, timeout: float
) -> Mapping[str, Any]:
    if process.stderr is None:
        raise CursorSDKError("Bridge process stderr is unavailable")

    lines: queue.Queue[tuple[str, str | BaseException | None]] = queue.Queue()

    def _reader() -> None:
        try:
            assert process.stderr is not None
            for line in process.stderr:
                lines.put(("line", line))
            lines.put(("eof", None))
        except BaseException as exc:  # noqa: BLE001 — surface to waiter
            lines.put(("err", exc))

    thread = threading.Thread(target=_reader, name="cursor-bridge-stderr", daemon=True)
    thread.start()

    deadline = time.monotonic() + timeout
    stderr_lines: list[str] = []

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            kind, payload = lines.get(timeout=min(0.1, max(remaining, 0.0)))
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break
            continue

        if kind == "err":
            assert isinstance(payload, BaseException)
            raise CursorSDKError(
                f"Failed reading bridge discovery: {payload}"
            ) from payload

        if kind == "eof":
            break

        assert isinstance(payload, str)
        stderr_lines.append(payload)
        discovery = _bridge.parse_discovery_line(payload)
        if discovery is not None:
            return discovery

    exit_code = process.poll()
    if exit_code is not None:
        raise CursorSDKError(
            f"Bridge exited before discovery with status {exit_code}: "
            + "".join(stderr_lines)
        )
    raise CursorSDKError("Timed out waiting for bridge discovery")


def apply() -> None:
    """Install Windows-only patches. No-op on non-Windows."""
    if sys.platform != "win32":
        return

    _tool_callback._new_auth_token = _safe_auth_token  # type: ignore[attr-defined]
    _store_callback._new_auth_token = _safe_auth_token  # type: ignore[attr-defined]
    _bridge._read_discovery = _read_discovery_windows  # type: ignore[attr-defined]
