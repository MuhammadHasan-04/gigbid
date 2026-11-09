# ADR 0004: Every node has a deterministic heuristic, and it is a profile, not a hidden default
**Context:** "run end to end without paying for an API", hosts without GPUs, and provider outages.
**Decision:** each node passes a rule-based fallback to `llm.structured`. The `heuristic` profile uses only those, and other profiles fall back to them last. Every trace span records the provider, so heuristic output is never presented as model output.
**Consequences:** CI and evals run offline and deterministically. The cost is maintaining two implementations per node, and heuristic results must be labelled as such.
