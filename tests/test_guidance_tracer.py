import json
from pathlib import Path

from stateforge.fuzzing.atheris_runner import (
    TraceJsonlWriter,
    build_input_handler,
)
from stateforge.runtime.tracer import TraceSession

SOURCE = (
    "def f():\n"
    "    return 1\n"
    "def g():\n"
    "    return 2\n"
)


def _namespace(tmp_path: Path) -> dict:
    source = tmp_path / "app.py"
    source.write_text(SOURCE, encoding="utf-8")
    namespace: dict = {}
    exec(compile(SOURCE, str(source), "exec"), namespace)
    return namespace


def test_drain_returns_only_the_requested_execution(tmp_path: Path):
    namespace = _namespace(tmp_path)
    session = TraceSession(tmp_path)
    with session:
        with session.request() as first:
            namespace["f"]()
        with session.request() as second:
            namespace["g"]()
        second_events = session.drain_request_events(second)
        assert second_events
        assert all(event.request_id == second for event in second_events)
        assert all(event.function == "g" for event in second_events)
        assert session.events
        assert all(event.request_id == first for event in session.events)
        assert second not in session._request_indices
        first_events = session.drain_request_events(first)
        assert first_events
        assert session.events == []


def test_nested_requests_restore_the_outer_request(tmp_path: Path):
    namespace = _namespace(tmp_path)
    session = TraceSession(tmp_path)
    with session:
        with session.request() as outer:
            with session.request() as inner:
                namespace["f"]()
            namespace["g"]()
        inner_events = session.drain_request_events(inner)
        outer_events = session.drain_request_events(outer)
    assert inner_events
    assert all(event.function == "f" for event in inner_events)
    assert outer_events
    assert all(event.function == "g" for event in outer_events)


def test_trace_execution_scope_works_without_global_session_context(tmp_path: Path):
    namespace = _namespace(tmp_path)
    session = TraceSession(tmp_path)
    with session.trace_execution():
        with session.request() as rid:
            namespace["f"]()
    events = session.drain_request_events(rid)
    assert events
    assert all(event.request_id == rid for event in events)


def test_bounded_handler_releases_events_and_writes_isolated_records(
        tmp_path: Path):
    namespace = _namespace(tmp_path)

    class Adapter:
        def __init__(self):
            self.calls = 0

        def execute(self, data: bytes):
            self.calls += 1
            namespace["f" if data == b"f" else "g"]()

    session = TraceSession(tmp_path)
    writer = TraceJsonlWriter(tmp_path / "trace.jsonl")
    handler = build_input_handler(Adapter(), session, writer, bounded=True)
    with session:
        handler(b"f")
        handler(b"g")
    assert session.events == []
    records = [json.loads(line) for line in
               (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert len(records) == 2
    assert {record["events"][0]["function"] for record in records} == {"f", "g"}
    for record in records:
        assert {event["request_id"] for event in record["events"]} == {
            record["request_id"]}


def test_default_handler_preserves_accumulating_semantics(tmp_path: Path):
    namespace = _namespace(tmp_path)

    class Adapter:
        def execute(self, data: bytes):
            namespace["f"]()

    session = TraceSession(tmp_path)
    handler = build_input_handler(Adapter(), session)
    with session:
        handler(b"x")
    assert session.events
    assert not (tmp_path / "trace.jsonl").exists()


def test_long_running_request_drain_keeps_memory_bounded(tmp_path: Path):
    namespace = _namespace(tmp_path)
    session = TraceSession(tmp_path)
    with session.trace_execution():
        for _ in range(500):
            with session.request() as rid:
                namespace["f"]()
            events = session.drain_request_events(rid)
            assert events
            assert session.events == []
    assert not session._request_indices


def test_draining_unknown_request_returns_empty(tmp_path: Path):
    session = TraceSession(tmp_path)
    assert session.drain_request_events(999) == []
