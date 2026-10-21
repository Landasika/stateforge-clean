from pathlib import Path

from stateforge.adapters.callable import CallableAdapter
from stateforge.analysis.static.icfg import build_icfg
from examples.m1_target import target

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def build_example_ir():
    return build_icfg(EXAMPLES)


def target_block_id(ir):
    return ir.functions["m1_target.target_block"].entry


def example_adapter():
    return CallableAdapter(target)


def example_seeds():
    return [item.read_bytes() for item in sorted((EXAMPLES / "seeds").iterdir())]
