
import ast
from pathlib import Path

from stateforge.analysis.static.icfg import build_icfg
from stateforge.analysis.static.predicate import (
    PredicateInfo,
    UnsupportedPredicate,
    extract_predicate,
    extract_predicates,
)
from stateforge.core.ir import BasicBlock, FlowEdge, ProgramIR
from stateforge.fuzzing.feedback.distance import target_distances
from stateforge.fuzzing.guidance.deviation import find_deviation_points
from stateforge.runtime.mapper import map_trace
from stateforge.runtime.tracer import TraceSession
from stateforge.adapters.callable import CallableAdapter
from examples.m1_target import target
from tests.helpers import build_example_ir, target_block_id


SUPPORTED_SOURCE = (
    "def target(a, b, c, d, e, f, data, name):\n"
    "    if a == 1:\n"
    "        target_block()\n"
    "    if b != 2:\n"
    "        target_block()\n"
    "    if c > 3:\n"
    "        target_block()\n"
    "    if d >= 4:\n"
    "        target_block()\n"
    "    if e < 5:\n"
    "        target_block()\n"
    "    if f <= 6:\n"
    "        target_block()\n"
    "    if data[:4] == b'MAGC':\n"
    "        target_block()\n"
    "    if name == 'admin':\n"
    "        target_block()\n"
    "def target_block():\n"
    "    return 1\n"
)

UNSUPPORTED_SOURCE = (
    "def target(x, y, values, predicate):\n"
    "    if 0 < x < 10:\n"
    "        return\n"
    "    if x > 1 and y < 2:\n"
    "        return\n"
    "    if x in values:\n"
    "        return\n"
    "    if not x:\n"
    "        return\n"
    "    if len(values) == 1:\n"
    "        return\n"
    "    if predicate(x):\n"
    "        return\n"
    "    for item in values:\n"
    "        return\n"
)


def _normal(expression: str) -> str:
    return ast.unparse(ast.parse(expression, mode="eval"))


def _branch_for(ir, expression: str) -> str:
    normalized = _normal(expression)
    for block_id, block in ir.blocks.items():
        if block.kind != "branch":
            continue
        if any(statement == f"<test> {normalized}"
               for statement in block.statements):
            return block_id
    raise AssertionError(f"branch not found: {expression}")


def _source_file(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "app.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_supported_comparisons_map_to_cfg(tmp_path: Path):
    _source_file(tmp_path, SUPPORTED_SOURCE)
    ir = build_icfg(tmp_path)
    extraction = extract_predicates(ir)
    operators = {
        "a == 1": "==",
        "b != 2": "!=",
        "c > 3": ">",
        "d >= 4": ">=",
        "e < 5": "<",
        "f <= 6": "<=",
        "data[:4] == b'MAGC'": "==",
        "name == 'admin'": "==",
    }
    by_block = extraction.by_block()
    for expression, operator in operators.items():
        block_id = _branch_for(ir, expression)
        predicate = by_block[block_id]
        assert predicate.block_id == block_id
        assert predicate.operator == operator
        assert predicate.expression == _normal(expression)
        assert predicate.source_file == ir.blocks[block_id].file
        assert predicate.line == ir.blocks[block_id].start_line
        assert predicate.true_successor == next(
            edge.dst for edge in ir.outgoing(block_id) if edge.kind == "true")
        assert predicate.false_successor == next(
            edge.dst for edge in ir.outgoing(block_id) if edge.kind == "false")
        assert predicate.outcome_for(predicate.true_successor) is True
        assert predicate.outcome_for(predicate.false_successor) is False
        assert predicate.outcome_for(None) is None
        assert predicate.outcome_for("missing") is None


def test_literal_operand_metadata(tmp_path: Path):
    _source_file(tmp_path, SUPPORTED_SOURCE)
    ir = build_icfg(tmp_path)
    extraction = extract_predicates(ir)
    integer = extraction.get(_branch_for(ir, "a == 1"))
    assert integer.literal == "1"
    assert integer.literal_side == "right"
    magic = extraction.get(_branch_for(ir, "data[:4] == b'MAGC'"))
    assert magic.literal == "b'MAGC'"
    assert magic.literal_side == "right"
    name = extraction.get(_branch_for(ir, "name == 'admin'"))
    assert name.literal == "'admin'"
    assert name.literal_side == "right"


def test_predicate_ids_are_deterministic_and_do_not_collide(tmp_path: Path):
    _source_file(tmp_path, SUPPORTED_SOURCE)
    ir = build_icfg(tmp_path)
    first = extract_predicates(ir)
    second = extract_predicates(ir)
    first_ids = [predicate.predicate_id for predicate in first.predicates]
    second_ids = [predicate.predicate_id for predicate in second.predicates]
    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))
    assert all(predicate_id.startswith("pred_")
               for predicate_id in first_ids)
    assert all(predicate_id not in ir.blocks
               for predicate_id in first_ids)


def test_extraction_can_be_limited_to_selected_blocks(tmp_path: Path):
    _source_file(tmp_path, SUPPORTED_SOURCE)
    ir = build_icfg(tmp_path)
    block_id = _branch_for(ir, "c > 3")
    extraction = extract_predicates(ir, [block_id])
    assert len(extraction.predicates) == 1
    assert extraction.predicates[0].block_id == block_id


