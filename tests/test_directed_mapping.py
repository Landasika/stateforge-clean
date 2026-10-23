from pathlib import Path

from stateforge.analysis.static.icfg import build_icfg
from stateforge.runtime.mapper import map_trace
from stateforge.runtime.tracer import TraceSession


CLASS_SOURCE = (
    "class User:\n"
    "    def check(self):\n"
    "        return self.helper()\n"
    "    def helper(self):\n"
    "        return 1\n"
    "\n"
    "class Admin:\n"
    "    def check(self):\n"
    "        return self.helper()\n"
    "    def helper(self):\n"
    "        return 2\n"
    "\n"
    "def run():\n"
    "    return User().check() + Admin().check()\n"
)

NESTED_SOURCE = (
    "def outer(x):\n"
    "    def inner(y):\n"
    "        if y > 0:\n"
    "            return 1\n"
    "        return 0\n"
    "    return inner(x)\n"
)


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "app.py"
    path.write_text(source, encoding="utf-8")
    return path


def _namespace(path: Path) -> dict:
    namespace: dict = {}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
    return namespace


def _execute(session, callback) -> list:
    with session.trace_execution():
        with session.request() as rid:
            callback()
    return session.drain_request_events(rid)


def test_class_methods_have_distinct_function_and_block_identity(tmp_path: Path):
    path = _write(tmp_path, CLASS_SOURCE)
    ir = build_icfg(tmp_path)
    assert "app.User.check" in ir.functions
    assert "app.Admin.check" in ir.functions
    assert ir.functions["app.User.check"].qualname == "User.check"
    assert ir.functions["app.Admin.check"].qualname == "Admin.check"
    assert ir.functions["app.User.check"].entry != ir.functions["app.Admin.check"].entry
    assert "User.check" in ir.functions["app.User.check"].entry
    assert "Admin.check" in ir.functions["app.Admin.check"].entry

    user_helper = ir.functions["app.User.helper"].entry
    admin_helper = ir.functions["app.Admin.helper"].entry
    user_calls = [edge for edge in ir.edges
                  if edge.kind == "call" and edge.dst == user_helper]
    admin_calls = [edge for edge in ir.edges
                   if edge.kind == "call" and edge.dst == admin_helper]
    assert user_calls and admin_calls
    assert all(not edge.src.startswith("app.py::Admin") for edge in user_calls)
    assert all(not edge.src.startswith("app.py::User") for edge in admin_calls)


def test_class_qualified_trace_maps_without_cross_class_confusion(tmp_path: Path):
    path = _write(tmp_path, CLASS_SOURCE)
    ir = build_icfg(tmp_path)
    namespace = _namespace(path)
    session = TraceSession(tmp_path)
    events = _execute(session, lambda: namespace["run"]())
    assert any(event.qualname == "User.check" for event in events)
    assert any(event.qualname == "Admin.check" for event in events)
    mapped = map_trace(events, ir)
    functions = {ir.blocks[block].function for block in mapped.blocks}
    assert {"User.check", "User.helper", "Admin.check", "Admin.helper",
            "run"} <= functions
    assert mapped.unresolved == []
    assert mapped.unmatched_transitions == []


def test_nested_function_qualname_maps_to_distinct_blocks(tmp_path: Path):
    path = _write(tmp_path, NESTED_SOURCE)
    ir = build_icfg(tmp_path)
    assert "app.outer.inner" in ir.functions
    assert ir.functions["app.outer.inner"].qualname == "outer.<locals>.inner"
    namespace = _namespace(path)
    session = TraceSession(tmp_path)
    events = _execute(session, lambda: namespace["outer"](2))
    mapped = map_trace(events, ir)
    functions = {ir.blocks[block].function for block in mapped.blocks}
    assert functions == {"outer", "outer.inner"}
    assert mapped.unresolved == []


def test_multiple_calls_on_one_line_keep_call_and_return_edges(tmp_path: Path):
    path = _write(tmp_path, CLASS_SOURCE)
    ir = build_icfg(tmp_path)
    namespace = _namespace(path)
    session = TraceSession(tmp_path)
    mapped = map_trace(_execute(session, lambda: namespace["run"]()), ir)
    assert not mapped.unmatched_transitions
    call_edges = {edge for edge in mapped.observed_valid_edges
                  if any(item.kind == "call" and item.src == edge[0]
                         and item.dst == edge[1] for item in ir.edges)}
    assert call_edges


def test_consecutive_blocks_can_form_an_unmatched_transition(tmp_path: Path):
    source = (
        "def f():\n"
        "    return 1\n"
        "def g():\n"
        "    return 2\n"
    )
    path = _write(tmp_path, source)
    ir = build_icfg(tmp_path)
    namespace = _namespace(path)
    session = TraceSession(tmp_path)

    def call_both():
        namespace["f"]()
        namespace["g"]()

    events = _execute(session, call_both)
    mapped = map_trace(events, ir)
    valid = {(edge.src, edge.dst) for edge in ir.edges}
    assert all(edge in valid for edge in mapped.observed_valid_edges)
    assert mapped.unmatched_transitions
    assert all(edge not in valid for edge in mapped.unmatched_transitions)


def test_two_requests_do_not_share_mapped_edges(tmp_path: Path):
    source = (
        "def f():\n"
        "    return 1\n"
        "def g():\n"
        "    return 2\n"
    )
    path = _write(tmp_path, source)
    ir = build_icfg(tmp_path)
    namespace = _namespace(path)
    session = TraceSession(tmp_path)
    with session.trace_execution():
        with session.request() as first:
            namespace["f"]()
        with session.request() as second:
            namespace["g"]()
    first_events = session.drain_request_events(first)
    second_events = session.drain_request_events(second)
    first_map = map_trace(first_events, ir)
    second_map = map_trace(second_events, ir)
    assert all(ir.blocks[block].function == "f" for block in first_map.blocks)
    assert all(ir.blocks[block].function == "g" for block in second_map.blocks)
    assert not first_map.unmatched_transitions
    assert not second_map.unmatched_transitions
    assert session.events == []


def test_same_callee_twice_on_one_line_maps_both_returnsites(tmp_path: Path):
    source = (
        "def h():\n"
        "    return 1\n"
        "def run():\n"
        "    return h() + h()\n"
    )
    path = _write(tmp_path, source)
    ir = build_icfg(tmp_path)
    namespace = _namespace(path)
    session = TraceSession(tmp_path)
    mapped = map_trace(_execute(session, lambda: namespace["run"]()), ir)
    assert mapped.unresolved == []
    assert mapped.unmatched_transitions == []
    returnsite_hits = [
        block for block in mapped.blocks
        if ir.blocks[block].kind == "returnsite"
        and ir.blocks[block].function == "run"
    ]
    assert returnsite_hits
