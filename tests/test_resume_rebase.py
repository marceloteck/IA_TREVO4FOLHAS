from training.backtest.backtest_smart_engine import _normalize_resume_state


def test_resume_repair_when_step_and_concurso_inconsistent():
    trainable = list(range(100, 141))
    state, reason, old_step, old_ref = _normalize_resume_state(
        {"step": 2, "concurso_ref": 131, "schema_version": 2}, trainable, done=0
    )

    assert reason == "repair"
    assert old_step == 2
    assert old_ref == 131
    assert state["concurso_ref"] == 131
    assert state["step_global"] == trainable.index(131) + 1


def test_resume_checkpoint_inconsistent_when_concurso_ref_out_of_range():
    trainable = list(range(10, 21))
    state, reason, _, _ = _normalize_resume_state({"step": 4, "concurso_ref": 2, "schema_version": 2}, trainable, done=0)

    assert reason == "checkpoint_inconsistent"
    assert state["concurso_ref"] == 10
    assert state["step_global"] == 4


def test_resume_rebase_only_on_schema_migration():
    trainable = list(range(10, 21))
    state, reason, _, _ = _normalize_resume_state({"step": 1, "concurso_ref": 20, "schema_version": 1}, trainable, done=0)

    assert reason == "rebase"
    assert state["concurso_ref"] == 20
    assert state["step_global"] == len(trainable)