def test_unsupported_expressions_are_classified(tmp_path: Path):
    _source_file(tmp_path, UNSUPPORTED_SOURCE)
    ir = build_icfg(tmp_path)
    extraction = extract_predicates(ir)
    expected = {
        "0 < x < 10": "chained_comparison",
        "x > 1 and y < 2": "boolean_expression",
        "x in values": "unsupported_operator",
        "not x": "unary_expression",
        "len(values) == 1": "unsupported_operand",
        "predicate(x)": "function_call",
        "values": "unsupported_expression",
    }
    for expression, reason in expected.items():
        block_id = _branch_for(ir, expression)
        item = extraction.unsupported_for(block_id)
        assert isinstance(item, UnsupportedPredicate)
        assert item.reason == reason
        assert extraction.get(block_id) is None


def test_missing_source_is_classified(tmp_path: Path):
    ir = ProgramIR()
    ir.blocks["branch"] = BasicBlock(
        "branch", str(tmp_path / "missing.py"), "app", "f", 1, 1,
        "branch", ["<test> x == 1"], [1])
    ir.blocks["yes"] = BasicBlock("yes", "app.py", "app", "f", 2, 2)
    ir.blocks["no"] = BasicBlock("no", "app.py", "app", "f", 3, 3)
    ir.add_edge(FlowEdge("branch", "yes", "true"))
    ir.add_edge(FlowEdge("branch", "no", "false"))
    item = extract_predicate(ir, "branch")
    assert isinstance(item, UnsupportedPredicate)
    assert item.reason == "source_unavailable"


def test_source_syntax_error_is_classified(tmp_path: Path):
    path = tmp_path / "broken.py"
    path.write_text("def f(x):\n    if x ==\n", encoding="utf-8")
    ir = ProgramIR()
    ir.blocks["branch"] = BasicBlock(
        "branch", str(path), "broken", "f", 2, 2, "branch",
        ["<test> x == 1"], [2])
    ir.blocks["yes"] = BasicBlock("yes", "app.py", "broken", "f", 3, 3)
    ir.blocks["no"] = BasicBlock("no", "app.py", "broken", "f", 4, 4)
    ir.add_edge(FlowEdge("branch", "yes", "true"))
    ir.add_edge(FlowEdge("branch", "no", "false"))
    item = extract_predicate(ir, "branch")
    assert isinstance(item, UnsupportedPredicate)
    assert item.reason == "source_syntax_error"


def test_source_line_mismatch_is_classified(tmp_path: Path):
    path = tmp_path / "app.py"
    path.write_text(
        "def f(x):\n"
        "    if x == 2:\n"
        "        return 1\n",
        encoding="utf-8")
    ir = ProgramIR()
    ir.blocks["branch"] = BasicBlock(
        "branch", str(path), "app", "f", 2, 2, "branch",
        ["<test> x == 1"], [2])
    ir.blocks["yes"] = BasicBlock("yes", "app.py", "app", "f", 3, 3)
    ir.blocks["no"] = BasicBlock("no", "app.py", "app", "f", 4, 4)
    ir.add_edge(FlowEdge("branch", "yes", "true"))
    ir.add_edge(FlowEdge("branch", "no", "false"))
    item = extract_predicate(ir, "branch")
    assert isinstance(item, UnsupportedPredicate)
    assert item.reason == "source_mismatch"


def test_example_target_maps_deviation_to_predicate_outcome():
    ir = build_example_ir()
    target_id = target_block_id(ir)
    branch_id = _branch_for(ir, "data[0] == 65")
    session = TraceSession(Path(__file__).resolve().parents[1] / "examples")
    with session.trace_execution():
        with session.request() as rid:
            CallableAdapter(target).execute(b"ZZZ")
    mapped = map_trace(session.drain_request_events(rid), ir)
    distances = target_distances(ir, {target_id})
    points = find_deviation_points(ir, target_id, mapped, distances)
    point = next(point for point in points if point.block_id == branch_id)
    extraction = extract_predicates(ir, [branch_id])
    predicate = extraction.get(branch_id)
    assert isinstance(predicate, PredicateInfo)
    assert predicate.expression == "data[0] == 65"
    assert predicate.true_successor == point.desired_successor
    assert predicate.outcome_for(point.desired_successor) is True
    assert predicate.outcome_for(point.observed_successor) is False


def test_left_hand_literal_is_recorded(tmp_path: Path):
    path = tmp_path / "left.py"
    path.write_text(
        "def target(x, data):\n"
        "    if 1 == x:\n"
        "        return\n"
        "    if b'MAGC' == data[:4]:\n"
        "        return\n",
        encoding="utf-8")
    ir = build_icfg(tmp_path)
    extraction = extract_predicates(ir)
    first = extraction.get(_branch_for(ir, "1 == x"))
    assert first.literal == "1"
    assert first.literal_side == "left"
    second = extraction.get(_branch_for(ir, "b'MAGC' == data[:4]"))
    assert second.literal == "b'MAGC'"
    assert second.literal_side == "left"
