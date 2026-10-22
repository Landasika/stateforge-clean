from stateforge.fuzzing.feedback.corpus import GuidedCorpus, seed_id_for
from stateforge.fuzzing.guidance.campaign import ExecutionResult


def _result(blocks=(), edges=(), distance=None, target=False) -> ExecutionResult:
    return ExecutionResult(
        input_id="input",
        parent_id=None,
        covered_blocks=frozenset(blocks),
        covered_edges=frozenset(edges),
        distance=0 if target else distance,
        target_reached=target,
        execution_time_ms=0.0,
        error=None,
    )


def test_seed_identity_is_content_addressed():
    assert seed_id_for(b"abc") == seed_id_for(b"abc")
    assert seed_id_for(b"abc") != seed_id_for(b"abd")


def test_duplicate_inputs_do_not_create_duplicate_entries():
    corpus = GuidedCorpus()
    first = _result({"a"}, {("a", "b")}, 4)
    assert corpus.consider(b"same", first)
    second = _result({"a", "b"}, {("a", "b")}, 3)
    assert not corpus.consider(b"same", second)
    assert len(corpus) == 1
    assert "b" in corpus.covered_blocks


def test_new_block_and_edge_are_retained():
    corpus = GuidedCorpus()
    assert corpus.consider(b"a", _result({"a"}, {("a", "b")}, 5))
    assert corpus.consider(b"b", _result({"b"}, {("b", "c")}, 5))
    assert corpus.consider(b"c", _result({"a"}, set(), 5)) is False


def test_distance_improvement_is_retained():
    corpus = GuidedCorpus()
    corpus.consider(b"a", _result({"a"}, {("a", "b")}, 6))
    old_best = corpus.best_distance
    assert corpus.consider(b"b", _result({"a"}, {("a", "b")}, 3))
    assert corpus.best_distance == 3
    assert old_best == 6


def test_target_reaching_seed_is_retained():
    corpus = GuidedCorpus()
    assert corpus.consider(b"hit", _result({"target"}, set(), 0, target=True))
    assert corpus.target_reached


def test_capacity_is_enforced():
    corpus = GuidedCorpus(max_size=5)
    for index in range(40):
        block = f"b{index}"
        corpus.consider(
            bytes([index]), _result({block}, {(block, "next")}, 100 + index))
    assert len(corpus) == 5


def test_best_distance_seed_survives_pruning():
    corpus = GuidedCorpus(max_size=4)
    corpus.consider(b"far", _result({"far"}, set(), 100))
    corpus.consider(b"best", _result({"best"}, set(), 10))
    for index in range(20):
        block = f"x{index}"
        corpus.consider(bytes([index]), _result({block}, set(), 200 + index))
    assert corpus.best_distance == 10
    assert corpus.get(seed_id_for(b"best")) is not None


def test_target_seeds_survive_pruning():
    corpus = GuidedCorpus(max_size=3)
    for index in range(2):
        corpus.consider(bytes([index]), _result({f"t{index}"}, set(), 0, True))
    for index in range(20):
        corpus.consider(bytes([50 + index]), _result({f"b{index}"}, set(), 50))
    assert len(corpus) <= 3
    assert corpus.get(seed_id_for(bytes([0]))) is not None
    assert corpus.get(seed_id_for(bytes([1]))) is not None


def test_coverage_representatives_survive_pruning():
    corpus = GuidedCorpus(max_size=2)
    corpus.consider(b"near", _result({"n"}, set(), 1))
    corpus.consider(b"wide", _result({"w1", "w2", "w3", "w4"}, set(), 9))
    corpus.consider(b"middle", _result({"m"}, set(), 5))
    assert corpus.get(seed_id_for(b"wide")) is not None
    assert corpus.get(seed_id_for(b"near")) is not None
    assert len(corpus) == 2


def test_novelty_is_reported_before_consider():
    corpus = GuidedCorpus()
    corpus.consider(b"a", _result({"a"}, {("a", "b")}, 5))
    new_blocks, new_edges = corpus.novelty(
        _result({"a", "b"}, {("a", "b"), ("b", "c")}, 4))
    assert new_blocks == {"b"}
    assert new_edges == {("b", "c")}


def test_pruning_is_deterministic():
    def build():
        corpus = GuidedCorpus(max_size=6)
        for index in range(30):
            block = f"b{index % 11}"
            corpus.consider(bytes([index]), _result(
                {block}, {(block, "n")}, 30 - (index % 7)))
        return [seed.seed_id for seed in corpus.seeds]

    assert build() == build()


def test_capacity_one_with_many_targets_keeps_one_and_archives_rest():
    corpus = GuidedCorpus(max_size=1)
    for index in range(20):
        corpus.consider(bytes([index]), _result(
            {f"t{index}"}, {(f"t{index}", "next")}, 0, target=True))
    assert len(corpus) == 1
    assert len(corpus.target_archive) == 19
    assert len(corpus.seeds[0].data) == 1
    assert corpus.seeds[0].target_reached
    assert corpus.best_distance == 0
    assert all(seed.target_reached for seed in corpus.archived_targets)


def test_capacity_ten_with_many_targets_is_enforced():
    corpus = GuidedCorpus(max_size=10)
    for index in range(25):
        corpus.consider(bytes([index]), _result(
            {f"t{index}"}, {(f"t{index}", "next")}, 0, target=True))
    assert len(corpus) == 10
    assert len(corpus.target_archive) == 15
    assert len(corpus) + len(corpus.target_archive) == 25
    for index in range(25):
        seed_id = seed_id_for(bytes([index]))
        assert (corpus.get(seed_id) is not None
                or seed_id in corpus.target_archive)


def test_target_representative_prefers_new_coverage():
    corpus = GuidedCorpus(max_size=1)
    corpus.consider(b"small", _result({"a"}, set(), 0, target=True))
    corpus.consider(b"wide", _result({"b1", "b2", "b3"}, set(), 0,
                                     target=True))
    assert len(corpus) == 1
    assert corpus.seeds[0].covered_blocks == frozenset({"b1", "b2", "b3"})
    assert seed_id_for(b"small") in corpus.target_archive


def test_target_archive_does_not_affect_capacity_or_best_seed():
    corpus = GuidedCorpus(max_size=2)
    corpus.consider(b"best", _result({"best"}, set(), 5))
    for index in range(6):
        corpus.consider(bytes([index]), _result(
            {f"t{index}"}, set(), 0, target=True))
    assert len(corpus) <= 2
    assert corpus.best_distance == 0
    assert corpus.get(seed_id_for(b"best")) is None
    assert seed_id_for(b"best") not in corpus.target_archive
    assert corpus.best_seed() is not None
    assert corpus.best_seed().distance == 0


def test_capacity_one_without_target_preserves_best_distance_seed():
    corpus = GuidedCorpus(max_size=1)
    corpus.consider(b"far", _result({"far"}, set(), 90))
    corpus.consider(b"best", _result({"best"}, set(), 7))
    corpus.consider(b"other", _result({"other"}, set(), 30))
    assert len(corpus) == 1
    assert corpus.get(seed_id_for(b"best")) is not None
    assert corpus.best_distance == 7


def test_target_pruning_is_deterministic():
    def build():
        corpus = GuidedCorpus(max_size=3)
        for index in range(30):
            corpus.consider(bytes([index]), _result(
                {f"t{index % 7}"}, {(f"t{index % 7}", "next")}, 0,
                target=True))
        return ([seed.seed_id for seed in corpus.seeds],
                sorted(corpus.target_archive))

    assert build() == build()
