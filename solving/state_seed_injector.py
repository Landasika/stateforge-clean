from __future__ import annotations
import ast
import hashlib
import json
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
import networkx as nx
from stateforge.analysis.builder import build_sstg
from stateforge.core.ir import ProgramIR
from stateforge.core.model import (AppModel, Effect, Endpoint, Param,
                                   PlanStep, Precondition)
from stateforge.fuzzing.corpus_manager import CorpusManager
from stateforge.fuzzing.entry_driver import encode_sequence_seed
from stateforge.solving.vulnshop_state_bridge import (
    AppModelPath, appmodel_path, reached_atoms, render_seed)
from stateforge.state.observer import run_state_analysis
from stateforge.state.planning.backward import plan_backward
from stateforge.state.planning.binding import BindingContext
from stateforge.state.planning.goals import GoalSpec
STATE_BUDGET = 3        
NEUTRAL = "x"           
_MUTATIONS = frozenset({"set", "update"})
_SCHEMA_KEYS = frozenset({"op", "json", "query", "form", "header", "cookie"})
_GUARD_TO_PRE = {
    "EQ": ("eq", True), "NE": ("ne", True), "IN": ("in", True),
    "TRUTHY": ("truthy", False), "IS_NOT_NONE": ("truthy", False),
    "FALSY": ("falsy", False), "IS_NONE": ("falsy", False),
}
@dataclass(frozen=True)
class GuardInfo:
    var: str                      
    pre_op: str                   
    value: str | None
    line: int                     
    body_lines: frozenset[int]    
    op: str                       
    atom: str | None = None       
@dataclass
class OpInfo:
    name: str
    params: list[str] = field(default_factory=list)          
    writes: dict[str, str | None] = field(default_factory=dict)  
    func: str = "target"


@dataclass
class WriteInfo:
    op: str
    key: str                     
    feed: str | None             
    line: int


@dataclass
class MicroStateModel:
    

    target: Path
    ops: dict[str, OpInfo]
    guards: list[GuardInfo]
    model: AppModel
    sstg: nx.MultiDiGraph



def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _stmt_lines(stmts) -> set[int]:
    out: set[int] = set()
    for s in stmts:
        out.update(range(s.lineno, s.end_lineno + 1))
    return out


def _dispatch_var(tree) -> str | None:
    
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                and value.func.id == "str" and value.args:
            value = value.args[0]
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if not names:
            continue
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) \
                and value.func.attr == "get" and value.args \
                and isinstance(value.args[0], ast.Constant) \
                and value.args[0].value == "op":
            return names[0]
        if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant) \
                and value.slice.value == "op":
            return names[0]
    return None


def _op_branches(tree, dispatch: str) -> dict[str, set[int]]:
    
    out: dict[str, set[int]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)):
            continue
        test = node.test
        if not (isinstance(test.left, ast.Name) and test.left.id == dispatch
                and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
                and isinstance(test.comparators[0], ast.Constant)
                and isinstance(test.comparators[0].value, str)):
            continue
        out.setdefault(test.comparators[0].value, set()).update(
            {node.lineno} | _stmt_lines(node.body))
    return out


def _body_var(tree) -> str | None:
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                and isinstance(node.value.func, ast.Attribute) \
                and node.value.func.attr == "get" and node.value.args \
                and isinstance(node.value.args[0], ast.Constant) \
                and node.value.args[0].value == "json":
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if names:
                return names[0]
    return None


def _owner(line: int, branches: dict[str, set[int]]) -> str | None:
    
    for op in sorted(branches, key=lambda o: (len(branches[o]), o)):
        if line in branches[op]:
            return op
    return None

def _op_params(tree, branches, body_var) -> dict[str, set[str]]:
    
    out: dict[str, set[str]] = {op: set() for op in branches}
    if body_var is None:
        return out
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if line is None:
            continue
        keys: list[str] = []
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == body_var and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            keys.append(node.args[0].value)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                and isinstance(node.value, ast.Name) and node.value.id == body_var \
                and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            keys.append(node.slice.value)
        if not keys:
            continue
        op = _owner(line, branches)
        if op is None:
            continue
        for k in keys:
            if k not in _SCHEMA_KEYS:
                out[op].add(k)
    return out


