from __future__ import annotations
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
from pathlib import Path
from stateforge.core.ir import ProgramIR
from stateforge.evaluation.experiment.epoch import EXECUTION_EDGE_KINDS
from stateforge.evaluation.experiment.runner import GROUPS, run_experiment
def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
def _manifest(target: str, ir: str, out: Path, args) -> dict:
    def _git(*cmd):
        try:
            return subprocess.run(["git", *cmd], capture_output=True,
                                  text=True, check=True).stdout.strip()
        except Exception:                      
            return "unknown"
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "python": platform.python_version(),
        "atheris": __import__("importlib.metadata", fromlist=["version"])
        .version("atheris"),
        "target": target, "target_sha": _sha(target), "ir_sha": _sha(ir),
        "runs": args.runs, "epochs": args.epochs,
        "seconds_per_epoch": args.seconds, "seed0": args.seed0,
    }


def _curve_points(run_dir: Path, group: str) -> list[tuple[float, int, int]]:
    
    p = run_dir / group / "group_summary.json"
    if not p.exists():
        return []
    g = json.loads(p.read_text(encoding="utf-8"))
    group_start = g["epoch_records"][0]["wall"]["start_offset"]
    pts = []
    for rec in g["epoch_records"]:
        base = rec["wall"]["start_offset"] - group_start   
        for s in rec["snapshots"]:
            pts.append((base + s["t"], s["blocks"], s["edges"]))
    return sorted(pts)


def _auc(points, horizon: float) -> tuple[float, float]:
    
    if not points:
        return 0.0, 0.0
    area, last_t, last_v = 0.0, 0.0, 0.0
    for t, v, _ in points:
        t = min(t, horizon)
        if t < last_t:
            continue
        area += (t - last_t) * last_v
        last_t, last_v = t, v
        if t >= horizon:
            break
    area += max(0.0, horizon - last_t) * last_v
    return area, area / horizon

def _stats(vals):
    vs = sorted(v for v in vals if v is not None)
    if not vs:
        return {}
    q1, q3 = (statistics.quantiles(vs, n=4)[0], statistics.quantiles(vs, n=4)[2]) \
        if len(vs) >= 4 else (vs[0], vs[-1])
    return {"mean": round(statistics.mean(vs), 4),
            "median": round(statistics.median(vs), 4),
            "stdev": round(statistics.stdev(vs), 4) if len(vs) > 1 else 0.0,
            "iqr": [round(q1, 3), round(q3, 3)], "n": len(vs)}


