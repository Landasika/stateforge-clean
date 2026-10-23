
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from stateforge.core.ir import ProgramIR
from stateforge.runtime.tracer import TraceEvent


@dataclass
class MappedTrace:
    blocks: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    block_hits: Counter = field(default_factory=Counter)
    edge_hits: Counter = field(default_factory=Counter)
    edge_kinds: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    unresolved: list[TraceEvent] = field(default_factory=list)
    block_requests: dict[str, set[int]] = field(default_factory=dict)
    edge_requests: dict[tuple[str, str], set[int]] = field(default_factory=dict)
    observed_valid_edges: list[tuple[str, str]] = field(default_factory=list)
    unmatched_transitions: list[tuple[str, str]] = field(default_factory=list)


def _normalize_qualname(name: str) -> str:
    return name.replace(".<locals>.", ".")


def map_trace(events: list[TraceEvent], ir: ProgramIR) -> MappedTrace:
    by_func: dict[tuple[str, str], list[str]] = {}
    function_by_loc: dict[tuple[str, str], object | None] = {}
    short_functions: dict[tuple[str, str], object | None] = {}
    for function in ir.functions.values():
        qualname = _normalize_qualname(
            function.qualname or function.name.rsplit(".", 1)[-1])
        function_by_loc[(function.file, qualname)] = function
        short = qualname.rsplit(".", 1)[-1]
        key = (function.file, short)
        if key not in short_functions:
            short_functions[key] = function
        elif short_functions[key] is not function:
            short_functions[key] = None
    for key, function in short_functions.items():
        function_by_loc.setdefault(key, function)
    for bid, block in ir.blocks.items():
        by_func.setdefault((block.file, _normalize_qualname(block.function)),
                           []).append(bid)
    valid_pairs = {(edge.src, edge.dst) for edge in ir.edges}
    out = MappedTrace()
    previous: str | None = None
    previous_request: int | None = None

    cs_chain: dict[tuple[str, str, int, str], list[str]] = {}
    rs_for_cs: dict[str, str] = {}
    for edge in ir.edges:
        src_block = ir.blocks.get(edge.src)
        if edge.kind == "call" and src_block is not None and src_block.kind == "callsite":
            key = (src_block.file, src_block.function,
                   edge.callsite_line or src_block.start_line, edge.dst)
            cs_chain.setdefault(key, []).append(edge.src)
        if edge.kind == "return" and edge.callsite_line is not None and edge.callee:
            callsite_id = edge.dst.replace("::returnsite::", "::callsite::", 1)
            cs = (callsite_id if callsite_id in ir.blocks
                  else next((e.src for e in ir.edges
                             if e.kind == "call" and e.callee == edge.callee
                             and e.callsite_line == edge.callsite_line), None))
            if cs is not None:
                rs_for_cs[cs] = edge.dst

    call_stack: list[tuple[str | None, tuple[str, str, int] | None]] = []
    chain_hits: dict[tuple[str, str, int, str], int] = {}
    last_line: tuple[str, str, int] | None = None
    valid_seen: set[tuple[str, str]] = set()
    unmatched_seen: set[tuple[str, str]] = set()

    def append_block(hit: str) -> None:
        nonlocal previous
        rid_now = previous_request if previous_request is not None else -1
        out.block_requests.setdefault(hit, set()).add(rid_now)
        if out.blocks and out.blocks[-1] == hit:
            return
        out.blocks.append(hit)
        out.block_hits[hit] += 1
        if previous is not None:
            pair = (previous, hit)
            out.edges.append(pair)
            out.edge_hits[pair] += 1
            out.edge_requests.setdefault(pair, set()).add(rid_now)
            if pair in valid_pairs:
                if pair not in valid_seen:
                    valid_seen.add(pair)
                    out.observed_valid_edges.append(pair)
                kinds = {edge.kind for edge in ir.edges
                         if edge.src == previous and edge.dst == hit}
                if kinds:
                    out.edge_kinds.setdefault(pair, set()).update(kinds)
            elif pair not in unmatched_seen:
                unmatched_seen.add(pair)
                out.unmatched_transitions.append(pair)
        previous = hit

    for event in events:
        if previous_request is not None and event.request_id != previous_request:
            previous = None
            call_stack = []
            chain_hits = {}
            last_line = None
        previous_request = event.request_id
        filename = event.file
        event_key = _normalize_qualname(event.qualname or event.function)
        function = function_by_loc.get((filename, event_key))
        if function is None:
            function = function_by_loc.get((filename, event.function))
        if event.event_type == "call" and function is not None:
            cs = None
            caller_last_line = last_line
            if last_line is not None:
                key = (last_line[0], last_line[1], last_line[2], function.entry)
                chain = cs_chain.get(key, [])
                idx = chain_hits.get(key, 0)
                if idx < len(chain):
                    chain_hits[key] = idx + 1
                    cs = chain[idx]
            if cs is not None:
                append_block(cs)
            append_block(function.entry)
            call_stack.append((cs, caller_last_line))
            last_line = None
            continue
        if event.event_type == "return" and function is not None:
            append_block(function.exit)
            if call_stack:
                cs, caller_last_line = call_stack.pop()
                if cs is not None:
                    rs = rs_for_cs.get(cs)
                    if rs is not None:
                        append_block(rs)
                last_line = caller_last_line
            else:
                last_line = None
            continue
        candidates = by_func.get((filename, event_key), [])
        if not candidates:
            candidates = by_func.get((filename, event.function), [])
        if not candidates:
            candidates = [bid for bid, block in ir.blocks.items()
                          if block.file == filename
                          and _normalize_qualname(block.function) == event_key]
        exact = [bid for bid in candidates
                 if event.line in ir.blocks[bid].line_numbers]
        real = [bid for bid in exact
                if ir.blocks[bid].kind not in ("callsite", "returnsite")]
        pool = real or exact
        if len(pool) == 1:
            hit = pool[0]
        else:
            hit = next((bid for bid in pool
                        if ir.blocks[bid].start_line <= event.line <= ir.blocks[bid].end_line),
                       None)
            if hit is None:
                hit = next((bid for bid in candidates
                            if ir.blocks[bid].start_line <= event.line <= ir.blocks[bid].end_line),
                           None)
        if hit is None:
            out.unresolved.append(event)
            continue
        last_line = (filename, event_key, event.line)
        append_block(hit)
    return out