def _session_writes(tree, branches, params) -> list[WriteInfo]:
    
    out: list[WriteInfo] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and node.targets
                and isinstance(node.targets[0], ast.Subscript)
                and isinstance(node.targets[0].value, ast.Name)
                and node.targets[0].value.id == "session"
                and isinstance(node.targets[0].slice, ast.Constant)):
            continue
        key = str(node.targets[0].slice.value)
        op = _owner(node.lineno, branches)
        if op is None:
            continue                       
        feed = _feed_param(node.value, params[op])
        out.append(WriteInfo(op=op, key=key, feed=feed, line=node.lineno))
    return out


def _feed_param(rhs, branch_params: set[str]) -> str | None:
    
    if isinstance(rhs, ast.Name):
        return rhs.id if rhs.id in branch_params else None
    if isinstance(rhs, ast.Call) and isinstance(rhs.func, ast.Attribute) \
            and rhs.func.attr == "get" and rhs.args \
            and isinstance(rhs.args[0], ast.Constant) \
            and isinstance(rhs.args[0].value, str):
        k = rhs.args[0].value
        return k if k in branch_params else None
    return None


def _if_bodies(tree) -> dict[int, frozenset[int]]:
    
    out: dict[int, frozenset[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While)):
            out.setdefault(node.lineno, frozenset(_stmt_lines(node.body)))
    return out





def _target_candidates(path: Path) -> list[dict]:
    
    try:
        analysis = run_state_analysis(path.parent)
    except Exception:                                  
        return []
    out = []
    for cand in analysis.get("transitions", {}).get("static_candidates", []):
        evidence = (cand.get("evidence") or [""])[0]
        file_part = evidence.rsplit(":", 1)[0]
        try:
            same = Path(file_part).resolve() == path.resolve()
        except OSError:
            same = False
        if same:
            out.append(cand)
    return out


def _parse_guard_op(raw: str) -> tuple[str, str | None] | None:
    
    body = raw.removeprefix("guard:")
    if not body:
        return None
    if "(" in body and body.endswith(")"):
        kind, _, rest = body.partition("(")
        return kind, rest[:-1]
    return body, None




@lru_cache(maxsize=None)
def _synthesized_model(resolved_target: str) -> MicroStateModel | None:
    path = Path(resolved_target)
    if not path.is_file():
        return None
    tree = _parse(path)
    if tree is None:
        return None
    dispatch = _dispatch_var(tree)
    if dispatch is None:
        return None
    branches = _op_branches(tree, dispatch)
    if not branches:
        return None
    params = _op_params(tree, branches, _body_var(tree))
    writes = _session_writes(tree, branches, params)
    if_bodies = _if_bodies(tree)

    ops: dict[str, OpInfo] = {}
    guards: list[GuardInfo] = []
    write_map: dict[tuple[str, str], WriteInfo] = {}
    for w in writes:
        write_map[(w.op, w.key)] = w
        ops.setdefault(w.op, OpInfo(name=w.op))
    for cand in _target_candidates(path):
        line = int((cand.get("evidence") or ["0:0"])[0].rsplit(":", 1)[1])
        op = _owner(line, branches)
        if op is None:
            continue
        entry = ops.setdefault(op, OpInfo(name=op, func=cand.get("function") or "target"))
        if cand["op"] in _MUTATIONS:                       
            key = cand["var"].split(".", 1)[-1]
            w = write_map.get((op, key))
            entry.writes[key] = w.feed if w is not None else None
        else:                                              
            parsed = _parse_guard_op(cand["op"])
            if parsed is None:
                continue
            kind, value = parsed
            pre = _GUARD_TO_PRE.get(kind)
            if pre is None:
                continue
            pre_op, has_val = pre
            guards.append(GuardInfo(
                var=f"Session.{cand['var'].split('.', 1)[-1]}",
                pre_op=pre_op, value=value if has_val else None,
                line=line, body_lines=if_bodies.get(line, frozenset()), op=op))
    for op, keys in params.items():
        ops.setdefault(op, OpInfo(name=op)).params = sorted(keys)

    guard_values: dict[str, list[str]] = {}                
    for g in guards:
        part = g.value if g.pre_op in ("eq", "ne", "in") else (
            "True" if g.pre_op == "truthy" else "False")
        if part:
            guard_values.setdefault(g.var.split(".", 1)[-1], []).append(part)

    endpoints = []
    for op in sorted(ops):
        entry = ops[op]
        pres = [Precondition(var=g.var, op=g.pre_op, value=g.value,
                             file=path.name, line=g.line)
                for g in sorted((g for g in guards if g.op == op),
                                key=lambda g: g.line)]
        effs = []
        for key in sorted(entry.writes):
            values = sorted(set(guard_values.get(key, [])))
            line = write_map.get((op, key), WriteInfo(op, key, None, 0)).line
            for v in values or [None]:                     
                effs.append(Effect(var=f"Session.{key}", op="set", value=v,
                                   file=path.name, line=line))
        endpoints.append(Endpoint(
            func=entry.func, route=op, methods=["POST"],
            params=[Param(name=p, location="json") for p in entry.params],
            preconditions=pres, effects=effs,
            observes=sorted(set(entry.writes) |
                            {g.var.split(".", 1)[-1] for g in guards if g.op == op})))

    model = AppModel(app_root=str(path.parent), framework="flask",
                     endpoints=endpoints)
    sstg = build_sstg(model)
    micro = MicroStateModel(target=path, ops=ops, guards=[], model=model,
                            sstg=sstg)
    for g in guards:                                       
        part = g.value if g.pre_op in ("eq", "ne", "in") else (
            "True" if g.pre_op == "truthy" else "False")
        micro.guards.append(replace(g, atom=_requires_atom(
            sstg, f"POST {g.op}", g.var, part)))
    return micro


