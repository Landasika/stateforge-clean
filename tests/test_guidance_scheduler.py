from types import SimpleNamespace

import pytest

from stateforge.fuzzing.feedback.corpus import GuidedCorpus, GuidedSeed
from stateforge.fuzzing.feedback.scorer import score_distance
from stateforge.fuzzing.guidance.scheduler import (
    EmptyCorpusError,
    GuidedScheduler,
    SchedulerError,
    UniformScheduler,
)


def _seed(name: str, distance: int | None, blocks=()) -> GuidedSeed:
    return GuidedSeed(
        seed_id=f"seed_{name}",
        data=name.encode(),
        distance=distance,
        score=score_distance(distance),
        covered_blocks=frozenset(blocks),
        covered_edges=frozenset(),
    )


def _corpus(*seeds: GuidedSeed, max_size: int = 100) -> GuidedCorpus:
    corpus = GuidedCorpus(max_size)
    for seed in seeds:
        corpus.add(seed)
    return corpus


def test_nearer_seed_has_higher_exploitation_probability():
    near = _seed("near", 1)
    far = _seed("far", 9)
    corpus = _corpus(near, far)
    scheduler = GuidedScheduler(epsilon=0.0, random_seed=7)
    probabilities = scheduler.selection_probabilities(corpus)
    assert probabilities[near.seed_id] > probabilities[far.seed_id]
    assert sum(probabilities.values()) == pytest.approx(1.0)


def test_unknown_distance_has_zero_directed_priority():
    near = _seed("near", 0)
    unknown = _seed("unknown", None)
    corpus = _corpus(near, unknown)
    scheduler = GuidedScheduler(epsilon=0.0, random_seed=1)
    probabilities = scheduler.selection_probabilities(corpus)
    assert scheduler.priority(unknown) == 0.0
    assert probabilities[unknown.seed_id] == 0.0
    assert probabilities[near.seed_id] == 1.0


def test_all_unknown_distances_fall_back_to_uniform():
    corpus = _corpus(_seed("a", None), _seed("b", None))
    scheduler = GuidedScheduler(epsilon=0.0, random_seed=1)
    probabilities = scheduler.selection_probabilities(corpus)
    assert all(value == pytest.approx(0.5) for value in probabilities.values())


def test_exploitation_favours_near_seed_over_many_trials():
    near = _seed("near", 1)
    far = _seed("far", 20)
    corpus = _corpus(near, far)
    scheduler = GuidedScheduler(epsilon=0.0, random_seed=11)
    hits = {near.seed_id: 0, far.seed_id: 0}
    for _ in range(300):
        for seed in corpus.seeds:
            seed.executions_selected = 0
        chosen = scheduler.select(corpus)
        hits[chosen.seed_id] += 1
    assert hits[near.seed_id] > hits[far.seed_id]


def test_exploration_remains_possible():
    near = _seed("near", 0)
    far = _seed("far", 1000)
    corpus = _corpus(near, far)
    scheduler = GuidedScheduler(epsilon=1.0, random_seed=3)
    chosen = {scheduler.select(corpus).seed_id for _ in range(80)}
    assert chosen == {near.seed_id, far.seed_id}


def test_feedback_update_changes_subsequent_priority():
    first = _seed("first", 5)
    second = _seed("second", 5)
    corpus = _corpus(first, second)
    scheduler = GuidedScheduler(epsilon=0.0, random_seed=2)
    before = scheduler.selection_probabilities(corpus)
    scheduler.update(first, SimpleNamespace(distance=0, target_reached=True))
    after = scheduler.selection_probabilities(corpus)
    assert after[first.seed_id] > before[first.seed_id]
    assert after[first.seed_id] > after[second.seed_id]
    assert scheduler.last_child_distance(first.seed_id) == 0


def test_energy_is_bounded_and_distance_sensitive():
    near = _seed("near", 0)
    far = _seed("far", 100)
    scheduler = GuidedScheduler(epsilon=0.2, random_seed=0,
                                min_energy=2, max_energy=8)
    assert scheduler.allocate_energy(near) == 8
    assert scheduler.allocate_energy(far) == 2
    for seed in (near, far):
        energy = scheduler.allocate_energy(seed)
        assert 2 <= energy <= 8


def test_fixed_random_seed_reproduces_schedule():
    def run():
        corpus = _corpus(_seed("a", 2), _seed("b", 5), _seed("c", 9))
        scheduler = GuidedScheduler(epsilon=0.3, random_seed=123)
        sequence = []
        for _ in range(40):
            selected = scheduler.select(corpus)
            sequence.append(selected.seed_id)
            scheduler.update(selected, SimpleNamespace(
                distance=max(0, (selected.distance or 0) - 1),
                target_reached=False))
        return sequence

    assert run() == run()


def test_selected_seed_is_counted_for_future_penalty():
    seed = _seed("only", 3)
    corpus = _corpus(seed)
    scheduler = GuidedScheduler(epsilon=0.0, random_seed=0)
    scheduler.select(corpus)
    assert seed.executions_selected == 1


def test_empty_corpus_is_rejected():
    scheduler = GuidedScheduler(epsilon=0.2, random_seed=0)
    with pytest.raises(EmptyCorpusError):
        scheduler.select(GuidedCorpus())
    with pytest.raises(EmptyCorpusError):
        scheduler.selection_probabilities(GuidedCorpus())


def test_invalid_scheduler_configuration_is_rejected():
    with pytest.raises(SchedulerError):
        GuidedScheduler(epsilon=-0.1)
    with pytest.raises(SchedulerError):
        GuidedScheduler(epsilon=1.1)
    with pytest.raises(SchedulerError):
        GuidedScheduler(min_energy=2, max_energy=1)
    with pytest.raises(SchedulerError):
        UniformScheduler(energy=0)


def test_uniform_scheduler_has_no_distance_dependence():
    corpus = _corpus(_seed("near", 0), _seed("far", 99))
    scheduler = UniformScheduler(random_seed=5, energy=1)
    probabilities = scheduler.selection_probabilities(corpus)
    assert all(value == pytest.approx(0.5) for value in probabilities.values())
    assert scheduler.allocate_energy(corpus.seeds[0]) == 1
