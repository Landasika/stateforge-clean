
from __future__ import annotations

import math
import random
from typing import Any

from stateforge.fuzzing.feedback.corpus import GuidedCorpus, GuidedSeed


class EmptyCorpusError(ValueError):
    pass


class SchedulerError(ValueError):
    pass


class GuidedScheduler:
    def __init__(self, epsilon: float = 0.20, random_seed: int = 0,
                 min_energy: int = 1, max_energy: int = 32,
                 rng: random.Random | None = None):
        if not 0.0 <= epsilon <= 1.0:
            raise SchedulerError("epsilon must be in [0, 1]")
        if min_energy < 1 or max_energy < min_energy:
            raise SchedulerError("invalid energy bounds")
        self.epsilon = epsilon
        self.random_seed = random_seed
        self.min_energy = min_energy
        self.max_energy = max_energy
        self._rng = rng if rng is not None else random.Random(random_seed)
        self._improvements: dict[str, int] = {}
        self._last_child_distance: dict[str, int | None] = {}
        self._best_distance: int | None = None

    @staticmethod
    def priority(seed: GuidedSeed) -> float:
        if seed.target_reached:
            return 1.0
        if seed.distance is None:
            return 0.0
        return 1.0 / (1.0 + seed.distance)

    def selection_weight(self, seed: GuidedSeed) -> float:
        base = self.priority(seed)
        if base <= 0.0:
            return 0.0
        bonus = 1.0 + 0.5 * self._improvements.get(seed.seed_id, 0)
        penalty = 1.0 + 0.1 * math.log1p(seed.executions_selected)
        return base * bonus / penalty

    def _refresh_best(self, corpus: GuidedCorpus) -> None:
        best = min((seed.distance for seed in corpus.seeds
                    if seed.distance is not None), default=None)
        if best is not None and (self._best_distance is None
                                 or best < self._best_distance):
            self._best_distance = best

    def selection_probabilities(self, corpus: GuidedCorpus) -> dict[str, float]:
        seeds = corpus.seeds
        if not seeds:
            raise EmptyCorpusError("cannot select from an empty corpus")
        self._refresh_best(corpus)
        weights = {seed.seed_id: self.selection_weight(seed) for seed in seeds}
        total = sum(weights.values())
        if total <= 0.0:
            uniform = 1.0 / len(seeds)
            return {seed.seed_id: uniform for seed in seeds}
        return {seed_id: weight / total for seed_id, weight in weights.items()}

    def select(self, corpus: GuidedCorpus) -> GuidedSeed:
        seeds = corpus.seeds
        if not seeds:
            raise EmptyCorpusError("cannot select from an empty corpus")
        self._refresh_best(corpus)
        if self._rng.random() < self.epsilon:
            selected = self._rng.choice(seeds)
        else:
            probabilities = self.selection_probabilities(corpus)
            draw = self._rng.random()
            cumulative = 0.0
            selected = seeds[-1]
            for seed in seeds:
                cumulative += probabilities[seed.seed_id]
                if draw <= cumulative:
                    selected = seed
                    break
        selected.executions_selected += 1
        return selected

    def allocate_energy(self, seed: GuidedSeed) -> int:
        span = self.max_energy - self.min_energy
        energy = self.min_energy + round(span * self.priority(seed))
        return max(self.min_energy, min(self.max_energy, energy))

    def update(self, seed: GuidedSeed, result: Any) -> None:
        distance = getattr(result, "distance", None)
        reached = bool(getattr(result, "target_reached", False))
        if reached:
            distance = 0
        self._last_child_distance[seed.seed_id] = distance
        if distance is not None and (self._best_distance is None
                                     or distance < self._best_distance):
            self._best_distance = distance
            self._improvements[seed.seed_id] = (
                self._improvements.get(seed.seed_id, 0) + 1)

    def last_child_distance(self, seed_id: str) -> int | None:
        return self._last_child_distance.get(seed_id)


class UniformScheduler:
    def __init__(self, random_seed: int = 0, energy: int = 1,
                 rng: random.Random | None = None):
        if energy < 1:
            raise SchedulerError("energy must be positive")
        self.random_seed = random_seed
        self.energy = energy
        self._rng = rng if rng is not None else random.Random(random_seed)

    def select(self, corpus: GuidedCorpus) -> GuidedSeed:
        seeds = corpus.seeds
        if not seeds:
            raise EmptyCorpusError("cannot select from an empty corpus")
        selected = self._rng.choice(seeds)
        selected.executions_selected += 1
        return selected

    def allocate_energy(self, seed: GuidedSeed) -> int:
        return self.energy

    def update(self, seed: GuidedSeed, result: Any) -> None:
        return None

    def selection_probabilities(self, corpus: GuidedCorpus) -> dict[str, float]:
        seeds = corpus.seeds
        if not seeds:
            raise EmptyCorpusError("cannot select from an empty corpus")
        uniform = 1.0 / len(seeds)
        return {seed.seed_id: uniform for seed in seeds}
