"""In-process sub agents: extra hands for the main Agent, with no identity.

A sub agent has no IM account, no workspace and no memory of its own. It exists
for the length of one task and reports back to the Agent that spawned it. Peer
agents, which do have their own workspace and identity, are a separate thing:
see agent/registry.py.
"""

from agent.subagent.runner import (
    SubagentSettings,
    SubagentTask,
    current_depth,
    run_tasks,
)
from agent.subagent.templates import (
    BLOCKED_TOOLS,
    BUILTIN_TEMPLATES,
    DEFAULT_TEMPLATE_NAME,
    SubagentTemplate,
    load_templates,
    parse_template,
)

__all__ = [
    "BLOCKED_TOOLS",
    "BUILTIN_TEMPLATES",
    "DEFAULT_TEMPLATE_NAME",
    "SubagentSettings",
    "SubagentTask",
    "SubagentTemplate",
    "current_depth",
    "load_templates",
    "parse_template",
    "run_tasks",
]
