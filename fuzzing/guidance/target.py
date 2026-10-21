
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from stateforge.analysis.static.icfg import _source_hash
from stateforge.core.ir import ProgramIR
from stateforge.fuzzing.feedback.distance import target_distances
from stateforge.runtime.mapper import MappedTrace


class GuidanceError(ValueError):
    pass


class InvalidTargetError(GuidanceError):
    pass


class StaleIRError(GuidanceError):
    pass


@dataclass(frozen=True)
class BasicBlockTarget:
    block_id: str
    kind: str = "basic_block"


class TargetManager:
    def __init__(self, ir: ProgramIR, target: BasicBlockTarget,
                 allow_stale: bool = False, validate_source: bool = True):
        if target.block_id not in ir.blocks:
            raise InvalidTargetError(
                f"target basic block not found in ProgramIR: {target.block_id}")
        self.ir = ir
        self.target = target
        self.allow_stale = allow_stale
        self._distances = target_distances(ir, {target.block_id})
        self._distances.setdefault(target.block_id, 0)
        self._distance_view = MappingProxyType(self._distances)
        self.stale = False
        if validate_source:
            self.stale = self._source_is_stale()
            if self.stale and not allow_stale:
                raise StaleIRError(
                    "ProgramIR is stale: source files changed since analysis")

    @property
    def block_id(self) -> str:
        return self.target.block_id

    @property
    def distances(self) -> Mapping[str, int]:
        return self._distance_view

    def distance(self, block_id: str) -> int | None:
        return self._distances.get(block_id)

    def distance_for_trace(self, trace: MappedTrace) -> int | None:
        if self.target.block_id in trace.blocks:
            return 0
        known = [self._distances[block] for block in trace.blocks
                 if block in self._distances]
        return min(known) if known else None

    def reached(self, trace: MappedTrace) -> bool:
        return self.target.block_id in trace.blocks

    def _source_is_stale(self) -> bool:
        root = self.ir.metadata.get("root")
        expected = self.ir.metadata.get("source_hash")
        if not root or not expected:
            return False
        try:
            return _source_hash(Path(str(root))) != expected
        except OSError:
            return True
