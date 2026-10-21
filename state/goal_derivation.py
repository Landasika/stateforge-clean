from __future__ import annotations
import ast
from dataclasses import dataclass, field
from pathlib import Path
from stateforge.core.ir import ProgramIR
from stateforge.state.model import StateFactCandidate, StructuredPredicate
@dataclass(frozen=True)
class StateGoal:
    

    target_block: str
    function: str
    file: str
    constraints: tuple[StructuredPredicate, ...]
    guard_blocks: tuple[str, ...] = field(default=())
    evidence: tuple[str, ...] = field(default=())
    relations: tuple = field(default=())            
    entity_vars: tuple[str, ...] = field(default=())
    var_provenance: tuple = field(default=())       
    path_conditions: tuple = field(default=())      
    unresolvable: tuple = field(default=())         
    def to_dict(self) -> dict:
        return {
            "target_block": self.target_block,
            "function": self.function,
            "file": self.file,
            "constraints": [p.to_dict() for p in self.constraints],
            "guard_blocks": list(self.guard_blocks),
            "evidence": list(self.evidence),
            "relations": [r.to_dict() for r in self.relations],
            "entity_vars": list(self.entity_vars),
            "var_provenance": [p.to_dict() for p in self.var_provenance],
            "path_conditions": [p.to_dict() for p in self.path_conditions],
            "unresolvable": [u.to_dict() for u in self.unresolvable],
        }
def _function_blocks(ir: ProgramIR, block_id: str) -> set[str]:
    
    blk = ir.blocks.get(block_id)
    if blk is None:
        return set()
    return {b.id for b in ir.blocks.values()
            if b.file == blk.file and b.function == blk.function}


def _all_paths_raise(stmts) -> bool:
    
    for s in stmts:
        if _stmt_all_paths_raise(s):
            return True
    return False


def _stmt_all_paths_raise(s) -> bool:
    if isinstance(s, ast.Raise):
        return True
    if isinstance(s, ast.If):
        return (_all_paths_raise(s.body)
                and bool(s.orelse) and _all_paths_raise(s.orelse))
    return False


_RAISE_CACHE: dict[tuple[str, str], bool] = {}

def _callee_never_returns(ir: ProgramIR, callee_qname: str) -> bool:
    fnir = ir.functions.get(callee_qname)
    if fnir is None:
        return False
    eb = ir.blocks.get(fnir.entry)
    if eb is None:
        return False
    key = (eb.file, eb.function)
    if key not in _RAISE_CACHE:
        _RAISE_CACHE[key] = _fn_all_paths_raise(eb.file, eb.function)
    return _RAISE_CACHE[key]


def _fn_all_paths_raise(source_file: str, function: str) -> bool:
    try:
        tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == function), None)
    return fn is not None and _all_paths_raise(fn.body)
def _intra_adjacency(ir: ProgramIR, block_ids: set[str],
                     skip_edge: tuple[str, str] | None
                     ) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for e in ir.edges:
        if e.src not in block_ids or e.dst not in block_ids:
            continue
        if skip_edge and (e.src, e.dst) == skip_edge:
            continue
        adj.setdefault(e.src, []).append(e.dst)
    for e in ir.edges:
        if e.kind != "call" or e.src not in block_ids:
            continue
        rs = e.src.replace("::callsite::", "::returnsite::")
        if rs not in block_ids or rs in adj.get(e.src, ()):
            continue
        if e.callee and _callee_never_returns(ir, e.callee):
            continue                      
        adj.setdefault(e.src, []).append(rs)
    return adj


def _reachable(src: str, dst: str, block_ids: set[str], ir: ProgramIR,
               skip_edge: tuple[str, str] | None = None) -> bool:
    
    adj = _intra_adjacency(ir, block_ids, skip_edge)
    seen = {src}
    stack = [src]
    while stack:
        n = stack.pop()
        if n == dst:
            return True
        for m in adj.get(n, []):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return False
def _entry_of(ir: ProgramIR, block_ids: set[str]) -> str | None:
    has_in = {e.dst for e in ir.edges
              if e.src in block_ids and e.dst in block_ids}
    entries = [b for b in block_ids if b not in has_in]
    if not entries:
        return None
    return min(entries, key=lambda b: ir.blocks[b].start_line)


