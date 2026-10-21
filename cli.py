
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

from stateforge.core.ir import ProgramIR
from stateforge.core.log import setup_logging
from stateforge.core.serialization import save_json, save_program_ir
from stateforge.runtime.io import merge_events
from stateforge.runtime.coverage import coverage
from stateforge.fuzzing.feedback.engine import compute_feedback
from stateforge.analysis.static.icfg import build_icfg


def analyze_cmd(target: str, out: str, callgraph_path: str | None = None) -> int:
    root = Path(target).resolve()
    callgraph = None
    if callgraph_path:
        callgraph = json.loads(Path(callgraph_path).read_text(encoding="utf-8"))
        if "graph" in callgraph:
            callgraph = callgraph["graph"]
    ir = build_icfg(root, callgraph=callgraph)
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    save_program_ir(ir, outdir / "program_ir.json")
    save_json({
        "target": str(root),
        "functions": len(ir.functions),
        "blocks": len(ir.blocks),
        "edges": len(ir.edges),
        "unresolved_calls": len(ir.metadata.get("unresolved_calls", [])),
        "edge_kinds": {kind: sum(e.kind == kind for e in ir.edges)
                        for kind in sorted({e.kind for e in ir.edges})},
    }, outdir / "summary.json")
    print(f"[icfg] functions={len(ir.functions)} blocks={len(ir.blocks)} edges={len(ir.edges)}")
    print(f"[out] {outdir / 'program_ir.json'}")
    return 0


def feedback_cmd(ir_path: str, trace_paths: list[str], out: str) -> int:
    ir = ProgramIR.from_json(ir_path)
    ir_stale = False                                   
    root = ir.metadata.get("root")
    if root:
        from stateforge.analysis.static.icfg import _source_hash
        try:
            ir_stale = _source_hash(Path(root)) != ir.metadata.get("source_hash")
        except OSError:
            ir_stale = True
        if ir_stale:
            print("[warn] ir is stale: sources changed since analyze",
                  file=sys.stderr)
    try:
        events = merge_events(trace_paths)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"[error] unable to read trace artifact: {exc}", file=sys.stderr)
        return 2
    report = compute_feedback(ir, events)
    payload = {
        "covered_blocks": sorted(report.overlay.covered_blocks),
        "covered_edges": [list(e) for e in sorted(report.overlay.covered_edges)],
        "dynamic_edge_kinds": {
            f"{src}\t{dst}": sorted(kinds)
            for (src, dst), kinds in sorted(report.trace.edge_kinds.items())
        },
        "frontiers": [f.__dict__ for f in report.frontiers],
        "edge_frontiers": [f.__dict__ for f in (report.edge_frontiers or [])],
        "request_count": report.request_count,
        "block_request_count": report.overlay.block_request_count,
        "block_hits": report.overlay.block_hits,
        "ir_stale": ir_stale,
        "target_distances": report.target_distances,
        "unresolved_events": len(report.trace.unresolved),
        "block_coverage": report.block_coverage,
        "coverage": coverage(ir, report.trace).to_dict(),
    }
    save_json(payload, out)
    print(f"[feedback] blocks={len(report.overlay.covered_blocks)} "
          f"edges={len(report.overlay.covered_edges)} frontiers={len(report.frontiers)}")
    print(f"[out] {out}")
    return 0


def experiment_cmd(target: str, out: str, trace_paths: list[str] | None = None) -> int:
    outdir = Path(out)
    analyze_cmd(target, str(outdir))
    if trace_paths:
        feedback_cmd(str(outdir / "program_ir.json"), trace_paths,
                     str(outdir / "feedback.json"))
    else:
        print("[experiment] no trace supplied; static artifact is ready for Atheris")
    return 0


def state_cmd(target: str, out: str) -> int:
    
    from stateforge.state.observer import run_state_analysis
    root = Path(target).resolve()
    result = run_state_analysis(root)
    payload = dict(result)
    payload["target"] = str(root)
    outpath = Path(out)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    save_json(payload, outpath)
    print(f"[state] variables={result['n_variables']} "
          f"predicates={result['n_predicates']} "
          f"candidates={len(result['transitions']['static_candidates'])}")
    print(f"[out] {out}")
    return 0


def _load_adapter(spec: str):
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("--adapter must be module:attribute")
    module = importlib.import_module(module_name)
    adapter = getattr(module, attribute)
    if callable(adapter) and not callable(getattr(adapter, "execute", None)):
        adapter = adapter()
    if not callable(getattr(adapter, "execute", None)):
        raise ValueError("adapter must provide execute(data)")
    return adapter


def _load_seed_corpus(path: str) -> list[bytes]:
    root = Path(path)
    if root.is_file():
        return [root.read_bytes()]
    if not root.is_dir():
        raise FileNotFoundError(f"seed corpus not found: {path}")
    files = sorted(item for item in root.iterdir() if item.is_file())
    if not files:
        raise ValueError(f"seed corpus is empty: {path}")
    return [item.read_bytes() for item in files]


