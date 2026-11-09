"""Structured hand-offs between agents. Anything a later step decides on is one of these objects."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list, description="skills/tools the job needs, canonical names")
    budget_min: float = 0
    budget_max: float = 0
    timeline_days: int | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="unstated needs implied by the post")
    category: str | None = None
    industry: str | None = None


class RiskReport(BaseModel):
    risk_score: float = Field(ge=0, le=1)
    is_scam: bool
    flags: list[Literal["unpaid_work", "off_platform_contact", "off_platform_payment", "upfront_fee",
                        "unverified_payment", "no_hire_history", "low_budget", "prompt_injection",
                        "bad_reviews", "vague_scope"]] = Field(default_factory=list)
    injection_detected: bool = False
    client_quality: float = Field(0.5, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class RequirementMatch(BaseModel):
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    strength: Literal["strong", "partial", "none"] = "none"
    note: str = ""


class FitReport(BaseModel):
    fit_score: float = Field(ge=0, le=1)
    matches: list[RequirementMatch] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)
    auto: bool = False


class PriceQuote(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "USD"
    market_p25: float | None = None
    market_p50: float | None = None
    market_p75: float | None = None
    floor: float | None = None
    connects_cost: int = 0
    connects_worth_it: bool = True
    expected_value_usd: float | None = None
    rationale: str = ""


class Claim(BaseModel):
    text: str
    verdict: Literal["supported", "partial", "unsupported"] = "unsupported"
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class ProposalDraft(BaseModel):
    cover_letter: str
    screening_answers: list[str] = Field(default_factory=list)
    citations: dict[str, list[str]] = Field(default_factory=dict, description="sentence index -> evidence ids")
    claims: list[Claim] = Field(default_factory=list)
    unsupported_before: int = 0
    unsupported_after: int = 0
    revision: int = 0


class Critique(BaseModel):
    passed: bool
    grounding: float = Field(ge=0, le=1)
    personalisation: float = Field(ge=0, le=1)
    length_ok: bool = True
    issues: list[str] = Field(default_factory=list)


class ComplianceVerdict(BaseModel):
    allowed: bool
    blocked_reason: str | None = None
    violations: list[dict] = Field(default_factory=list)
    cleaned_text: str = ""
    policy_version: int = 1


class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    confidence: float = Field(0.5, ge=0, le=1)
    injection_detected: bool = False
    summary: str = ""


class ReplyDraft(BaseModel):
    body: str
    proposed_slots: list[str] = Field(default_factory=list)
    needs_attention: bool = False
    note: str = ""