def necessary_guard_edges(ir: ProgramIR,
                          target_block: str) -> list[tuple[str, str]]:
    
    fblocks = _function_blocks(ir, target_block)
    entry = _entry_of(ir, fblocks)
    if entry is None or entry == target_block:
        return []
    
    
    if not _reachable(entry, target_block, fblocks, ir):
        return []
    out: list[tuple[str, str]] = []
    branch_blocks = [b for b in fblocks
                     if any(e.src == b and e.kind in ("true", "false")
                            for e in ir.edges)]
    for b in branch_blocks:
        for e in ir.edges:
            if e.src != b or e.kind not in ("true", "false"):
                continue
            if not _reachable(entry, target_block, fblocks, ir,
                              skip_edge=(e.src, e.dst)):
                if (b, e.kind) not in out:
                    out.append((b, e.kind))
                break
    return sorted(out, key=lambda t: ir.blocks[t[0]].start_line)


def necessary_guards(ir: ProgramIR, target_block: str) -> list[str]:
    
    return [b for b, _kind in necessary_guard_edges(ir, target_block)]

def _same_file(a: str, b: str) -> bool:
    
    from pathlib import Path

    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b

def _facts_in_block(facts: list[StateFactCandidate], file: str,
                    start: int, end: int) -> list[StateFactCandidate]:
    return [f for f in facts
            if _same_file(f.source_file, file) and start <= f.lineno <= end
            and f.relevance.value == "CONTROL"
            and f.structured_predicate is not None]


def derive_state_goal(ir: ProgramIR, facts: list[StateFactCandidate],
                      target_block: str) -> StateGoal | None:
    blk = ir.blocks.get(target_block)
    if blk is None:
        return None
    from stateforge.state.model import PredicateOp, StructuredPredicate

    _invert = {"EQ": PredicateOp.NE, "IN": PredicateOp.NOT_IN}
    guards = necessary_guard_edges(ir, target_block)
    constraints: list = []
    evidence: list[str] = []
    for g, edge_kind in guards:
        gblk = ir.blocks[g]
        for f in _facts_in_block(facts, gblk.file,
                                 gblk.start_line, gblk.end_line):
            pred = f.structured_predicate
            if edge_kind == "false" and pred.operator.value in _invert:
                pred = StructuredPredicate(
                    _invert[pred.operator.value], pred.subject, pred.value)
            if pred in constraints:
                continue                      
            constraints.append(pred)
            evidence.append(
                f"{f.source_file}:{f.lineno} {f.object_ref}"
                f" {pred.operator.value}"
                f"{'' if edge_kind == 'true' else '(false 边反转)'}")
    for f in _facts_in_block(facts, blk.file, blk.start_line, blk.end_line):
        if f.structured_predicate in constraints:
            continue
        constraints.append(f.structured_predicate)
        evidence.append(
            f"{f.source_file}:{f.lineno} {f.object_ref}"
            f" {f.structured_predicate.operator.value}")
    return StateGoal(
        target_block=target_block,
        function=blk.function,
        file=blk.file,
        constraints=tuple(constraints),
        guard_blocks=tuple(b for b, _kind in guards),
        evidence=tuple(evidence),
    )














def _all_terminate(stmts) -> bool:
    
    for s in stmts:
        if _stmt_all_terminate(s):
            return True
    return False

def _stmt_all_terminate(s) -> bool:
    if isinstance(s, (ast.Return, ast.Raise)):
        return True
    if isinstance(s, ast.If):
        return (_all_terminate(s.body)
                and bool(s.orelse) and _all_terminate(s.orelse))
    return False                                   


def _parent_map(fn: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(fn):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _inside_loop_or_try(node, parents: dict[int, ast.AST]) -> bool:
    cur = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, (ast.While, ast.For, ast.AsyncFor, ast.Try)):
            return True
        cur = parents.get(id(cur))
    return False
def _enclosing_ifs(node, fn: ast.AST,
                   parents: dict[int, ast.AST]) -> list[ast.If]:
    out: list[ast.If] = []
    cur = parents.get(id(node))
    while cur is not None and cur is not fn:
        if isinstance(cur, ast.If):
            out.append(cur)
        cur = parents.get(id(cur))
    return out
def _classify_ifs(fn: ast.AST) -> tuple[set[int], set[int]]:
    parents = _parent_map(fn)
    guards: set[int] = set()
    wrappers: set[int] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or node.orelse:
            continue
        if _inside_loop_or_try(node, parents):
            continue
        if _all_terminate(node.body):
            guards.add(id(node))
        else:
            wrappers.add(id(node))
    return guards, wrappers



