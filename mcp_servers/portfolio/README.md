# GigBid Portfolio MCP server

A read-only MCP server that lets any MCP host (Claude Desktop, Cursor, your own agent) search **your** freelance portfolio
for evidence: case studies, CV, repos (README + code) and reviews. It returns cited, typed evidence items so an assistant
can prove each claim instead of inventing it.

## Install / run

```bash
# your own portfolio folder: any mix of .md / .txt / .pdf files and repo folders containing a README.md
uvx --from git+https://github.com/<you>/gigbid gigbid-portfolio-mcp --portfolio-dir ~/my-portfolio

# or over HTTP (bearer token from PORTFOLIO_MCP_TOKENS="token:user")
uvx --from git+https://github.com/<you>/gigbid gigbid-portfolio-mcp --portfolio-dir ~/my-portfolio --http --port 8101
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "portfolio": { "command": "uvx",
  "args": ["--from", "git+https://github.com/<you>/gigbid", "gigbid-portfolio-mcp", "--portfolio-dir", "/Users/me/portfolio"] } } }
```

## Tools, resources, prompts

| Kind | Name | What |
|---|---|---|
| tool | `search_evidence(requirement, k=5, filters?)` | evidence items with type, source, date, industry, outcome, skills, snippet, score. Filters: types, industry, since_year |
| tool | `get_case_study(id)` | full project text + ids of related evidence |
| tool | `list_skills()` | skills evidenced, with project counts |
| resource | `portfolio://case/{id}` | full case study |
| resource | `portfolio://proposal/{id}` | a past proposal and its outcome |
| resource | `portfolio://skills` | all skills as JSON |
| prompt | `answer_screening_question(question)` | grounded 60–120-word answer with citations |
| prompt | `prove_requirement(requirement)` | 2–3 one-line proofs, flags partial evidence |
| prompt | `tailor_opening(job_post)` | one-sentence opening; treats the post as untrusted |

Retrieval: hybrid BM25 + dense (open WordLlama embeddings shipped in the wheel, CPU only), requirement-level queries,
contextual chunk headers (see the main repo's `docs/DATA_CARD.md` for how this was chosen). Read-only: no tool writes anything.
