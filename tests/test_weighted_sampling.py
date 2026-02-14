from training.brains._utils import weighted_sample_without_replacement


def test_weighted_sample_respects_weight_keys_only():
    weights = {2: 1.0, 4: 1.0, 6: 1.0}
    picks = weighted_sample_without_replacement(weights, 3)

    assert len(picks) == 3
    assert set(picks).issubset(set(weights.keys()))


def test_weighted_sample_caps_when_k_exceeds_pool_size():
    weights = {1: 1.0, 3: 1.0}
    picks = weighted_sample_without_replacement(weights, 10)

    assert sorted(picks) == [1, 3]
