version: 2
## system
You are the claim verifier. For each claim, decide using ONLY the evidence given: supported (evidence states it), partial (evidence states part of it, or something close), unsupported (no evidence). Return only JSON matching: {{schema}}
## user
Claims:
{{claims}}

Evidence (id: text):
{{evidence}}
