# Signature extension: X2 Proposal experiments

**What.** Two proposal strategies run as an A/B test in GigSim:
* **A, evidence-first** (`agent/prompts/writer.md`): open with the client's problem, then 2–3 cited projects, a plan, the price and a question.
* **B, question-first and short** (`agent/prompts/writer_b.md`): open with one diagnostic question, then one cited project, one plan line and the price.

**How it's wired.** `experiments.proposal_ab` in config enables deterministic assignment by `sha256(job_id)` (`share_b`). The
strategy is stored on the draft (`ProposalDraft.strategy`), so outcomes in analytics and outcome memory can be split by arm.

**How it's measured.** `python -m evals.runners.ab_test` drafts *both* arms for every dev job the graph would bid on (a paired
design, so the client and job are held constant), scores each with GigSim's deterministic simulated clients, and reports reply and
hire rates, McNemar's exact test on the discordant pairs, and a two-proportion z-test.

**Result (heuristic profile, `evals/results/ab_test_heuristic.json`).** 234 paired jobs. Reply rate A 0.8803 vs B 0.7607; hire rate A 0.406 vs B 0.3803. Discordant pairs: A-only 46 vs B-only 18. McNemar exact p = 0.0006 (two-proportion z = 3.373, p = 0.0007), so A is significantly better. Shorter
proposals lose because B cites only one project, so a client's second must-have skill is left without evidence more often.
The simulated client rewards "must-have evidenced" more than it penalises length. **Caveat:** the client model is a
designed proxy, so this tells us what our simulated clients prefer. A real-market test would need X6 (live mode).

A model-profile rerun will be added to `ab_test_open.json`.
