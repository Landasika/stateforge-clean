
from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any


@dataclass
class TraceEvent:
    request_id: int
    index: int
    file: str
    function: str
    line: int
    event_type: str = "line"
    qualname: str = ""


_SELF_FILE = __file__      


class TraceSession:
    def __init__(self, root: str | Path | None = None):
        self.root = str(Path(root).resolve()) if root else None
        self.events: list[TraceEvent] = []
        self._request_id = 0
        self._request_indices: dict[int, int] = {}
        self._previous = None
        self._lock = threading.Lock()
        self._file_cache: dict[str, tuple[bool, str]] = {}
        self._local = threading.local()
        self._active_request = 0

    def start_request(self) -> int:
        with self._lock:
            rid = self._request_id
            self._request_id += 1
            self._request_indices[rid] = 0
        return rid

    def _trace(self, frame, event, arg):
        if frame.f_code.co_filename == _SELF_FILE:
            return None                     
        if event not in {"call", "line", "return", "exception"}:
            return self._trace
        filename = frame.f_code.co_filename
        cached = self._file_cache.get(filename)
        if cached is None:
            resolved = str(Path(filename).resolve())
            if self.root is None:
                cached = (True, resolved)
            else:
                inside = resolved == self.root or resolved.startswith(self.root + os.sep)
                cached = (inside, resolved)
            self._file_cache[filename] = cached
        inside, resolved = cached
        if inside:
            rid = getattr(self._local, "request_id", 0)
            with self._lock:
                index = self._request_indices.get(rid, 0)
                self._request_indices[rid] = index + 1
                qualname = getattr(frame.f_code, "co_qualname",
                                   frame.f_code.co_name)
                self.events.append(TraceEvent(rid, index, resolved,
                                              frame.f_code.co_name,
                                              frame.f_lineno, event,
                                              qualname=qualname))
        return self._trace

    def __enter__(self):
        self._previous = sys.gettrace()
        self._previous_request = getattr(self._local, "request_id", None)
        rid = self.start_request()
        self._active_request = rid
        self._local.request_id = rid
        sys.settrace(self._trace)
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.settrace(self._previous)
        previous = getattr(self, "_previous_request", None)
        self._local.request_id = previous
        self._active_request = previous if previous is not None else 0
        return False

    def request(self):
        session = self

        class _Request:
            def __enter__(self):
                self._previous = getattr(session._local, "request_id", None)
                rid = session.start_request()
                session._local.request_id = rid
                session._active_request = rid
                return rid

            def __exit__(self, exc_type, exc, tb):
                previous = self._previous
                session._local.request_id = previous
                session._active_request = previous if previous is not None else 0
                return False

        return _Request()

    @contextlib.contextmanager
    def trace_execution(self):
        previous = sys.gettrace()
        sys.settrace(self._trace)
        try:
            yield
        finally:
            sys.settrace(previous)

    def drain_request_events(self, request_id: int) -> list[TraceEvent]:
        with self._lock:
            drained = [event for event in self.events
                       if event.request_id == request_id]
            if drained:
                self.events = [event for event in self.events
                               if event.request_id != request_id]
            self._request_indices.pop(request_id, None)
        return drained

    @contextlib.contextmanager
    def untraced(self):
        prev = sys.gettrace()
        sys.settrace(None)
        try:
            yield
        finally:
            sys.settrace(prev)
    def to_dict(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self.events]

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> list[TraceEvent]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("events", raw.get("trace", []))
        return [TraceEvent(**item) for item in raw]