def synthesize_micro_model(target) -> MicroStateModel | None:
    
    return _synthesized_model(str(Path(target).resolve()))


synthesize_micro_model.cache_clear = _synthesized_model.cache_clear
synthesize_micro_model.cache_info = _synthesized_model.cache_info

def _requires_atom(sstg: nx.MultiDiGraph, action: str, var: str,
                   value_part: str | None) -> str | None:
    
    if value_part is None:
        return None
    for _, v, d in sstg.out_edges(action, data=True):
        if d.get("kind") != "requires":
            continue
        attrs = sstg.nodes[v]
        if attrs.get("var") == var and attrs.get("value") == value_part:
            return v
    return None




def goal_atoms(sstg: nx.MultiDiGraph) -> set[str]:
    
    return {v for _, v, d in sstg.edges(data=True) if d.get("kind") == "requires"}


def _coerce_ir(ir) -> ProgramIR | None:
    if ir is None or isinstance(ir, ProgramIR):
        return ir
    try:
        return ProgramIR.from_json(ir)
    except (OSError, ValueError):
        return None


def _covered_lines(ir: ProgramIR, target: Path, state: dict) -> set[int]:
    
    covered = set(state.get("covered_blocks") or state.get("blocks") or [])
    lines: set[int] = set()
    for bid in covered:
        block = ir.blocks.get(bid)
        if block is None:
            continue
        try:
            if Path(block.file).resolve() != target.resolve():
                continue
        except OSError:
            continue
        lines.update(block.line_numbers or
                     range(block.start_line, block.end_line + 1))
    return lines

def reached_state_atoms(ir, target, state: dict) -> set[str]:
    
    amp = appmodel_path(target)
    if amp is not None:
        return reached_atoms(ir, state, amp)
    micro = synthesize_micro_model(target)
    ir_obj = _coerce_ir(ir)
    if micro is None or ir_obj is None:
        return set()
    lines = _covered_lines(ir_obj, micro.target, state or {})
    return {g.atom for g in micro.guards
            if g.atom and lines & g.body_lines}


def _goal_units(micro: MicroStateModel, reached: set[str]) -> list[tuple[str, str]]:
    out = []
    for op in sorted(micro.ops):
        unreached = sorted({g.atom for g in micro.guards
                            if g.op == op and g.atom and g.atom not in reached})
        if unreached:
            out.append((op, unreached[0]))
    return out


def _overrides(micro: MicroStateModel, atom: str) -> dict[str, str]:
    
    var, _, value_part = atom.partition("=")
    key = var.partition(".")[2]
    guard = next((g for g in micro.guards if g.atom == atom), None)
    bind = value_part if guard is not None and guard.pre_op == "eq" else NEUTRAL
    out: dict[str, str] = {}
    for op in sorted(micro.ops):
        feed = micro.ops[op].writes.get(key)
        if feed:
            out.setdefault(feed, bind)
    return out