_CMP_BASE = {"Eq": ("EQ", "NE"), "NotEq": ("NE", "EQ"),
             "In": ("IN", "NOT_IN"), "NotIn": ("NOT_IN", "IN")}
_CMP_NONE = {"Is": ("NOT_EXISTS", "EXISTS"),
             "IsNot": ("EXISTS", "NOT_EXISTS")}


def _compare_relation(term, op_name: str, invert: bool,
                      via_edge: str, src: str, line: int):
    
    from stateforge.state.relational import (Const, Field, RelPredicate,
                                              RelOp, UnresolvableItem)

    left, right = term.left, term.right
    if left is None or right is None:
        return None, UnresolvableItem(
            what=f"term:{term.raw}", cause="term-unparseable",
            source_file=src, source_line=line)
    if isinstance(left, Const) and isinstance(right, Const):
        return None, UnresolvableItem(
            what=f"term:{term.raw}", cause="const-only-compare",
            source_file=src, source_line=line)

    
    if op_name in _CMP_NONE:
        entity, other = (left, right) if isinstance(left, Field) \
            else (right, left)
        if not isinstance(entity, Field) \
                or not (isinstance(other, Const) and other.value is None) \
                or entity.name:
            return None, UnresolvableItem(
                what=f"term:{term.raw}", cause="unsupported-none-compare",
                source_file=src, source_line=line)
        base, inv = _CMP_NONE[op_name]
        return RelPredicate(
            op=RelOp(inv if invert else base), left=entity, right=None,
            origin_op=op_name, source_file=src, source_line=line,
            via_edge=via_edge), None

    if op_name not in _CMP_BASE:
        return None, UnresolvableItem(
            what=f"term:{term.raw}", cause=f"unsupported-op:{op_name}",
            source_file=src, source_line=line)
    base, inv = _CMP_BASE[op_name]
    
    if isinstance(left, Const) and isinstance(right, Field) \
            and op_name in ("Eq", "NotEq"):
        left, right = right, left
    return RelPredicate(
        op=RelOp(inv if invert else base), left=left, right=right,
        origin_op=op_name, source_file=src, source_line=line,
        via_edge=via_edge), None


