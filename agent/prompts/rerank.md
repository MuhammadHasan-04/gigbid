version: 1
## system
Score how well each passage proves experience relevant to the query, 0 (irrelevant) to 3 (direct proof). Return only JSON {"scores": [..one number per passage in order..]}.
## user
Query: {{query}}

{{passages}}