def guided_cmd(args) -> int:
    from stateforge.fuzzing.feedback.corpus import GuidedCorpus
    from stateforge.fuzzing.guidance.campaign import (
        CampaignConfig,
        GuidedCampaign,
    )
    from stateforge.fuzzing.guidance.mutator import BasicMutator
    from stateforge.fuzzing.guidance.scheduler import (
        EmptyCorpusError,
        GuidedScheduler,
        UniformScheduler,
    )
    from stateforge.fuzzing.guidance.target import (
        BasicBlockTarget,
        GuidanceError,
    )

    try:
        ir = ProgramIR.from_json(args.ir)
        seeds = _load_seed_corpus(args.corpus)
        adapter = _load_adapter(args.adapter)
        config = CampaignConfig(
            max_executions=args.max_execs,
            max_seconds=args.max_seconds,
            max_input_size=args.max_input_size,
            max_corpus_size=args.max_corpus_size,
            epsilon=args.epsilon,
            random_seed=args.random_seed,
            stop_on_target=args.stop_on_target,
            fault_policy=args.fault_policy,
            allow_stale_ir=args.allow_stale_ir,
            output_dir=args.out,
            min_energy=args.min_energy,
            max_energy=args.max_energy,
            scheduler_name=args.scheduler,
            progress_every=args.progress_every,
        )
        target = BasicBlockTarget(args.target_bb)
        corpus = GuidedCorpus(args.max_corpus_size)
        if args.scheduler == "uniform":
            scheduler = UniformScheduler(
                random_seed=args.random_seed, energy=args.min_energy)
        else:
            scheduler = GuidedScheduler(
                epsilon=args.epsilon,
                random_seed=args.random_seed,
                min_energy=args.min_energy,
                max_energy=args.max_energy,
            )
        campaign = GuidedCampaign(
            ir=ir,
            target=target,
            adapter=adapter,
            corpus=corpus,
            scheduler=scheduler,
            mutator=BasicMutator(args.random_seed),
            config=config,
        )
        result = campaign.run(seeds)
    except (GuidanceError, EmptyCorpusError, ValueError, OSError,
            ImportError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    print(f"[guided] target={result.target_block_id} "
          f"reached={result.target_reached} executions={result.executions} "
          f"best_distance={result.best_distance} "
          f"reason={result.termination_reason}")
    print(json.dumps(result.to_dict(), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="StateForge structural feedback")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="DEBUG logging on stderr (default INFO)")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="build a stable ProgramIR/ICFG")
    analyze.add_argument("target")
    analyze.add_argument("--out", default="results/structural")
    analyze.add_argument("--callgraph")
    feedback = sub.add_parser("feedback", help="map a runtime trace and find frontiers")
    feedback.add_argument("ir")
    feedback.add_argument("trace", nargs="+", help="one or more trace artifacts")
    feedback.add_argument("--out", default="results/feedback.json")
    experiment = sub.add_parser("experiment", help="build static artifact and optional feedback")
    experiment.add_argument("target")
    experiment.add_argument("--out", default="results/experiment")
    experiment.add_argument("--trace", action="append", dest="traces",
                            help="trace artifact; repeat for multiple seeds")
    viz = sub.add_parser("viz", help="static+dynamic coverage overlay dot (P1-5)")
    viz.add_argument("ir")
    viz.add_argument("feedback")
    viz.add_argument("--out", default="results/coverage.dot")
    state = sub.add_parser("state",
                           help="session-state variables/predicates/domains "
                                "+ static transition candidates (P3-M2)")
    state.add_argument("target")
    state.add_argument("--out", default="results/state.json")
    guided = sub.add_parser("guided", help="basic-block directed greybox campaign")
    guided.add_argument("--ir", required=True)
    guided.add_argument("--target-bb", required=True)
    guided.add_argument("--corpus", required=True)
    guided.add_argument("--adapter", required=True)
    guided.add_argument("--out", default="results/m1")
    guided.add_argument("--max-execs", type=int, default=10000)
    guided.add_argument("--max-seconds", type=float)
    guided.add_argument("--max-input-size", type=int, default=4096)
    guided.add_argument("--max-corpus-size", type=int, default=1000)
    guided.add_argument("--epsilon", type=float, default=0.20)
    guided.add_argument("--random-seed", type=int, default=0)
    guided.add_argument("--min-energy", type=int, default=1)
    guided.add_argument("--max-energy", type=int, default=32)
    guided.add_argument("--fault-policy", choices=("continue", "stop"),
                        default="continue")
    guided.add_argument("--scheduler", choices=("guided", "uniform"),
                        default="guided")
    guided.add_argument("--progress-every", type=int, default=100)
    guided.add_argument("--allow-stale-ir", action="store_true")
    guided.add_argument("--stop-on-target", action=argparse.BooleanOptionalAction,
                        default=True)
    args = parser.parse_args()
    setup_logging(args.verbose)
    if args.command == "guided":
        return guided_cmd(args)
    if args.command == "analyze":
        return analyze_cmd(args.target, args.out, args.callgraph)
    if args.command == "experiment":
        return experiment_cmd(args.target, args.out, args.traces)
    if args.command == "state":
        return state_cmd(args.target, args.out)
    if args.command == "viz":
        from stateforge.evaluation.viz.coverage_dot import coverage_dot
        ir_obj = ProgramIR.from_json(args.ir)
        fb = json.loads(Path(args.feedback).read_text(encoding="utf-8"))
        out = coverage_dot(ir_obj, fb, args.out)
        print(f"[viz] {out}")
        return 0
    return feedback_cmd(args.ir, args.trace, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
