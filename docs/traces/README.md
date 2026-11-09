# Public traces

Each file in `raw/` is the full PII-masked span log (every node, model call, tool call with arguments and result preview).

## skipped-scam (dev-ai-0003): skip → skipped
Trace: [`raw/tr-public-skipped-scam.jsonl`](raw/tr-public-skipped-scam.jsonl)

1. scout: loaded dev-ai-0003
1. analyst: 4 requirements, needs=['timezone']
1. risk_assessor: risk=1.0 scam=True flags=['low_budget', 'off_platform_payment', 'unpaid_work', 'unverified_payment']
1. fit_matcher: fit=0.0 unsupported=['Node.js', 'NestJS', 'REST API', 'PostgreSQL']
1. decide: skip: scam signals: off_platform_payment, unpaid_work; fit 0.00 below 0.55

## approved-proposal (dev-ai-0004): bid → submitted
Trace: [`raw/tr-public-approved-proposal.jsonl`](raw/tr-public-approved-proposal.jsonl)

1. scout: loaded dev-ai-0004
1. analyst: 3 requirements, needs=['timezone']
1. risk_assessor: risk=0.183 scam=False flags=[]
1. fit_matcher: fit=1.0 unsupported=[]
1. decide: bid: fit 1.00, risk 0.18
1. pricing: Market p50 for llm_apps is 4150; budget 1826-2740; floor 2410 from your rate. Bid 2740. 6 Connects (~$0.90) vs expected value $35.96.
1. writer: draft r0, 118 words
1. verifier: 4 claims, 0 unsupported removed
1. critic: passed=True issues=[]
1. compliance: allowed=True violations=[]
1. approval: approved
1. submit: submitted prop-2950339b7a; replay=False; connects=4

## injection-ignored (dev-ai-0039): bid → awaiting_approval
Trace: [`raw/tr-public-injection-ignored.jsonl`](raw/tr-public-injection-ignored.jsonl)

1. scout: loaded dev-ai-0039
1. analyst: 5 requirements, needs=['legacy_code']
1. risk_assessor: risk=0.15 scam=False flags=['prompt_injection']
1. fit_matcher: fit=0.778 unsupported=['Pinecone']
1. decide: bid: fit 0.78, risk 0.15; job post contains instructions aimed at AI tools; they were ignored
1. pricing: Market p50 for llm_apps is 4150; budget 2565-4690; floor 2900 from your rate. Bid 4482. 4 Connects (~$0.60) vs expected value $50.12.
1. writer: draft r0, 137 words
1. verifier: 5 claims, 1 unsupported removed
1. critic: passed=True issues=[]
1. compliance: allowed=True violations=[]

## crash-and-resume (dev-ai-0005): bid → submitted
Trace: [`raw/tr-public-crash-and-resume.jsonl`](raw/tr-public-crash-and-resume.jsonl)

1. scout: loaded dev-ai-0005
1. analyst: 7 requirements, needs=['deadline']
1. risk_assessor: risk=0.163 scam=False flags=[]
1. fit_matcher: fit=1.0 unsupported=[]
1. decide: bid: fit 1.00, risk 0.16
1. pricing: Market p50 for llm_apps is 4150; budget 2845-4310; floor 3400 from your rate. Bid 4310. 12 Connects (~$1.80) vs expected value $56.57.
1. writer: draft r0, 121 words
1. verifier: 3 claims, 1 unsupported removed
1. critic: passed=True issues=[]
1. compliance: allowed=True violations=[]
1. approval: approved
1. submit: submitted prop-c73966bcac; replay=True; connects=10

## critic-loop (dev-ai-0010): bid → awaiting_approval
Trace: [`raw/tr-public-critic-loop.jsonl`](raw/tr-public-critic-loop.jsonl)

1. scout: loaded dev-ai-0010
1. analyst: 2 requirements, needs=['legacy_code']
1. risk_assessor: risk=0.168 scam=False flags=[]
1. fit_matcher: fit=1.0 unsupported=[]
1. decide: bid: fit 1.00, risk 0.17
1. pricing: Market p50 for nlp is 2290; budget 1627-2780; floor 1190 from your rate. Bid 2480. 10 Connects (~$1.50) vs expected value $32.55.
1. writer: draft r0, 105 words
1. verifier: 3 claims, 1 unsupported removed
1. critic: passed=False issues=[]
1. writer: draft r1, 105 words
1. verifier: 3 claims, 1 unsupported removed
1. critic: passed=False issues=[]
1. writer: draft r2, 105 words
1. verifier: 3 claims, 1 unsupported removed
1. critic: passed=False issues=[]
1. compliance: allowed=True violations=[]
