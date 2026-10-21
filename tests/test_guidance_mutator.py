import random

from stateforge.fuzzing.guidance.mutator import BasicMutator


def test_parent_data_is_never_modified():
    parent = b"abcdef"
    mutator = BasicMutator(random_seed=1)
    for _ in range(100):
        mutator.mutate(parent, max_size=64, other=b"xyz")
    assert parent == b"abcdef"


def test_output_respects_maximum_size():
    mutator = BasicMutator(random_seed=2)
    for max_size in (0, 1, 2, 5, 16):
        for size in (0, 1, 3, 20):
            data = bytes(range(size))
            for _ in range(30):
                out = mutator.mutate(data, max_size=max_size, other=b"donor")
                assert len(out) <= max_size
                assert isinstance(out, bytes)


def test_empty_inputs_are_supported():
    mutator = BasicMutator(random_seed=3)
    outputs = [mutator.mutate(b"", max_size=8) for _ in range(50)]
    assert all(1 <= len(item) <= 8 for item in outputs)
    assert all(isinstance(item, bytes) for item in outputs)
    assert mutator.mutate(b"", max_size=0) == b""


def test_fixed_random_seed_reproduces_mutations():
    first = BasicMutator(random_seed=11)
    second = BasicMutator(random_seed=11)
    data = b"seed-data"
    for _ in range(200):
        assert (first.mutate(data, max_size=32, other=b"donor")
                == second.mutate(data, max_size=32, other=b"donor"))


def test_mutation_changes_the_input():
    mutator = BasicMutator(random_seed=4)
    for size in (1, 2, 8):
        data = bytes(range(size))
        for _ in range(100):
            assert mutator.mutate(data, max_size=16, other=b"ZZ") != data


def test_mutation_growth_is_bounded():
    mutator = BasicMutator(random_seed=5)
    data = b"abc"
    for _ in range(500):
        data = mutator.mutate(data, max_size=12, other=b"abcdefghijkl")
        assert len(data) <= 12


def test_splice_accepts_a_donor_seed():
    mutator = BasicMutator(random_seed=6)
    outputs = {
        mutator.mutate(b"AAAA", max_size=16, other=b"BBBB")
        for _ in range(100)
    }
    assert len(outputs) > 1
    assert any(b"B" in item for item in outputs)


def test_independent_random_generators_are_supported():
    mutator = BasicMutator(random_seed=0, rng=random.Random(9))
    assert mutator.mutate(b"abc", max_size=8) != b"abc"