def _plan_requests(micro: MicroStateModel, op: str) -> list[dict]:
    
    action = f"POST {op}"
    req_atoms = sorted({v for _, v, d in micro.sstg.out_edges(action, data=True)
                        if d.get("kind") == "requires"})
    steps: list[PlanStep] = []
    seen: set[str] = set()
    for atom in req_atoms:                       
        goal = GoalSpec(name=f"reach_{atom}", vuln_class="state_reach",
                        kind="reach_state", target=atom,
                        param_overrides=_overrides(micro, atom))
        for st in plan_backward(micro.model, micro.sstg, goal).steps:
            if st.action not in seen:
                seen.add(st.action)
                steps.append(st)
    if action not in seen:                       
        steps.append(PlanStep(action=action,
                              json={p: NEUTRAL for p in micro.ops[op].params}))
    ctx = BindingContext(salt=hashlib.sha256(
        str(micro.target.resolve()).encode("utf-8")).hexdigest()[:8])
    requests = []
    for st in steps:
        route, json_body, headers = ctx.render_step(st)
        request = {"json": {"op": route, **json_body}}
        if headers:
            request["header"] = headers
        requests.append(request)
    return requests



def _audit(audit_path: Path, record: dict) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _appmodel_goals(amp: AppModelPath, reached: set[str]) -> list[str]:
    
    return sorted(set(amp.atoms) - reached)


def _inject_appmodel(ir, amp: AppModelPath, state: dict, corpus_dir,
                     budget: int) -> int:
    
    if budget <= 0:
        return 0
    reached = reached_atoms(ir, state, amp)        
    goals = _appmodel_goals(amp, reached)

    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    spool = CorpusManager(corpus_dir.parent / "state_spool")
    audit_path = corpus_dir.parent / "epochs" / "state_injections.jsonl"
    salt = hashlib.sha256(
        str(amp.target.resolve()).encode("utf-8")).hexdigest()[:8]

    written = 0
    for atom in goals:
        if written >= budget:
            break
        record = {"goal": atom, "path": "appmodel"}
        try:
            steps = render_seed(amp, atom, salt)
        except Exception as exc:                          
            _audit(audit_path, {**record,
                                "status": f"PLAN_ERROR_{type(exc).__name__}"})
            continue
        record["steps"] = [f"{s.get('method', 'GET')} {s.get('path', '')}"
                           for s in steps]
        if not steps:                              
            _audit(audit_path, {**record, "status": "NO_PLAN"})
            continue
        data = encode_sequence_seed(steps)
        cid = spool.save(data, epoch=0, new_blocks=0, new_edges=0,
                         discovered_blocks=0, discovered_edges=0,
                         interesting_reason="state_plan", origin="STATE")
        if cid:
            (corpus_dir / cid).write_bytes(data)
            written += 1
            _audit(audit_path, {**record, "status": "INJECTED", "seed_id": cid})
        else:
            _audit(audit_path, {**record, "status": "DUPLICATE"})
    return written


def inject_state_seeds(ir, target, state: dict, corpus_dir,
                       budget: int = STATE_BUDGET) -> int:
    
    amp = appmodel_path(target)
    if amp is not None:
        return _inject_appmodel(ir, amp, state, corpus_dir, budget)
    micro = synthesize_micro_model(target)
    if micro is None or budget <= 0:
        return 0
    reached = reached_state_atoms(ir, target, state)
    goals = _goal_units(micro, reached)

    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    spool = CorpusManager(corpus_dir.parent / "state_spool")
    audit_path = corpus_dir.parent / "epochs" / "state_injections.jsonl"

    written = 0
    for op, atom in goals[:budget]:
        try:
            requests = _plan_requests(micro, op)
        except Exception as exc:                          
            _audit(audit_path, {"goal": atom, "op": op,
                                "status": f"PLAN_ERROR_{type(exc).__name__}"})
            continue
        data = encode_sequence_seed(requests)
        cid = spool.save(data, epoch=0, new_blocks=0, new_edges=0,
                         discovered_blocks=0, discovered_edges=0,
                         interesting_reason="state_plan", origin="STATE")
        record = {"goal": atom, "op": op,
                  "steps": [r.get("json", {}).get("op") for r in requests]}
        if cid:
            (corpus_dir / cid).write_bytes(data)
            written += 1
            record.update(status="INJECTED", seed_id=cid)
        else:
            record.update(status="DUPLICATE")
        _audit(audit_path, record)
    return written
