"""Canonical event types. Journal is the source of truth; UI subscribes via WS."""

PROJECT_CREATED = "project.created"
PROJECT_STARTED = "project.started"
PROJECT_PAUSED = "project.paused"
PROJECT_RESUMED = "project.resumed"
PROJECT_STOPPED = "project.stopped"
PROJECT_SOLVED = "project.solved"

PHASE_ENTER = "phase.enter"
PHASE_EXIT = "phase.exit"

THOUGHT = "agent.thought"
HYPOTHESIS_PROPOSED = "hypothesis.proposed"
HYPOTHESIS_REJECTED = "hypothesis.rejected"
HYPOTHESIS_SELECTED = "hypothesis.selected"

SEARCH_QUERY = "search.query"
SEARCH_HIT = "search.hit"
SEARCH_SKIPPED = "search.skipped"
PAPER_INGESTED = "paper.ingested"

RUN_STARTED = "run.started"
RUN_FINISHED = "run.finished"
RUN_FAILED = "run.failed"
METRIC = "run.metric"

CEMETERY_ADD = "cemetery.add"
MEMORY_PATCH = "memory.patch"
BLACKBOARD_CLAIM = "blackboard.claim"
BLACKBOARD_RELEASE = "blackboard.release"

HUMAN_STEER = "human.steer"
HUMAN_QUESTION = "human.question"
HUMAN_ASK_ANSWERED = "human.ask.answered"
JOB_READY = "job.ready"
JOB_BLOCKED = "job.blocked"
FUNNEL_STEP = "funnel.step"
ROLLBACK = "project.rollback"

COST = "llm.cost"
SAFETY_BLOCK = "safety.block"
HW_PROBE = "hw.probe"

TREE_NODE = "tree.node"
