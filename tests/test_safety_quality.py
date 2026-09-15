from openrd.plugins.safety_policy import SafetyService
from openrd.plugins.rnd_quality_bar import QualityBar
from openrd.util.canon import canon_query, canon_url


def test_url_and_query_canon():
    a = canon_url("https://WWW.Example.com/path/?utm_source=x&b=1")
    b = canon_url("https://example.com/path?b=1")
    assert a == b
    assert canon_query("  Foo   BAR ") == "foo bar"


def test_safety_blocks_malware_and_allows_research():
    s = SafetyService()
    assert not s.check_hypothesis("exploit CVE-2024-1234 with a payload").ok
    assert s.check_hypothesis("Use BTYD features; do not implement any exploit.").ok
    code_bad = "import subprocess\nsubprocess.run(['curl','http://x'])\n"
    assert not s.check_code(code_bad).ok
    code_ok = "print('METRICS:{\"primary\": 1.0}')\n"
    assert s.check_code(code_ok).ok


def test_quality_bar_rejects_bare_bert():
    bar = QualityBar()
    assert not bar.cheap_check("bert", "just bert")["ok"]
    idea = (
        "Baseline is log1p LightGBM. Trigger: mid-band underprediction. "
        "Action: add a recency-decayed RFM kNN prior and keep the LGB stack frozen. "
        "Expected: RMSLE drop on mid-activity users without touching zero-class."
    )
    assert bar.cheap_check("RFM kNN prior + recency decay on LGB stack", idea)["ok"]
