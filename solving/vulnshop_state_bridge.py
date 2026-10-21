from __future__ import annotations
import ast
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import networkx as nx
from stateforge.analysis.analyzer import derive_invariants
from stateforge.analysis.builder import build_sstg
from stateforge.analysis.flask_adapter import extract_flask
from stateforge.core.ir import ProgramIR
from stateforge.core.model import (AppModel, Effect, PlanStep,
                                   Precondition)
from stateforge.state.planning.backward import plan_backward
from stateforge.state.planning.binding import BindingContext
from stateforge.state.planning.goals import GoalSpec, register_step
_AUTH_VAR = "Session.authed_as"
_PUBLIC_ROUTES = ("/auth/register", "/auth/login", "/")
_MUTATING = ("POST", "PUT")
_SQL_EXECUTE = ("execute", "executemany", "executescript")
@dataclass(frozen=True)
class AppModelPath:
    target: Path                                  
    app_root: Path                                
    model: AppModel
    sstg: nx.MultiDiGraph
    atoms: dict[str, frozenset[tuple[str, int]]]  
def _success_return_line(model: AppModel, app_root: Path, ep) -> int:
    src = _abs_source(ep.file, app_root)
    funcs = _functions_by_file(model, app_root)
    fn = funcs.get(str(src), {}).get(ep.func) if src is not None else None
    if fn is None:
        return ep.line
    returns = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Return)]
    return max(returns) if returns else ep.line
def _complete_auth_chain(model: AppModel, app_root: Path) -> None:
    
    entities = {p.var.split(".", 1)[0] for ep in model.endpoints
                for p in ep.preconditions if "." in p.var}
    entities |= {e.var.split(".", 1)[0] for ep in model.endpoints
                 for e in ep.effects if "." in e.var}
    entities.discard("Session")

    def _public(ep) -> bool:
        return ep.route in _PUBLIC_ROUTES or ep.route.startswith("/auth/")

    for ep in model.endpoints:
        if _public(ep):
            continue
        touches = any(p.var.split(".", 1)[0] in entities
                      for p in ep.preconditions) or \
            any(e.var.split(".", 1)[0] in entities for e in ep.effects)
        if touches and not any(p.var == _AUTH_VAR for p in ep.preconditions):
            ep.preconditions.append(Precondition(
                var=_AUTH_VAR, op="truthy", file=ep.file, line=ep.line))
    for ep in model.endpoints:
        if ep.route.endswith("/auth/login") and \
                not any(e.var == _AUTH_VAR for e in ep.effects):
            ep.effects.append(Effect(
                var=_AUTH_VAR, op="set", key="username",
                file=ep.file,
                line=_success_return_line(model, app_root, ep)))


def _abs_source(file: str, app_root: Path) -> Path | None:
    p = Path(file)
    if not p.is_absolute():
        p = app_root / p
    try:
        return p.resolve()
    except OSError:
        return None