def derive_relational_goal(ir, target_block: str) -> "StateGoal | None":
    
    import ast as _ast
    from pathlib import Path as _Path
    from stateforge.state.extractor import extract_guard_terms
    from stateforge.state.provenance import analyze_provenance
    from stateforge.state.relational import (Field, PathCondition, RelOp,
                                              RelPredicate, UnresolvableItem,
                                              VarProvenance)

    blk = ir.blocks.get(target_block)
    if blk is None:
        return None
    src_file = blk.file
    try:
        tree = _ast.parse(_Path(src_file).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None
    fn = next((n for n in _ast.walk(tree)
               if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
               and n.name == blk.function), None)
    if fn is None:
        return None

    target_line = blk.start_line
    prov = analyze_provenance(src_file)
    terms = {t.lineno: t for t in extract_guard_terms(fn, src_file)}
    parents = _parent_map(fn)
    guard_ids, wrapper_ids = _classify_ifs(fn)

    relations: list[RelPredicate] = []
    path_conds: dict[tuple, PathCondition] = {}
    unres: list[UnresolvableItem] = []

    for node in _ast.walk(fn):
        if not isinstance(node, _ast.If) or id(node) not in guard_ids:
            continue
        term = terms.get(node.lineno)
        if term is None:
            continue
        inside_body = node.lineno <= target_line <= node.end_lineno
        after = node.end_lineno < target_line
        if not (inside_body or after):
            continue                       
        invert = after                     
        via = "false" if after else "true"

        
        
        for w in _enclosing_ifs(node, fn, parents):
            w_on_path = (w.end_lineno < target_line
                         or w.lineno <= target_line <= w.end_lineno)
            if id(w) in wrapper_ids and w_on_path:
                wterm = terms.get(w.lineno)
                if wterm is not None and wterm.kind == "truthy" \
                        and isinstance(wterm.left, Field) \
                        and not wterm.left.name:
                    name = wterm.left.var.lstrip("?")
                    kind = prov.var_kind(blk.function, name)
                    key = (name, True, kind)
                    path_conds.setdefault(key, PathCondition(
                        var=name, requires=True, kind=kind,
                        source_file=src_file, source_line=w.lineno))
                else:
                    unres.append(UnresolvableItem(
                        what=f"wrapper:{terms[w.lineno].raw if w.lineno in terms else '?'}",
                        cause="wrapper-test-not-simple-name",
                        source_file=src_file, source_line=w.lineno))

        if term.kind == "compare" and term.op:
            rel, bad = _compare_relation(term, term.op, invert, via,
                                         src_file, node.lineno)
            if rel is not None:
                relations.append(rel)
            if bad is not None:
                unres.append(bad)
            continue

        if term.kind == "truthy" and isinstance(term.left, Field):
            fld = term.left
            name = fld.var.lstrip("?")
            if not fld.name:               
                if prov.lookup(blk.function, name) is not None:
                    op = RelOp("NOT_EXISTS" if invert else "EXISTS")
                    relations.append(RelPredicate(
                        op=op, left=fld, right=None, origin_op="Truthy",
                        source_file=src_file, source_line=node.lineno,
                        via_edge=via))
                else:                      
                    kind = prov.var_kind(blk.function, name)
                    key = (name, not invert, kind)
                    path_conds.setdefault(key, PathCondition(
                        var=name, requires=not invert, kind=kind,
                        source_file=src_file, source_line=node.lineno))
            else:                          
                op = RelOp("FALSY" if invert else "TRUTHY")
                relations.append(RelPredicate(
                    op=op, left=fld, right=None, origin_op="Truthy",
                    source_file=src_file, source_line=node.lineno,
                    via_edge=via))
            continue
        unres.append(UnresolvableItem(
            what=f"guard:{term.raw}", cause=f"guard-kind:{term.kind}",
            source_file=src_file, source_line=node.lineno))

    
    entity_vars = sorted({f.var for r in relations
                          for f in (r.left, r.right)
                          if isinstance(f, Field)})
    var_prov: list[VarProvenance] = []
    for var in entity_vars:
        local = var.lstrip("?")
        p = prov.lookup(blk.function, local)
        if p is not None:
            var_prov.append(p)
        else:
            unres.append(UnresolvableItem(
                what=f"var:{var}",
                cause="provenance-unresolved(callee 不可分析/动态来源)",
                source_file=src_file, source_line=0))

    return StateGoal(
        target_block=target_block, function=blk.function, file=src_file,
        constraints=(),
        relations=tuple(relations),
        entity_vars=tuple(entity_vars),
        var_provenance=tuple(var_prov),
        path_conditions=tuple(path_conds.values()),
        unresolvable=tuple(unres),
        evidence=tuple(
            f"{r.source_file}:{r.source_line} {r.render()}"
            f"{'(false 边反转)' if r.via_edge == 'false' else ''}"
            for r in relations),
    )


def guard_analysis_diagnostic(ir, target_block: str) -> dict:
    
    goal = derive_relational_goal(ir, target_block)
    dominators = necessary_guard_edges(ir, target_block)
    dom_lines = {ir.blocks[b].start_line: kind for b, kind in dominators}

    rel_lines = {r.source_line for r in (goal.relations if goal else ())}
    pc_lines = {p.source_line for p in (goal.path_conditions if goal else ())}
    notes: list[str] = []
    if goal is None:
        notes.append("relational: no goal derived (fn/file unparsable)")
    if not dom_lines and goal is not None:
        notes.append("dominator: no unconditional necessary guards; "
                     "relational relations are all conditional or absent")
    for line in sorted(dom_lines):
        if line in rel_lines:
            continue                     
        if line in pc_lines:
            notes.append(f"line {line}: dominator-necessary but only a "
                         f"path condition in relational (non-entity guard)")
            continue
        notes.append(f"line {line}: dominator-necessary with no relational "
                     f"term — check extractor coverage for this guard")
    for line in sorted(rel_lines):
        if line not in dom_lines:
            notes.append(f"line {line}: relational relation NOT "
                         f"unconditional-dominator (conditional under "
                         f"path conditions — expected for wrapped guards)")
    return {
        "target_block": target_block,
        "dominator_guards": [{"line": ln, "edge": kind}
                             for ln, kind in sorted(dom_lines.items())],
        
        "relational_relation_lines": sorted(rel_lines),
        "notes": notes,
    }
