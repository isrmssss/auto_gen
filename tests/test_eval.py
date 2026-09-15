from openrd.eval.harness import run_suite


def test_smoke_eval_suite():
    assert run_suite("smoke") == 0