def _functions_by_file(model: AppModel, app_root: Path
                       ) -> dict[str, dict[str, ast.FunctionDef]]:
    
    out: dict[str, dict[str, ast.FunctionDef]] = {}
    for ep in model.endpoints:
        src = _abs_source(ep.file, app_root)
        if src is None or str(src) in out:
            continue
        try:
            tree = ast.parse(src.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            out[str(src)] = {}
            continue
        funcs = {n.name: n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        out[str(src)] = funcs
    return out

def _target_text(node) -> str:
    words: list[str] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            words.append(n.id)
        elif isinstance(n, ast.Attribute):
            words.append(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            words.append(n.value)
    return " ".join(words)


def _write_sites(fn: ast.FunctionDef, attr: str, value: str):
    
    word = re.compile(rf"\b{re.escape(attr)}\b")
    lhs = re.compile(rf"\b{re.escape(attr)}\s*=")
    rhs = re.compile(
        rf"\b{re.escape(attr)}\s*=\s*['\"]?{re.escape(value)}\b")
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and node.targets:
            if not word.search(_target_text(node.targets[0])):
                continue
            const = node.value
            is_value = isinstance(const, ast.Constant) \
                and isinstance(const.value, str) and const.value == value
            yield node.lineno, ("value" if is_value else "attr")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in _SQL_EXECUTE:
            hit = None
            for c in ast.walk(node):
                if not (isinstance(c, ast.Constant) and isinstance(c.value, str)):
                    continue
                if rhs.search(c.value):
                    hit = "value"
                    break
                if lhs.search(c.value):
                    hit = "attr"
            if hit is not None:
                yield node.lineno, hit


def _anchors(model: AppModel, app_root: Path, sstg: nx.MultiDiGraph
             ) -> dict[str, frozenset[tuple[str, int]]]:
    
    funcs = _functions_by_file(model, app_root)
    out: dict[str, frozenset[tuple[str, int]]] = {}
    requires = {v for _, v, d in sstg.edges(data=True) if d.get("kind") == "requires"}
    for atom in requires:
        var, _, value = atom.partition("=")
        _entity, _, attr = var.partition(".")
        matched: set[tuple[str, int]] = set()
        blind: set[tuple[str, int]] = set()
        for ep in model.endpoints:
            src = _abs_source(ep.file, app_root)
            fn = funcs.get(str(src), {}).get(ep.func) if src else None
            if ep.methods and ep.methods[0] not in _MUTATING:
                fn = None                      
            if fn is not None:
                for line, kind in _write_sites(fn, attr, value):
                    (matched if kind == "value" else blind).add((str(src), line))
            if not value:
                continue
            for eff in ep.effects:             
                
                auth_sentinel = var == _AUTH_VAR and eff.value is None
                if eff.var == var and eff.line and \
                        (eff.value == value or auth_sentinel):
                    src2 = _abs_source(eff.file, app_root)
                    if src2 is not None:
                        matched.add((str(src2), eff.line))
        out[atom] = frozenset(matched or blind)
    return out


@lru_cache(maxsize=None)
def _appmodel_path(resolved_target: str) -> AppModelPath | None:
    target = Path(resolved_target)
    if not target.is_file():
        return None
    app_root = target.parent
    try:
        model = extract_flask(app_root)
        if not model.endpoints:
            return None              
        _complete_auth_chain(model, app_root)
        model.invariants = derive_invariants(model)
        sstg = build_sstg(model)
        return AppModelPath(target=target, app_root=app_root, model=model,
                            sstg=sstg, atoms=_anchors(model, app_root, sstg))
    except Exception:                                      
        return None                  


def appmodel_path(target) -> AppModelPath | None:
    
    return _appmodel_path(str(Path(target).resolve()))



appmodel_path.cache_clear = _appmodel_path.cache_clear
appmodel_path.cache_info = _appmodel_path.cache_info





def _coerce_ir(ir) -> ProgramIR | None:
    if ir is None or isinstance(ir, ProgramIR):
        return ir
    try:
        return ProgramIR.from_json(ir)
    except (OSError, ValueError):
        return None


def _covered_lines_by_file(ir: ProgramIR, state: dict, app_root: Path
                           ) -> dict[str, set[int]]:
    
    covered = set(state.get("covered_blocks") or state.get("blocks") or [])
    root = app_root.resolve()
    out: dict[str, set[int]] = {}
    for bid in covered:
        block = ir.blocks.get(bid)
        if block is None:
            continue
        try:
            f = Path(block.file)
            f = f if f.is_absolute() else root / f
            f = f.resolve()
        except OSError:
            continue
        if not (f == root or root in f.parents):
            continue
        out.setdefault(str(f), set()).update(
            block.line_numbers or range(block.start_line, block.end_line + 1))
    return out


def reached_atoms(ir, state: dict, amp: AppModelPath) -> set[str]:
    
    ir_obj = _coerce_ir(ir)
    if ir_obj is None:
        return set()
    lines = _covered_lines_by_file(ir_obj, state or {}, amp.app_root)
    return {atom for atom, anchors in amp.atoms.items()
            if any(line in lines.get(file, ()) for file, line in anchors)}





def _complete_plan(model: AppModel, steps: list[PlanStep]) -> list[PlanStep]:
    steps = list(steps)
    if steps and any(s.action.endswith("/auth/login") for s in steps) and \
            not any(s.action.endswith("/auth/register") for s in steps):
        steps = [register_step()] + steps
    ep_by_action = {f"{ep.methods[0]} {ep.route}": ep for ep in model.endpoints}
    def _observes(step: PlanStep) -> list[str]:
        ep = ep_by_action.get(step.action)
        return ep.observes if ep is not None else []

    bound = {slot.lstrip("?") for s in steps for slot in s.extract.values()}
    used = sorted({v[1:] for s in steps for v in s.path.values()
                   if isinstance(v, str) and v.startswith("?")} - bound)
    for slot in used:
        key = slot if any(slot in _observes(s) for s in steps) else "id"
        for s in steps:
            if key in _observes(s) and f"?{slot}" not in s.extract.values():
                s.extract[key] = f"?{slot}"
                break
    return steps


def _symbolic(ctx: BindingContext, v):
    if isinstance(v, str) and v.startswith("@"):
        return ctx.render(v)
    return v


def _render_step(ctx: BindingContext, st: PlanStep) -> dict:
    method, _, route = st.action.partition(" ")
    path = route
    for name, v in st.path.items():
        val = str(_symbolic(ctx, v))
        path = path.replace(f"<int:{name}>", val).replace(f"<{name}>", val)
    step = {"method": method or "GET", "path": path}
    if st.json:
        step["json"] = {k: _symbolic(ctx, v) for k, v in st.json.items()}
    if st.headers:
        step["header"] = {k: _symbolic(ctx, v) for k, v in st.headers.items()}
    if st.extract:
        step["extract"] = dict(st.extract)
    return step


def render_seed(amp: AppModelPath, atom: str, salt: str) -> list[dict]:
    
    goal = GoalSpec(name=f"reach_{atom}", vuln_class="state_reach",
                    kind="reach_state", target=atom)
    segment = plan_backward(amp.model, amp.sstg, goal)
    steps = _complete_plan(amp.model, segment.steps)
    ctx = BindingContext(salt=salt)
    return [_render_step(ctx, st) for st in steps]
