# ADR 0005: Fit Matcher runs in parallel with the Analyst, using its own cheap requirement extraction
**Context:** R3 requires Analyst, Risk and Fit in parallel, but Fit needs requirements.
**Decision:** Fit extracts requirements with the canonical-name rule extractor, and `decide` tops up requirements the Analyst found that Fit missed.
**Consequences:** wall-clock parallelism is kept. On jobs where the post uses paraphrases, `decide` makes a few extra retrieval calls.
