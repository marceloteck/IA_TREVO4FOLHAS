from __future__ import annotations


def get_validation_windows(concurso_ref: int, cfg: dict) -> dict:
    train_w = max(10, int(cfg.get("train_window", 120)))
    valid_w = max(10, int(cfg.get("valid_window", 120)))
    gap = max(0, int(cfg.get("gap", 0)))

    train_end = int(concurso_ref)
    train_start = max(1, train_end - train_w + 1)

    valid_end = max(1, train_start - gap - 1)
    valid_start = max(1, valid_end - valid_w + 1)

    return {
        "window_train": [int(train_start), int(train_end)],
        "window_valid": [int(valid_start), int(valid_end)],
    }
