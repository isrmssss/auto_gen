from openrd.core.context import Context
from openrd.core.loader import catalog, load_into
from openrd.core.profile import load_profile, profiles_dir


def test_catalog_has_core_plugins():
    ids = set(catalog())
    for needed in (
        "llm.openai_compat",
        "memory.journal",
        "rnd.orchestrator",
        "safety.policy",
        "search.arxiv",
        "sandbox.docker",
    ):
        assert needed in ids


def test_default_profile_lists_known_plugins():
    profile = load_profile(profiles_dir() / "default.yaml")
    cat = catalog()
    missing = [p for p in profile.bundles if p not in cat]
    assert missing == []


def test_context_provide_and_unload():
    ctx = Context()
    ctx.provide("x", 1)
    assert ctx.require("x") == 1
    called = []
    ctx.on("ping", lambda p: called.append(p["n"]))
    ctx.emit_sync("ping", {"n": 2})
    assert called == [2]
    ctx.unload()
    assert not ctx.has("x")


def test_load_profile_into_context():
    ctx = Context()
    load_into(ctx, load_profile(profiles_dir() / "default.yaml"))
    assert ctx.has("llm")
    assert ctx.has("safety")
    assert ctx.has("compiler")
    assert ctx.has("orchestrator")
    ctx.unload()
