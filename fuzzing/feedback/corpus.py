
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from stateforge.core.ir import ProgramIR
from stateforge.runtime.mapper import MappedTrace
from stateforge.fuzzing.feedback.scorer import score_distance, score_trace


@dataclass
class CorpusEntry:
    seed: str
    score: float
    blocks: int
    edges: int
    nearest_target: int | None = None


def evaluate_seed(ir: ProgramIR, seed: str, trace: MappedTrace,
                  targets: set[str],
                  distances: dict[str, int] | None = None) -> CorpusEntry:
    if distances is None and targets:
        from stateforge.fuzzing.feedback.distance import distance_to_targets
        distances = distance_to_targets(ir, set(trace.blocks), targets)
    nearest = None
    if distances and trace.blocks:
        known = [distances[block] for block in trace.blocks if block in distances]
        nearest = min(known) if known else None
    score = (score_distance(nearest) if distances is not None
             else score_trace(ir, trace, targets))
    return CorpusEntry(seed, score, len(trace.block_hits),
                       len(trace.edge_hits), nearest)


def rank(entries: list[CorpusEntry]) -> list[CorpusEntry]:
    return sorted(entries, key=lambda e: (e.score, e.blocks, e.edges, e.seed), reverse=True)


def save(entries: list[CorpusEntry], path: str | Path) -> None:
    Path(path).write_text(json.dumps([asdict(e) for e in rank(entries)], indent=2),
                          encoding="utf-8")


def seed_id_for(data: bytes) -> str:
    return f"seed_{hashlib.sha256(data).hexdigest()[:16]}"


@dataclass
class GuidedSeed:
    seed_id: str
    data: bytes
    distance: int | None
    score: float
    covered_blocks: frozenset[str]
    covered_edges: frozenset[tuple[str, str]]
    executions_selected: int = 0
    parent_id: str | None = None
    target_reached: bool = False


