from collections import Counter
import random
import time

from training.brains._utils import weighted_sample_without_replacement


def test_weighted_sample_respects_weight_keys_only():
    weights = {2: 1.0, 4: 1.0, 6: 1.0}
    picks = weighted_sample_without_replacement(weights, 3)

    assert len(picks) == 3
    assert len(set(picks)) == 3
    assert set(picks).issubset(set(weights.keys()))


def test_weighted_sample_caps_when_k_exceeds_pool_size():
    weights = {1: 1.0, 3: 1.0}
    picks = weighted_sample_without_replacement(weights, 10)

    assert sorted(picks) == [1, 3]


def test_weighted_sample_smoke_distribution_bias():
    weights = {1: 10.0, 2: 1.0, 3: 1.0, 4: 1.0}
    counts = Counter()
    for _ in range(400):
        picked = weighted_sample_without_replacement(weights, 2)
        assert len(picked) == len(set(picked))
        for item in picked:
            counts[item] += 1

    assert counts[1] > counts[2]
    assert counts[1] > counts[3]
    assert counts[1] > counts[4]


def test_weighted_sample_excludes_zero_or_negative_weights():
    rng = random.Random(123)
    picks = weighted_sample_without_replacement({1: 0.0, 2: -1.0, 3: 0.0, 4: 2.0}, 3, rng=rng)
    assert picks == [4]


def test_weighted_sample_returns_empty_when_no_positive_weight():
    picks = weighted_sample_without_replacement({1: 0.0, 2: -2.0}, 2, rng=random.Random(9))
    assert picks == []


def test_weighted_sample_large_n_perf_smoke():
    weights = {i: float((i % 17) + 1) for i in range(1, 50_001)}
    t0 = time.perf_counter()
    picks = weighted_sample_without_replacement(weights, 100, rng=random.Random(999))
    dt = time.perf_counter() - t0

    assert len(picks) == 100
    assert len(set(picks)) == 100
    assert dt < 2.5
