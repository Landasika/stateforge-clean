import hashlib
import json
import platform
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stateforge.analysis.static.icfg import build_icfg
from stateforge.fuzzing.feedback.corpus import GuidedCorpus
from stateforge.fuzzing.guidance.campaign import CampaignConfig, GuidedCampaign
from stateforge.fuzzing.guidance.mutator import BasicMutator
from stateforge.fuzzing.guidance.scheduler import (
    GuidedScheduler,
    UniformScheduler,
)
from stateforge.fuzzing.guidance.target import BasicBlockTarget
from targets.toy_app.adapter import build_adapter as simple_adapter
from targets.toy_branches.adapter import build_adapter as branch_adapter
from targets.toy_nested.adapter import build_adapter as nested_adapter

TRIALS = 20
BUDGET = 2000
TARGETS = {
    "toy_simple": {
        "root": ROOT / "targets" / "toy_app" / "target",
        "seeds": [ROOT / "targets" / "toy_app" / "seeds" / "seed_00.bin",
                  ROOT / "targets" / "toy_app" / "seeds" / "seed_01.bin"],
        "adapter": simple_adapter,
        "target_function": "deep_target",
    },
    "toy_interprocedural": {
        "root": ROOT / "targets" / "toy_nested" / "target",
        "seeds": [ROOT / "targets" / "toy_nested" / "seeds" / "seed_00.bin"],
        "adapter": nested_adapter,
        "target_function": "gate",
    },
    "toy_branches": {
        "root": ROOT / "targets" / "toy_branches" / "target",
        "seeds": [ROOT / "targets" / "toy_branches" / "seeds" / "seed_00.bin"],
        "adapter": branch_adapter,
        "target_function": "deep_target",
    },
}
ARMS = ("directed", "uniform", "coverage_only")


def _target_id(ir, function: str) -> str:
    return next(
        block_id for block_id, block in ir.blocks.items()
        if block.function == function
        and any("TARGET_REACHED" in statement
                for statement in block.statements))


def _scheduler(arm: str, trial: int):
    if arm == "directed":
        return GuidedScheduler(epsilon=0.20, random_seed=trial,
                               min_energy=1, max_energy=1)
    return UniformScheduler(random_seed=trial, energy=1)


def _corpus(arm: str):
    policy = "coverage" if arm == "coverage_only" else "distance"
    return GuidedCorpus(1000, retention_policy=policy)


def _aggregate(rows):
    reached = [row for row in rows if row["target_reached"]]
    executions = [row["executions_to_target"] for row in reached]
    times = [row["wall_clock_time_to_target_seconds"] for row in reached]
    return {
        "trials": len(rows),
        "successes": len(reached),
        "censored": len(rows) - len(reached),
        "success_rate": len(reached) / len(rows),
        "mean_executions_to_target": (
            statistics.mean(executions) if executions else None),
        "median_executions_to_target": (
            statistics.median(executions) if executions else None),
        "min_executions_to_target": (
            min(executions) if executions else None),
        "max_executions_to_target": (
            max(executions) if executions else None),
        "median_wall_clock_to_target_seconds": (
            statistics.median(times) if times else None),
        "mean_executions_per_second": statistics.mean(
            row["executions"] / row["elapsed_seconds"]
            for row in rows if row["elapsed_seconds"] > 0),
        "mean_covered_blocks": statistics.mean(
            row["unique_covered_blocks"] for row in rows),
        "mean_valid_icfg_edges": statistics.mean(
            row["unique_valid_icfg_edges"] for row in rows),
    }


def main() -> int:
    payload = {
        "plan": "directed greybox MVP",
        "generated_at": datetime.now().astimezone().isoformat(),
        "trials": TRIALS,
        "max_executions": BUDGET,
        "energy": 1,
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
        },
        "targets": {},
    }
    try:
        payload["code_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        payload["branch"] = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    except subprocess.CalledProcessError:
        payload["code_commit"] = None
        payload["branch"] = None
    for target_name, target in TARGETS.items():
        ir = build_icfg(target["root"])
        target_id = _target_id(ir, target["target_function"])
        seeds = [path.read_bytes() for path in target["seeds"]]
        arms = {}
        for arm in ARMS:
            rows = []
            for trial in range(TRIALS):
                policy = "coverage" if arm == "coverage_only" else "distance"
                config = CampaignConfig(
                    max_executions=BUDGET,
                    max_input_size=64,
                    max_corpus_size=1000,
                    epsilon=0.20,
                    random_seed=trial,
                    stop_on_target=True,
                    fault_policy="continue",
                    min_energy=1,
                    max_energy=1,
                    scheduler_name=("guided" if arm == "directed"
                                    else "uniform"),
                    corpus_policy=policy,
                )
                campaign = GuidedCampaign(
                    ir=ir,
                    target=BasicBlockTarget(target_id),
                    adapter=target["adapter"](),
                    corpus=_corpus(arm),
                    scheduler=_scheduler(arm, trial),
                    mutator=BasicMutator(trial),
                    config=config,
                )
                result = campaign.run(seeds)
                row = result.to_dict()
                row.update({
                    "arm": arm,
                    "trial": trial,
                    "corpus_policy": policy,
                    "config": config.to_dict(),
                    "corpus_size": len(campaign.corpus),
                    "total_trace_events": campaign.total_trace_events,
                })
                rows.append(row)
            arms[arm] = {"runs": rows, "aggregate": _aggregate(rows)}
        payload["targets"][target_name] = {
            "target_basic_block": target_id,
            "target_source_hash": ir.metadata.get("source_hash"),
            "initial_corpus_sha256": [
                hashlib.sha256(seed).hexdigest() for seed in seeds],
            "initial_corpus_hex": [seed.hex() for seed in seeds],
            "arms": arms,
        }
        print(target_name, json.dumps(
            {arm: data["aggregate"] for arm, data in arms.items()},
            indent=2), flush=True)

    output = ROOT / "evaluation" / "directed_mvp"
    output.mkdir(parents=True, exist_ok=True)
    (output / "baseline.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")

    demo_root = ROOT / "targets" / "toy_app" / "target"
    demo_ir = build_icfg(demo_root)
    demo_target = _target_id(demo_ir, "deep_target")
    demo_config = CampaignConfig(
        max_executions=BUDGET,
        max_input_size=64,
        max_corpus_size=1000,
        epsilon=0.20,
        random_seed=42,
        stop_on_target=True,
        min_energy=1,
        max_energy=1,
        scheduler_name="guided",
        corpus_policy="distance",
        output_dir=output / "demo",
    )
    demo = GuidedCampaign(
        ir=demo_ir,
        target=BasicBlockTarget(demo_target),
        adapter=simple_adapter(),
        corpus=GuidedCorpus(1000, retention_policy="distance"),
        scheduler=GuidedScheduler(epsilon=0.20, random_seed=42,
                                  min_energy=1, max_energy=1),
        mutator=BasicMutator(42),
        config=demo_config,
    )
    demo_result = demo.run(
        [path.read_bytes() for path in TARGETS["toy_simple"]["seeds"]])
    (output / "demo" / "replay.json").write_text(
        json.dumps(demo_result.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(demo_result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
