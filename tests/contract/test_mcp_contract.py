"""Contract tests through a real in-memory MCP client session (protocol level), plus schema snapshots
that fail CI when a tool signature changes unintentionally. Update snapshots deliberately with
UPDATE_SNAPSHOTS=1 pytest tests/contract."""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from tests.fakes import gigsim_adapter

SNAP = Path(__file__).parent / "snapshots"


def servers():
    from mcp_servers.marketplace import server as m
    from mcp_servers.portfolio import server as p
    from mcp_servers.workspace import server as w
    m.set_port(gigsim_adapter())
    return {"marketplace": m.mcp, "portfolio": p.mcp, "workspace": w.mcp}


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["marketplace", "portfolio", "workspace"])
async def test_schema_snapshot(name):
    srv = servers()[name]
    async with create_connected_server_and_client_session(srv._mcp_server) as c:
        tools = (await c.list_tools()).tools
    snap = {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                     "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None} for t in tools}
    f = SNAP / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not f.exists():
        f.write_text(json.dumps(snap, indent=1, sort_keys=True))
    assert json.loads(f.read_text()) == json.loads(json.dumps(snap, sort_keys=True)), f"{name} tool schema changed"


@pytest.mark.anyio
async def test_annotations_are_correct():
    srv = servers()["marketplace"]
    async with create_connected_server_and_client_session(srv._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    for n in ["search_jobs", "get_job", "get_client_history", "get_market_stats", "list_messages"]:
        assert tools[n].annotations.readOnlyHint is True
    for n in ["create_proposal_draft", "submit_proposal", "send_message"]:
        a = tools[n].annotations
        assert a.readOnlyHint is False and a.idempotentHint is True
    assert tools["submit_proposal"].annotations.destructiveHint is True


@pytest.mark.anyio
async def test_portfolio_search_and_resources():
    srv = servers()["portfolio"]
    async with create_connected_server_and_client_session(srv._mcp_server) as c:
        r = await c.call_tool("search_evidence", {"requirement": "LangGraph agents", "k": 3, "portfolio": "ai_ml"})
        items = r.structuredContent["items"]
        assert items and all("evidence_id" in i and "type" in i for i in items)
        templates = (await c.list_resource_templates()).resourceTemplates
        assert {"portfolio://case/{id}", "portfolio://proposal/{id}"} <= {t.uriTemplate for t in templates}
        prompts = {p.name for p in (await c.list_prompts()).prompts}
        assert "answer_screening_question" in prompts
        res = await c.read_resource("portfolio://case/ai_ml-p01")
        assert "Client" in res.contents[0].text


@pytest.mark.anyio
async def test_write_requires_approval_and_is_idempotent():
    from mcp_servers.marketplace.server import approval_token
    srv = servers()["marketplace"]
    letter = "I built a churn model with XGBoost and MLflow for a fintech client; happy to walk you through it."
    async with create_connected_server_and_client_session(srv._mcp_server) as c:
        dry = await c.call_tool("create_proposal_draft", {"freelancer_id": "fl-ai-ml", "job_id": "dev-ai-0004", "cover_letter": letter,
                                                          "bid_amount": 900, "idempotency_key": "test-key-0001", "dry_run": True})
        assert dry.structuredContent["status"] == "preview"
        no = await c.call_tool("create_proposal_draft", {"freelancer_id": "fl-ai-ml", "job_id": "dev-ai-0004", "cover_letter": letter,
                                                         "bid_amount": 900, "idempotency_key": "test-key-0002"})
        assert no.structuredContent["status"] == "rejected"
        tok = approval_token("proposal", "dev-ai-0004", letter + str(900.0))
        args = {"freelancer_id": "fl-ai-ml", "job_id": "dev-ai-0004", "cover_letter": letter, "bid_amount": 900,
                "idempotency_key": "test-key-0003", "approval_id": tok}
        a = (await c.call_tool("create_proposal_draft", args)).structuredContent
        b = (await c.call_tool("create_proposal_draft", args)).structuredContent
        assert a["result"]["proposal_id"] == b["result"]["proposal_id"] and b["idempotent_replay"]
        pid = a["result"]["proposal_id"]
        sub_args = {"proposal_id": pid, "freelancer_id": "fl-ai-ml", "idempotency_key": "test-sub-0001",
                    "approval_id": approval_token("submit", pid, letter + "900.0")}
        s1 = (await c.call_tool("submit_proposal", sub_args)).structuredContent
        s2 = (await c.call_tool("submit_proposal", sub_args)).structuredContent
        assert s1["status"] == "submitted" and s2["idempotent_replay"] is True
        assert s1["connects_balance_after"] == s1.get("connects_balance_after")


@pytest.mark.anyio
async def test_input_constraints_enforced():
    srv = servers()["marketplace"]
    async with create_connected_server_and_client_session(srv._mcp_server) as c:
        r = await c.call_tool("search_jobs", {"limit": 500})
        assert r.isError


@pytest.fixture
def anyio_backend():
    return "asyncio"