class GuidedCorpus:
    def __init__(self, max_size: int = 1000):
        if max_size < 1:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self._seeds: dict[str, GuidedSeed] = {}
        self.target_archive: dict[str, GuidedSeed] = {}
        self.covered_blocks: set[str] = set()
        self.covered_edges: set[tuple[str, str]] = set()
        self.best_distance: int | None = None
        self.target_reached = False

    def __len__(self) -> int:
        return len(self._seeds)

    @property
    def seeds(self) -> list[GuidedSeed]:
        return list(self._seeds.values())

    @property
    def archived_targets(self) -> list[GuidedSeed]:
        return list(self.target_archive.values())

    def get(self, seed_id: str) -> GuidedSeed | None:
        return self._seeds.get(seed_id)

    def novelty(self, result: Any) -> tuple[set[str], set[tuple[str, str]]]:
        return (set(result.covered_blocks) - self.covered_blocks,
                set(result.covered_edges) - self.covered_edges)

    def consider(self, data: bytes, result: Any, score: float | None = None,
                 parent_id: str | None = None) -> bool:
        seed_id = seed_id_for(data)
        new_blocks, new_edges = self.novelty(result)
        reached = bool(result.target_reached)
        distance = 0 if reached else result.distance
        improves = (distance is not None
                    and (self.best_distance is None
                         or distance < self.best_distance))
        representative = (distance is not None
                          and all(seed.distance != distance
                                  for seed in self._seeds.values()))
        self.covered_blocks.update(result.covered_blocks)
        self.covered_edges.update(result.covered_edges)
        if distance is not None and (self.best_distance is None
                                     or distance < self.best_distance):
            self.best_distance = distance
        if reached:
            self.target_reached = True
        if seed_id in self._seeds or seed_id in self.target_archive:
            return False
        retain = (reached or bool(new_blocks) or bool(new_edges) or improves
                  or representative or not self._seeds)
        if not retain:
            return False
        seed = GuidedSeed(
            seed_id=seed_id,
            data=bytes(data),
            distance=distance,
            score=score if score is not None else score_distance(distance),
            covered_blocks=frozenset(result.covered_blocks),
            covered_edges=frozenset(result.covered_edges),
            parent_id=parent_id,
            target_reached=reached,
        )
        self._seeds[seed_id] = seed
        self._prune()
        return seed_id in self._seeds

    def add(self, seed: GuidedSeed) -> None:
        if seed.target_reached and seed.distance is None:
            seed.distance = 0
            seed.score = 1.0
        self._seeds[seed.seed_id] = seed
        self.covered_blocks.update(seed.covered_blocks)
        self.covered_edges.update(seed.covered_edges)
        if seed.distance is not None and (self.best_distance is None
                                          or seed.distance < self.best_distance):
            self.best_distance = seed.distance
        if seed.target_reached:
            self.target_reached = True
        self._prune()

    def remove(self, seed_id: str) -> None:
        self._seeds.pop(seed_id, None)
        self.target_archive.pop(seed_id, None)

    def best_seed(self) -> GuidedSeed | None:
        candidates = [seed for seed in self._seeds.values()
                      if seed.distance is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda seed: (seed.distance, seed.seed_id))

    def _prune(self) -> None:
        if len(self._seeds) <= self.max_size:
            self._sync_target_archive()
            return
        seeds = list(self._seeds.values())
        forced: list[str] = []
        forced.extend(self._target_representatives(seeds, self.max_size))
        best = self.best_seed()
        if best is not None and len(forced) < self.max_size:
            if best.seed_id not in forced:
                forced.append(best.seed_id)
        if len(forced) < self.max_size:
            wide = max(seeds, key=lambda seed: (
                len(seed.covered_blocks), len(seed.covered_edges), seed.seed_id))
            if wide.seed_id not in forced:
                forced.append(wide.seed_id)
        if len(forced) < self.max_size:
            broad = max(seeds, key=lambda seed: (
                len(seed.covered_edges), len(seed.covered_blocks), seed.seed_id))
            if broad.seed_id not in forced:
                forced.append(broad.seed_id)
        forced = forced[:self.max_size]
        forced_set = set(forced)
        remaining = [seed for seed_id, seed in self._seeds.items()
                     if seed_id not in forced_set]
        remaining.sort(key=self._prune_key, reverse=True)
        keep = forced + [seed.seed_id for seed in
                         remaining[:self.max_size - len(forced)]]
        keep_set = set(keep)
        removed = [seed for seed_id, seed in self._seeds.items()
                   if seed_id not in keep_set]
        for seed in removed:
            if seed.target_reached:
                self.target_archive[seed.seed_id] = seed
        self._seeds = {seed_id: seed for seed_id, seed in self._seeds.items()
                       if seed_id in keep_set}
        self._sync_target_archive()

    @staticmethod
    def _target_representatives(seeds: list[GuidedSeed],
                                limit: int) -> list[str]:
        targets = [seed for seed in seeds if seed.target_reached]
        if not targets or limit < 1:
            return []
        if len(targets) <= limit:
            return [seed.seed_id for seed in sorted(
                targets, key=lambda seed: seed.seed_id)]
        selected: list[str] = []
        remaining = list(targets)
        seen_blocks: set[str] = set()
        seen_edges: set[tuple[str, str]] = set()
        while remaining and len(selected) < limit:
            best = max(remaining, key=lambda seed: (
                len(seed.covered_blocks - seen_blocks),
                len(seed.covered_edges - seen_edges),
                len(seed.covered_blocks),
                len(seed.covered_edges),
                -seed.executions_selected,
                seed.seed_id,
            ))
            selected.append(best.seed_id)
            seen_blocks.update(best.covered_blocks)
            seen_edges.update(best.covered_edges)
            remaining.remove(best)
        return selected

    def _sync_target_archive(self) -> None:
        for seed_id in list(self.target_archive):
            if seed_id in self._seeds:
                del self.target_archive[seed_id]
        for seed_id, seed in self._seeds.items():
            if seed.target_reached:
                self.target_archive.pop(seed_id, None)

    @staticmethod
    def _prune_key(seed: GuidedSeed) -> tuple[int, int, int, int, int, str]:
        distance = seed.distance if seed.distance is not None else 10**9
        return (1 if seed.target_reached else 0, -distance,
                len(seed.covered_blocks), len(seed.covered_edges),
                -seed.executions_selected, seed.seed_id)
