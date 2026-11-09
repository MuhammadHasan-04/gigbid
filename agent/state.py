"""Typed graph state. Three things are kept apart:

* State (this file): what this job / conversation needs right now. Small, typed fields.
* Execution trace: every tool name, argument, result and model call -> agent/tracing.py spans
  (data/runtime/traces + Langfuse), keyed by trace_id. Only a short `log` lives in state.
* Long-term memory: promoted knowledge in the LangGraph store (agent/memory), written only by
  explicit promotion rules. Raw tool output never goes there.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


def merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


def keep_last(a, b):
    return b if b is not None else a


Status = Literal["new", "analysing", "skipped", "watch", "drafting", "needs_attention", "awaiting_approval",
                 "approved", "submitted", "rejected", "dead_letter", "replied", "sent"]


class BidState(TypedDict, total=False):
    # identity
    user_id: str
    persona: str
    freelancer_id: str
    job_id: str
    trace_id: str
    autonomy: str
    # inputs
    job: dict[str, Any]
    client: dict[str, Any]
    # parallel analyses (each branch writes its own field; reducers make concurrent writes safe)
    job_spec: Annotated[dict | None, keep_last]
    risk: Annotated[dict | None, keep_last]
    fit: Annotated[dict | None, keep_last]
    evidence: Annotated[dict[str, str], merge_dict]   # evidence_id -> text shown to the writer
    # decisions and drafts
    decision: dict | None
    price: dict | None
    draft: dict | None
    critiques: Annotated[list[dict], operator.add]
    compliance: dict | None
    approval: dict | None
    submission: dict | None
    revision: int
    # control
    status: Status
    attention_reason: str | None
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    usd: Annotated[float, operator.add]
    errors: Annotated[list[dict], operator.add]
    log: Annotated[list[dict], operator.add]


class ConvState(TypedDict, total=False):
    user_id: str
    persona: str
    freelancer_id: str
    thread_id: str
    trace_id: str
    thread: dict[str, Any]
    job: dict[str, Any]
    floor: float
    intent: dict | None
    slots: list[dict]
    reply: dict | None
    compliance: dict | None
    approval: dict | None
    sent: dict | None
    status: Status
    attention_reason: str | None
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    usd: Annotated[float, operator.add]
    errors: Annotated[list[dict], operator.add]
    log: Annotated[list[dict], operator.add]
