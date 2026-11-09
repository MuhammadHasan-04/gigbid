# Prompts

One versioned markdown file per node. Format: `version:` line, then `## system` and `## user`.
`{{var}}` placeholders are filled by `agent/llm.py::render`. Untrusted marketplace text always
arrives wrapped in `<untrusted_*>` tags by `llm.untrusted()`. CI fails if a prompt string is
found inline in Python (`tests/unit/test_repo_rules.py`).
