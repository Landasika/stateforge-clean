
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from stateforge.core.ir import ProgramIR, FlowEdge, BasicBlock
from stateforge.analysis.static.cfg import build_function_cfg

_SKIP = {"tests", "__pycache__", "migrations", "node_modules", ".git", "golden",
         ".venv", "venv", ".tox", ".eggs", "site-packages"}

_OWNED_STOP = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _iter_owned_calls(fn_node: ast.FunctionDef | ast.AsyncFunctionDef):
    stack = list(fn_node.body)
    while stack:
        node = stack.pop()
        if isinstance(node, _OWNED_STOP):
            continue                      
        if isinstance(node, ast.Call):
            yield node
        stack.extend(ast.iter_child_nodes(node))

def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if not any(part in _SKIP for part in path.parts):
            yield path


def _source_hash(root: Path) -> str:
    
    parts = []
    for path in _files(root):
        st = path.stat()
        parts.append(f"{path}:{st.st_size}:{st.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def build_icfg(app_root: str | Path, callgraph: dict[str, list[str]] | None = None,
               include_all_functions: bool = True) -> ProgramIR:
    root = Path(app_root).resolve()
    ir = ProgramIR(metadata={"root": str(root), "kind": "icfg", "version": 1})
    ast_functions: dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef] = {}
    aliases: dict[str, list[str]] = {}
    for path in _files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        module = _module_name(root, path)
        for node, class_path in _walk_with_class(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                
                
                short = ".".join(class_path + [node.name]) if class_path else node.name
                qname = f"{module}.{short}"
                ast_functions[(module, short)] = node
                aliases.setdefault(short, []).append(qname)
                rel_id = str(path.relative_to(root))
                cfg = build_function_cfg(node, str(path), module, id_file=rel_id)
                if not include_all_functions and callgraph and qname not in callgraph:
                    continue
                ir.functions[qname] = cfg.function
                ir.blocks.update(cfg.blocks)
                for edge in cfg.edges:
                    ir.add_edge(edge)

    
    
    
    
    unresolved: list[dict[str, object]] = []
    for qname, fn in list(ir.functions.items()):
        module, _, fname = qname.rpartition(".")
        node = ast_functions.get((module, fname))
        if node is None:
            continue
        block_calls: dict[str, list[tuple[int, int, str]]] = {}
        for call in _iter_owned_calls(node):
            callee_short = _callee_name(call)
            callee = _resolve_callee(callee_short, module, ast_functions, aliases)
            if callee is None and callee_short and callgraph is not None:
                
                
                callee = _resolve_via_callgraph(qname, callee_short,
                                                ir, callgraph)
            line = getattr(call, "lineno", 0)
            if callee is None or callee not in ir.functions:
                unresolved.append({"caller": qname, "callee": callee_short,
                                   "line": line})
                continue
            host = next((bid for bid in fn.blocks
                         if line in ir.blocks[bid].line_numbers), None)
            if host is None:
                unresolved.append({"caller": qname, "callee": callee_short,
                                   "reason": "no host block", "line": line})
                continue
            col = getattr(call, "col_offset", 0)
            block_calls.setdefault(host, []).append((line, col, callee))

        for host, calls in block_calls.items():
            calls.sort(key=lambda t: (t[0], t[1]))   
            succs = [out for out in ir.outgoing(host)
                     if out.kind in ("flow", "true", "false")]
            continuations = succs or []          
            for out in succs:
                ir.remove_edge(host, out.dst, out.kind)
            file = ir.blocks[host].file
            root_str = str(root)
            id_file = file[len(root_str) + 1:] if file.startswith(root_str + "/") else file
            prev = host
            chain_blocks: list[str] = []
            for n, (line, _col, callee) in enumerate(calls, start=1):
                cs = f"{id_file}::{fname}::{line}-{line}::callsite::{n}"
                rs = f"{id_file}::{fname}::{line}-{line}::returnsite::{n}"
                ir.blocks[cs] = BasicBlock(cs, file, module, fname, line, line,
                                           "callsite", [f"<call> {callee}"], [line])
                ir.blocks[rs] = BasicBlock(rs, file, module, fname, line, line,
                                           "returnsite", [f"<ret> {callee}"], [line])
                chain_blocks.extend([cs, rs])
                ir.add_edge(FlowEdge(prev, cs, "flow", callsite_line=line,
                                     callee=callee))
                ir.add_edge(FlowEdge(cs, ir.functions[callee].entry, "call",
                                     callsite_line=line, callee=callee))
                ir.add_edge(FlowEdge(ir.functions[callee].exit, rs, "return",
                                     callsite_line=line, callee=callee))
                prev = rs
            if continuations:
                for out in continuations:       
                    ir.add_edge(FlowEdge(prev, out.dst, out.kind,
                                         condition=out.condition))
            else:
                ir.add_edge(FlowEdge(prev, fn.exit, "flow"))
            fn.blocks.extend(chain_blocks)
    ir.metadata["callgraph_supplied"] = callgraph is not None
    ir.metadata["function_count"] = len(ir.functions)
    ir.metadata["block_count"] = len(ir.blocks)
    ir.metadata["edge_count"] = len(ir.edges)
    ir.metadata["unresolved_calls"] = unresolved
    ir.metadata["source_hash"] = _source_hash(root)
    return ir


def _walk_with_class(tree: ast.Module):
    
    stack = [(node, []) for node in ast.iter_child_nodes(tree)]
    while stack:
        node, path = stack.pop()
        yield node, path
        child_path = path + [node.name] if isinstance(node, ast.ClassDef) else path
        stack.extend((child, child_path)
                     for child in ast.iter_child_nodes(node))


def _resolve_via_callgraph(caller: str, short: str | None, ir: ProgramIR,
                           callgraph: dict[str, list[str]]) -> str | None:
    
    if not short:
        return None
    known = set(ir.functions)
    callees: set[str] = set()
    for key, targets in callgraph.items():
        if key != caller and not key.endswith("." + caller):
            continue
        for target in targets:
            tname = target.rsplit(".", 1)[-1]
            if tname != short:
                continue
            if target in known:
                callees.add(target)
            else:                       
                for fn in known:
                    if target == fn or target.endswith("." + fn):
                        callees.add(fn)
    return callees.pop() if len(callees) == 1 else None


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _resolve_callee(short: str | None, module: str, funcs, aliases) -> str | None:
    if not short:
        return None
    direct = (module, short)
    if direct in funcs:
        return f"{module}.{short}"
    candidates = [f"{m}.{n}" for (m, n) in funcs if n == short]
    if len(candidates) == 1:
        return candidates[0]
    aliased = aliases.get(short, [])
    return aliased[0] if len(aliased) == 1 else None