def run_campaign(target: str, ir_path: str, out: Path, runs: int, epochs: int,
                 seconds: float, seed0: int,
                 groups: tuple[str, ...] | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    ir = ProgramIR.from_json(ir_path)
    total_blocks = len(ir.blocks)
    total_edges = sum(1 for e in ir.edges if e.kind in EXECUTION_EDGE_KINDS)
    horizon = epochs * seconds

    class _Args:                                     
        pass
    margs = _Args()
    margs.runs, margs.epochs = runs, epochs
    margs.seconds, margs.seed0 = seconds, seed0
    manifest = _manifest(target, ir_path, out, margs)
    manifest["total_blocks"], manifest["total_edges"] = total_blocks, total_edges
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    per_run = []
    for k in range(runs):
        seed = seed0 + k * 100
        run_dir = out / f"run{k:02d}"
        print(f"[campaign] run {k + 1}/{runs} seed={seed}", flush=True)
        
        exp_kwargs = {} if groups is None else {"groups": groups}
        rep = run_experiment(target, ir_path, run_dir, epochs, seconds, seed,
                             **exp_kwargs)
        rec = {"seed": seed}
        for group, g in rep["groups"].items():
            rec[group] = {
                "total_executions": g["total_executions"],
                "wall_span": g["wall_span"],
                "final_blocks": g["final_blocks"],
                "final_edges": g["final_edges"],
                "total_feedback_seconds": g["total_feedback_seconds"],
                "throughput": round(g["total_executions"] /
                                    max(g["wall_span"], 1e-9), 1),
            }
            if group != "A_native":
                pts = _curve_points(run_dir, group)
                abs_auc, norm_auc = _auc(
                    [(t, b, 0) for t, b, _ in pts], horizon)
                abs_e, norm_e = _auc(
                    [(t, e, 0) for t, _, e in pts], horizon)
                rec[group]["auc_blocks_abs"] = round(abs_auc, 1)
                rec[group]["auc_blocks_norm"] = round(
                    norm_auc / max(total_blocks, 1), 4)
                rec[group]["auc_edges_abs"] = round(abs_e, 1)
                rec[group]["auc_edges_norm"] = round(
                    norm_e / max(total_edges, 1), 4)
            if "novel_seed_gain" in g:
                rec[group]["novel_seed_gain"] = g["novel_seed_gain"]
            
            
            for k in ("state_atoms_reached", "state_injections_total"):
                if k in g:
                    rec[group][k] = g[k]
        per_run.append(rec)

    summary = {"manifest": manifest, "per_run": per_run, "aggregate": {},
               "questions": {}}
    
    
    ran = {g for r in per_run for g in r}
    for group in GROUPS:
        if group not in ran:
            continue
        
        
        
        
        
        
        keys = sorted({k for r in per_run for k in r[group]
                       if k != "novel_seed_gain"})
        summary["aggregate"][group] = {
            k: _stats([r[group][k] for r in per_run if k in r[group]])
            for k in keys}
    
    q = summary["questions"]
    if {"A_native", "A_measure"} <= ran:
        q["tracing_overhead"] = {
            "a_native_tput": _stats([r["A_native"]["throughput"] for r in per_run]),
            "a_measure_tput": _stats([r["A_measure"]["throughput"] for r in per_run]),
            "ratio_measure_over_native": round(
                statistics.mean([r["A_measure"]["throughput"] for r in per_run]) /
                max(statistics.mean([r["A_native"]["throughput"] for r in per_run]),
                    1e-9), 5)}
    if {"A_measure", "B"} <= ran:
        q["restart_penalty_final_blocks"] = _stats(
            [r["B"]["final_blocks"] - r["A_measure"]["final_blocks"] for r in per_run])
    if {"B", "C"} <= ran:
        q["feedback_gain_final_blocks"] = _stats(
            [r["C"]["final_blocks"] - r["B"]["final_blocks"] for r in per_run])
        q["feedback_gain_auc_norm"] = _stats(
            [r["C"]["auc_blocks_norm"] - r["B"]["auc_blocks_norm"] for r in per_run])
    for gname in ("D2R", "D2P"):
        if gname not in ran:
            continue
        runs_g = []
        for k, r in enumerate(per_run):
            gs = json.loads((out / f"run{k:02d}" / gname / "group_summary.json")
                            .read_text(encoding="utf-8"))
            runs_g.append({"champions": gs.get("portfolio_champions"),
                           "replacements": gs.get("portfolio_replacements"),
                           "yield": gs.get("portfolio_yield"),
                           "cdr": gs.get("corpus_dilution_ratio")})
        q[f"diagnostics_{gname}"] = runs_g
    nsg = [r["C"]["novel_seed_gain"] for r in per_run
           if "C" in r and "novel_seed_gain" in r["C"]]
    if {"C", "D1"} <= ran:
        q["directed_gain_final_blocks"] = _stats(
            [r["D1"]["final_blocks"] - r["C"]["final_blocks"] for r in per_run])
        q["directed_gain_auc_norm"] = _stats(
            [r["D1"]["auc_blocks_norm"] - r["C"]["auc_blocks_norm"] for r in per_run])
    if {"D2R", "D2P"} <= ran:
        q["portfolio_gain_final_blocks"] = _stats(
            [r["D2P"]["final_blocks"] - r["D2R"]["final_blocks"] for r in per_run])
        q["portfolio_gain_auc_norm"] = _stats(
            [r["D2P"]["auc_blocks_norm"] - r["D2R"]["auc_blocks_norm"] for r in per_run])
    
    if {"D1", "E"} <= ran:
        q["state_gain_final_blocks"] = _stats(
            [r["E"]["final_blocks"] - r["D1"]["final_blocks"] for r in per_run])
        q["state_gain_auc_norm"] = _stats(
            [r["E"]["auc_blocks_norm"] - r["D1"]["auc_blocks_norm"] for r in per_run])
    paired = {}
    if {"C", "D1"} <= ran:
        paired["D1_minus_C"] = [
            round(r["D1"]["auc_blocks_norm"] - r["C"]["auc_blocks_norm"], 4)
            for r in per_run]
    if {"D2R", "D2P"} <= ran:
        paired["D2P_minus_D2R"] = [
            round(r["D2P"]["auc_blocks_norm"] - r["D2R"]["auc_blocks_norm"], 4)
            for r in per_run]
    if {"D1", "E"} <= ran:
        paired["E_minus_D1"] = [
            round(r["E"]["auc_blocks_norm"] - r["D1"]["auc_blocks_norm"], 4)
            for r in per_run]
    q["paired_deltas"] = paired
    
    if nsg:
        q["novel_seed_gain"] = {
            "sf_total": sum(x["sf_candidates_total"] for x in nsg),
            "sf_unique": sum(x["sf_unique_vs_native"] for x in nsg),
            "gain_mean": _stats([x["novel_seed_gain"] for x in nsg
                                 if x["novel_seed_gain"] is not None])}
    
    
    
    
    csv = ["group,t,blocks_mean,blocks_p25,blocks_p75"]
    for group in ("A_measure", "B", "C", "D1", "D2R", "D2P", "E"):
        if group not in ran:
            continue               
        grid = {t: [] for t in range(0, int(horizon) + 1)}
        for k in range(runs):
            pts = _curve_points(out / f"run{k:02d}", group)
            last = 0.0
            for t in range(0, int(horizon) + 1):
                while pts and pts[0][0] <= t:
                    last = pts.pop(0)[1]
                grid[t].append(last)
        for t in range(0, int(horizon) + 1):
            vs = sorted(grid[t])
            if vs:
                q1, q3 = (statistics.quantiles(vs, n=4)[0],
                          statistics.quantiles(vs, n=4)[2]) if len(vs) >= 4 \
                    else (vs[0], vs[-1])
                csv.append(f"{group},{t},{statistics.mean(vs):.2f},"
                           f"{q1:.2f},{q3:.2f}")
    (out / "curves.csv").write_text("\n".join(csv), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=1,
                                                 ensure_ascii=False),
                                      encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("ir")
    parser.add_argument("--out", required=True)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--seed0", type=int, default=7)
    parser.add_argument(
        "--groups", default=None,
        help="逗号分隔的 GROUPS 子集,如 'D1,E'(缺省=全部八组)")
    args = parser.parse_args(argv)
    
    
    groups = None
    if args.groups is not None:
        requested = tuple(g.strip() for g in args.groups.split(",")
                          if g.strip())
        unknown = [g for g in requested if g not in GROUPS]
        if unknown or not requested:
            parser.error(f"--groups 无效: {unknown or '空子集'};"
                         f" 有效组: {', '.join(GROUPS)}")
        groups = requested
    
    
    
    
    
    try:
        ir_blocks = ProgramIR.from_json(args.ir).blocks
    except Exception as exc:                    
        parser.error(f"IR 无法载入: {args.ir}"
                     f"({type(exc).__name__}: {exc});请对靶套件目录重新"
                     " analyze——`python -m stateforge.cli analyze <suite-dir> "
                     "--out results/structural`,再以其 program_ir.json "
                     "作为 ir 参数")
    if not ir_blocks:
        parser.error(
            f"IR 无块(blocks=0): {args.ir};请对靶套件目录重新 analyze——"
            "`python -m stateforge.cli analyze <suite-dir> "
            "--out results/structural`,再以其 program_ir.json 作为 ir 参数")
    s = run_campaign(args.target, args.ir, Path(args.out), args.runs,
                     args.epochs, args.seconds, args.seed0, groups=groups)
    print(json.dumps(s["questions"], indent=1, ensure_ascii=False))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
