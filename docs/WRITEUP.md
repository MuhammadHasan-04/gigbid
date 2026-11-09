# The guardrail that cost more replies than our retrieval ever won

*What building GigBid, a multi-agent freelance proposal copilot, taught me about measuring safety layers.*

I spent the first part of this project the way most RAG projects go. I built nine retrieval variants, swept 64 combinations of
their switches, and picked the winner by nDCG@10. Then I looked at the end-to-end numbers and found that one regular
expression in the *safety* layer had a bigger effect on whether simulated clients replied than everything I had done to
retrieval combined. This post is about that finding, why it happened, and what it changed about how I evaluate guardrails.

## The system, briefly

GigBid is a LangGraph application. For each freelance job it runs three agents in parallel: a Job Analyst that extracts
requirements, a Risk Assessor that looks for scams and injected instructions, and a Fit Matcher that maps every requirement
to portfolio evidence. A decision node then chooses bid, watch or skip. For bids, a Pricing Strategist computes a price,
a Proposal Writer drafts a cover letter in which every experience claim must cite an evidence id, and then three checks run in order:

1. a **claim verifier** splits the draft into claims and deletes any claim the portfolio does not support;
2. a **Critic** sends the draft back to the writer (at most twice) if grounding, personalisation or length are off;
3. a **Compliance Guard** enforces the marketplace policy pack (no contact details, no guarantees, no off-platform anything).

Nothing is sent until a human approves it in the web UI. The approval is a LangGraph `interrupt()` backed by a Postgres
checkpointer, so it survives restarts.

Everything was measured against a marketplace simulator with 600 labelled development jobs across three freelancer
personas and simulated clients with hidden preferences. Each client decides whether to reply using a logistic model over what a
real client would notice: whether the proposal shows evidence for the client's must-have skills, whether it opens with a
generic line, whether the price is under the client's ceiling, and whether it claims things the freelancer can't back up. That
model is a proxy, and I'll come back to what that means. But it is a fixed, repeatable proxy, which is what you want when
comparing designs.

An important caveat: the numbers in this post come from GigBid's deterministic rule-based profile, which every agent has
as a fallback. That profile let me run every experiment end to end without paying for an API, and it makes runs reproducible
to the last decimal. The model-backed profile runs the same commands.

## Retrieval: real gains, small in the end

The portfolio corpus is deliberately hostile to naive RAG. Each past project is described three ways: a business-language
case study where half the skills appear only as paraphrases ("a background task queue" instead of Celery), a technical
README, and a terse CV line. Some skills appear only in a repo's code, never in its README.

The baseline (V0: fixed 500-character chunks, cosine similarity against the whole job post) scored nDCG@10 0.8333 on the
384 dev jobs that have gold evidence. My pre-registered hypothesis was that requirement decomposition plus hybrid
BM25 + dense retrieval would raise Recall@5 by at least five points. It didn't. On their own, decomposition (V1) and
hybrid retrieval (V2) slightly *lowered* Recall@5 (0.7488 and 0.7296 vs 0.7583). The gains came from combinations. A
sweep over 64 configurations, ranked by nDCG@10 as declared before running, picked decomposition + hybrid + a
contextual header on each chunk + structure-aware chunking: nDCG@10 0.8799 on dev and 0.8634 vs 0.8394 on the held-out
set. The ablation said the contextual header and structural chunking carried most of that. Multi-vector aggregation,
which sounds like exactly the right tool for "the repo looks irrelevant from its README", hurt when combined with the rest.

So retrieval improved, measurably and on held-out data. Then I ran the whole pipeline, drafts scored by the
simulated clients, once per retrieval variant. Simulated reply rates landed between 0.83 and 0.88 across variants. They
roughly followed nDCG, but the spread was about five points.

## The finding: the verifier was deleting the openings

Before tuning the writer, I ran a failure analysis that grouped every dev job where the system was wrong into a taxonomy:
wrong skip, wrong bid, mispriced, missed evidence, unsupported claim removed, and so on. One bucket stood out:
**107 sentences removed by the claim verifier, 94 of which began with "For your…"**.

That sentence was the writer's opening, the one that names the client's problem: *"For your recommendation engine for a
fintech platform, the core of the work is getting recommendation systems right for a fintech team, so here is the closest
match from my portfolio."* It doesn't claim experience. It frames the problem. But the verifier's claim detector used
a reasonable-sounding rule, "a sentence that mentions a skill and contains *I* or *my* is a claim", and *my portfolio*
plus *recommendation systems* matched it. The verifier then tried to find one evidence item containing every entity in
the sentence, failed, and deleted it as unsupported.

