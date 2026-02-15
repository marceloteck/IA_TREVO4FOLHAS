from training.backtest.backtest_smart_engine import _normalize_resume_state


def test_resume_rebase_when_step_and_concurso_inconsistent():
    trainable = list(range(100, 141))
    state, reason, old_step, old_ref = _normalize_resume_state(
        {"step": 2600, "concurso_ref": 131}, trainable, done=0
    )

    assert reason == "rebase"
    assert old_step == 2600
    assert old_ref == 131
    assert state["concurso_ref"] == 131
    assert state["step_global"] == trainable.index(131) + 1


def test_resume_reset_when_concurso_ref_out_of_range():
    trainable = list(range(10, 21))
    state, reason, _, _ = _normalize_resume_state({"step": 4, "concurso_ref": 2}, trainable, done=0)

    assert reason == "reset"
    assert state["concurso_ref"] == 20
    assert state["step_global"] == len(trainable)
