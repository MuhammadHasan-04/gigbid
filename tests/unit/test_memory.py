import asyncio

from langgraph.store.memory import InMemoryStore

from agent.memory import promotion_rules
from agent.memory.store import set_store, style_rules


def test_style_rule_needs_two_distinct_jobs():
    set_store(InMemoryStore())
    before = "Dear Sir, I am passionate about data. I built dashboards for retail clients and can help."
    after = "I built dashboards for retail clients and can help."

    async def run():
        r1 = await promotion_rules.record_edit("u1", "job-1", before, after)
        assert r1["promoted"] == []                       # one edit is not enough
        r1b = await promotion_rules.record_edit("u1", "job-1", before, after)
        assert r1b["promoted"] == []                      # same job again does not count
        r2 = await promotion_rules.record_edit("u1", "job-2", before, after)
        assert any("first sentence" in x for x in r2["promoted"])
        rules = await style_rules("u1")
        assert any("passionate" in x for x in rules)
        assert await style_rules("someone-else") == []    # tenant scoped
    asyncio.run(run())


def test_outcome_exemplars_need_samples():
    set_store(InMemoryStore())

    async def run():
        for _ in range(2):
            await promotion_rules.record_outcome("u", "bi", "p", "submitted")
        v = await promotion_rules.record_outcome("u", "bi", "good proposal", "replied")
        assert v["exemplars"] == []                       # only 2 sends so far
        await promotion_rules.record_outcome("u", "bi", "p", "submitted")
        v = await promotion_rules.record_outcome("u", "bi", "good proposal", "replied")
        assert v["exemplars"] == ["good proposal"] and v["reply_rate"] == round(2 / 3, 3)
    asyncio.run(run())