Look at what that does downstream. The opening is where the proposal shows it has read the job. Remove it and the draft
starts with a citation-heavy sentence about a past project. That is grounded, but it's exactly the shape of a templated
proposal. The Critic then saw a lower personalisation score and sometimes sent the draft back for a revision that the
same verifier would cut again.

The fix was one rule. A skill mention with a first-person pronoun now counts as a claim only if the sentence asserts past
work (a past-tense verb attached to *I* or *my*), and "is getting X right" phrasing is excluded. The effect, on the same 600
jobs with everything else unchanged:

| | Unsupported claims removed per proposal | Simulated reply rate |
|---|---|---|
| verifier before the fix | 0.4612 | 0.8362 |
| verifier after the fix | 0.056 | 0.8793 |

That 4.3-point gain from one regular expression is larger than the difference between the naive retriever and the
sweep-selected one in the end-to-end runs. The unsupported-claim metric dropped by 88%, and almost none of that was
real fabrication. It was the verifier's false positives counted as if they were the writer's lies.

## Why this matters beyond my project

**A guardrail's false-positive rate is a product metric, not just a safety metric.** It's tempting to treat
"unsupported claims removed" as purely good: every removal is a lie prevented. But the metric can't tell a removed
fabrication from a removed framing sentence. If you only report "unsupported claims before → after verification", a
verifier that deletes everything scores perfectly. I now report removals alongside a sample of what was removed, and the
failure analysis keeps a copy of the pre-fix results (`pipeline_heuristic_dev_before_verifier_fix.json`) so the comparison
can be checked.

**Measure the stack, not the component.** Retrieval metrics are clean, cheap and satisfying to optimise. But in this
pipeline retrieval feeds a writer, whose output goes through a verifier, a critic and a compliance pass before anything
is scored. Each layer can absorb or erase the improvement below it. The component metric told me retrieval had improved,
and it had. Only the end-to-end run showed that a later layer was throwing away more value than retrieval added.

**Safety layers interact with each other.** The verifier deleted the opening, the Critic penalised the result for being
less personal, and the writer revised a draft the verifier would trim again. None of these components was wrong in isolation.
The loop was. I found this through the failure taxonomy, not through any per-component test.

## The same lesson, twice more

Two smaller bugs had the same shape: a guardrail quietly removing value nobody was measuring.

The Compliance Guard's phone-number pattern (`\+?\d[\d\s-]{8,}\d`) also matched ISO timestamps. When a client asked
for a call, the Client Liaison drafted a reply offering three calendar slots ("2026-11-10 10:00…"), and Compliance
deleted the sentence with the slots as an off-platform contact attempt. The reply still read fine, and that's the problem:
it was polite, compliant and useless. It's now a regression test.

In testing, the Marketplace MCP server's idempotency store (the layer that guarantees a retried submission never
submits twice) outlived the simulator's state between runs. A retried call with an old key replayed a stored result
pointing at a proposal that no longer existed. Exactly-once was working as designed. The lifecycle of the
deduplication record didn't match the lifecycle of the thing it deduplicated.

## What I would tell someone building one of these

* Keep a failure taxonomy from day one, and read examples from every bucket, not just the counts.
* For every guardrail, report what it removed, with samples, next to how much it removed.
* Before tuning a component, run the full pipeline with that component swapped for its baseline. If the end-to-end metric
  barely moves, the bottleneck is somewhere else.
* Pre-register the primary metric for a sweep. I did, and I kept a winner whose Recall@5 was lower than the runner-up's
  because nDCG@10 was the declared metric. The difference between them was within noise.

## Limits

The clients are simulated, and I wrote both the simulator and the system. A real client might not care whether a
proposal opens with their problem, though every freelancer I asked says they do. The results in this post come from the
rule-based profile. A language-model writer might produce openings the verifier handles differently. The pattern I
would bet on transferring is not the 4.3 points. It's that a precision problem in a safety layer can quietly cost more
than the feature work you're optimising, and that you'll only see it by measuring the whole pipeline and reading what each
layer threw away.

*Code, results files and traces: the GigBid repository (`evals/results/`, `docs/traces/`).*
