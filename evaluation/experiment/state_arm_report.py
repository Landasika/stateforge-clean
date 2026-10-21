from __future__ import annotations
import argparse
import ast
import json
import statistics
from pathlib import Path
from stateforge.core.ir import ProgramIR
from stateforge.solving.state_seed_injector import (synthesize_micro_model,
                                                    reached_state_atoms)
ARMS = ("A", "B", "C", "D", "E")
_EMPTY_STATE = {"atoms_reached": 0, "atoms": [], "transitions_observed": 0,
                "transitions": [], "deep_state_blocks": 0,
                "deep_block_ids": [], "deep_functions": []}
def _covered_state(workdir: Path) -> dict | None:
    p = Path(workdir) / "epochs" / "global_state.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
def _covered_lines(ir: ProgramIR, target_res: Path, state: dict) -> set[int]:
    covered = set(state.get("covered_blocks") or state.get("blocks") or [])
    lines: set[int] = set()
    for bid in covered:
        block = ir.blocks.get(bid)
        if block is None:
            continue
        try:
            if Path(block.file).resolve() != target_res:
                continue
        except OSError:
            continue
        lines.update(block.line_numbers or
                     range(block.start_line, block.end_line + 1))
    return lines


def _deep_functions(target: Path, guards) -> tuple[set[str], set[frozenset[int]]]:
    
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set(), set()
    module_funcs = {n.name for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    call_lines: dict[int, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_lines.setdefault(node.lineno, set()).add(node.func.id)
    funcs: set[str] = set()
    regions: set[frozenset[int]] = set()
    for g in guards:
        regions.add(g.body_lines)
        for ln in g.body_lines:
            funcs |= call_lines.get(ln, set()) & module_funcs
    return funcs, regions


def state_metrics(ir: ProgramIR | str | Path, target: str, workdir: Path,
                  ledger: bool = True) -> dict:
    
    out = dict(_EMPTY_STATE)
    state = _covered_state(workdir)
    target_path = Path(target)
    micro = synthesize_micro_model(target_path) \
        if target_path.is_file() else None
    if micro is None or state is None:
        return out
    if not isinstance(ir, ProgramIR):
        ir = ProgramIR.from_json(ir)
    reached = reached_state_atoms(ir, target_path, state)
    if ledger:
        lp = Path(workdir) / "epochs" / "state_ledger.json"
        if lp.exists():
            try:
                reached |= set(json.loads(
                    lp.read_text(encoding="utf-8")).get("atoms", []))
            except (OSError, json.JSONDecodeError, ValueError):
                pass
    if not reached:
        return out
    triples: list[list[str]] = []
    for u, v, d in micro.sstg.edges(data=True):
        kind = d.get("kind")
        if kind == "produces" and v in reached:      
            triples.append([u, v, d.get("op") or kind])
        elif kind == "requires" and v in reached:    
            triples.append([v, u, d.get("op") or kind])
    triples.sort()

    
    target_res = micro.target.resolve()
    lines = _covered_lines(ir, target_res, state)
    deep_funcs, regions = _deep_functions(target_path,
                                          (g for g in micro.guards
                                           if g.atom in reached))
    covered = sorted(set(state.get("covered_blocks")
                         or state.get("blocks") or []))
    deep_ids: list[str] = []
    for bid in covered:
        block = ir.blocks.get(bid)
        if block is None:
            continue
        try:
            if Path(block.file).resolve() != target_res:
                continue
        except OSError:
            continue
        blines = set(block.line_numbers or
                     range(block.start_line, block.end_line + 1))
        if block.function in deep_funcs or any(blines & r for r in regions):
            deep_ids.append(bid)

    out.update(atoms_reached=len(reached), atoms=sorted(reached),
               transitions_observed=len(triples), transitions=triples,
               deep_state_blocks=len(deep_ids), deep_block_ids=deep_ids,
               deep_functions=sorted(deep_funcs))
    return out





def _rows(workdir: Path) -> dict | None:
    gs = Path(workdir) / "group_summary.json"
    if not gs.exists():
        return None
    try:
        g = json.loads(gs.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {"blocks": g.get("final_blocks"), "edges": g.get("final_edges"),
            "executions": g.get("total_executions")}

def _paired(rows: dict, x: str, y: str) -> float | None:
    
    diffs = [r[x]["blocks"] - r[y]["blocks"] for r in rows.values()
             if r.get(x) and r.get(y)
             and r[x]["blocks"] is not None and r[y]["blocks"] is not None]
    return round(statistics.mean(diffs), 1) if diffs else None


def _mean_blocks(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 1) if vals else None


def _merge_state(e_runs: list[dict]) -> dict:
    
    merged = dict(_EMPTY_STATE)
    if not e_runs:
        return merged
    atoms: set[str] = set()
    triples: set[tuple] = set()
    deep_ids: set[str] = set()
    deep_funcs: set[str] = set()
    for r in e_runs:
        atoms |= set(r["atoms"])
        triples |= {tuple(t) for t in r["transitions"]}
        deep_ids |= set(r["deep_block_ids"])
        deep_funcs |= set(r["deep_functions"])
    merged["atoms_reached"] = len(atoms)
    merged["atoms"] = sorted(atoms)
    merged["transitions"] = [list(t) for t in sorted(triples)]
    merged["transitions_observed"] = len(triples)
    merged["deep_state_blocks"] = len(deep_ids)
    merged["deep_block_ids"] = sorted(deep_ids)
    merged["deep_functions"] = sorted(deep_funcs)
    return merged


def build_report(run_dir: str | Path, target: str | None = None,
                 ir_path: str | None = None) -> dict:
    
    run_dir = Path(run_dir)
    manifest: dict = {}
    mp = run_dir / "run_manifest.json"
    if mp.exists():
        try:
            manifest = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    ir_file = ir_path or manifest.get("ir") \
        or str(run_dir / "ir" / "program_ir.json")
    ir_obj = None
    if Path(ir_file).exists():
        try:
            ir_obj = ProgramIR.from_json(ir_file)
        except (OSError, ValueError, KeyError):
            ir_obj = None

    report: dict = {"run_dir": str(run_dir), "targets": {}}
    if not run_dir.exists():
        return report
    for tdir in sorted(p for p in run_dir.iterdir()
                       if p.is_dir() and p.name not in ("ir",)):
        runs = sorted(d for d in tdir.iterdir()
                      if d.is_dir() and d.name.startswith("run"))
        if not runs:
            continue
        name = tdir.name
        rows: dict[str, dict] = {arm: {} for arm in ARMS}
        per_run: dict[str, dict] = {}
        for rd in runs:
            for arm in ARMS:
                r = _rows(rd / arm)
                if r is not None:
                    rows[arm][rd.name] = r
                    per_run.setdefault(rd.name, {})[arm] = r
        entry: dict = {
            "runs": len(runs),
            "mean": {arm: {"blocks": _mean_blocks(
                               [r["blocks"] for r in rows[arm].values()]),
                           "edges": _mean_blocks(
                               [r["edges"] for r in rows[arm].values()])}
                     for arm in ARMS if rows[arm]},
            "pairwise": {"E_minus_D": _paired(per_run, "E", "D"),
                         "D_minus_C": _paired(per_run, "D", "C"),
                         "D_minus_B": _paired(per_run, "D", "B")},
        }
        tpath = target or (manifest.get("targets") or {}).get(name)
        if tpath is None:                     
            cand = Path("stateforge/targets") / name / f"{name}.py"
            if cand.is_file():
                tpath = str(cand)
            else:
                hits = sorted(Path("stateforge/targets").glob(f"*/{name}.py"))
                tpath = str(hits[0]) if hits else None
        if tpath and ir_obj is not None:
            e_runs = []
            d_states: dict[str, dict] = {}
            for rd in runs:
                e_runs.append({"run": rd.name,
                               **state_metrics(ir_obj, tpath, rd / "E")})
                d_states[rd.name] = state_metrics(
                    ir_obj, tpath, rd / "D", ledger=False)
            d_atoms: set[str] = set()          
            for d in d_states.values():
                d_atoms |= set(d["atoms"])
            entry["state"] = {
                "E": _merge_state(e_runs),      
                "E_runs": e_runs,               
                "D_coverage_proxy": {
                    "atoms_reached": len(d_atoms),
                    "per_run": {k: v["atoms_reached"]
                                for k, v in d_states.items()},
                },
            }
        report["targets"][name] = entry
    return report





def render_text(report: dict) -> str:
    lines: list[str] = [f"five-arm report — {report['run_dir']}"]
    for name, e in report["targets"].items():
        lines.append(f"\n== {name} (runs={e['runs']}) ==")
        lines.append("arm  mean_blocks  mean_edges")
        for arm in ARMS:
            m = e["mean"].get(arm)
            if m:
                lines.append(f"{arm:<4} {m['blocks']!s:<12} {m['edges']}")
        pw = e["pairwise"]
        for key in ("D_minus_B", "D_minus_C", "E_minus_D"):
            if pw.get(key) is not None:
                lines.append(f"{key}: {pw[key]:+.1f}")
        st = e.get("state")
        if st:
            m = st["E"]
            lines.append(
                f"E state: state_atoms_reached={m['atoms_reached']} "
                f"({','.join(m['atoms']) or '-'}) "
                f"transitions_observed={m['transitions_observed']} "
                f"deep_state_blocks={m['deep_state_blocks']}")
            for s in st.get("E_runs", []):
                lines.append(
                    f"  [{s['run']}] atoms={s['atoms_reached']} "
                    f"transitions={s['transitions_observed']} "
                    f"deep_blocks={s['deep_state_blocks']}")
            lines.append(f"D coverage-proxy atoms: "
                         f"{st['D_coverage_proxy']['atoms_reached']} "
                         f"{st['D_coverage_proxy']['per_run']}")
    return "\n".join(lines)


def write_json(report: dict, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                 encoding="utf-8")
    return p


def main() -> int:
    parser = argparse.ArgumentParser(
        description="five-arm (E=state) comparison report")
    parser.add_argument("run_dir")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="JSON 输出路径(缺省 <run_dir>/state_arm_report.json)")
    parser.add_argument("--target", default=None, help="覆盖靶路径解析")
    parser.add_argument("--ir", default=None, help="覆盖 IR 路径解析")
    args = parser.parse_args()
    report = build_report(args.run_dir, target=args.target, ir_path=args.ir)
    text = render_text(report)
    print(text)
    out_json = args.json_out or str(Path(args.run_dir)
                                    / "state_arm_report.json")
    write_json(report, out_json)
    (Path(args.run_dir) / "state_arm_report.txt").write_text(
        text + "\n", encoding="utf-8")
    print(f"\n[out] {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
