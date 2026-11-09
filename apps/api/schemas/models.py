"""Request/response models. The web client in apps/web/src/lib/api is generated from this OpenAPI schema."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field("", max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str
    user: "UserOut"


class SavedSearch(BaseModel):
    id: str
    query: str = Field("", max_length=200)
    every_minutes: int = Field(30, ge=15, le=1440)
    limit: int = Field(15, ge=1, le=50)
    posted_within_min: int | None = None


class Filters(BaseModel):
    min_budget: float = 0


class SettingsModel(BaseModel):
    autonomy: Literal["suggest", "auto_skip_low_fit"] = "suggest"
    hourly_floor: float | None = Field(None, ge=1, le=1000)
    weekly_connects_budget: int = Field(80, ge=0, le=1000)
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"
    saved_searches: list[SavedSearch] = []
    filters: Filters = Filters()


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None
    persona: str | None
    freelancer_id: str | None
    settings: SettingsModel
    upwork_connected: bool = False


class OnboardIn(BaseModel):
    persona: Literal["ai_ml", "fullstack", "data_analyst"]
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"
    hourly_floor: float | None = Field(None, ge=1, le=1000)
    weekly_connects_budget: int = Field(80, ge=0, le=1000)
    saved_search_query: str = ""
    min_budget: float = 0


class JobRow(BaseModel):
    job_id: str
    title: str | None
    category: str | None
    status: str | None
    action: str | None
    fit_score: float | None
    risk_score: float | None
    is_scam: bool | None
    flags: list[str] = []
    price: float | None
    connects_cost: int | None
    reasons: list[str] = []
    attention_reason: str | None = None
    budget: dict | None = None
    thread_id: str | None
    trace_id: str | None
    updated_at: Any = None


class JobDetail(BaseModel):
    job: dict
    row: JobRow | None
    state: dict
    next: list[str]
    interrupt: dict | None


class DecisionIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    cover_letter: str | None = Field(None, max_length=5000)
    screening_answers: list[str] | None = None
    bid_amount: float | None = Field(None, gt=0, le=100000)
    body: str | None = Field(None, max_length=4000)
    slot: str | None = None
    reason: str | None = Field(None, max_length=500)


class Accepted(BaseModel):
    queued: bool = True
    thread_id: str | None = None
    job_id: str | None = None
    detail: str | None = None


class Approval(BaseModel):
    thread_id: str
    kind: str
    title: str | None
    created: Any = None
    payload: dict


class PipelineCard(BaseModel):
    proposal_id: str
    job_id: str | None
    title: str | None
    category: str | None
    status: str
    bid: float | None
    connects: int | None
    updated_at: Any = None


class Conversation(BaseModel):
    thread_id: str
    job_id: str | None
    status: str | None
    intent: str | None
    last_client_msg: str | None
    graph_thread: str | None
    messages: list[dict] = []
    pending: dict | None = None


class RunEvent(BaseModel):
    id: int
    thread_id: str
    trace_id: str | None
    event: dict
    ts: Any


class TraceSpan(BaseModel):
    ts: float
    kind: str
    name: str
    node: str | None = None
    data: dict = {}


class TraceOut(BaseModel):
    trace_id: str
    summary: dict
    spans: list[TraceSpan]


class Health(BaseModel):
    api: bool = True
    marketplace: dict
    model_profile: str
    policy_version: int


class Analytics(BaseModel):
    by_category: list[dict]
    connects: dict
    cost_latency: dict
    rejection_reasons: list[dict]
    funnel: dict


class MemoryOut(BaseModel):
    style: list[dict]
    style_candidates: list[dict]
    outcome: list[dict]
    edits: list[dict]


class UploadIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    text: str = Field(min_length=20, max_length=20000)
    industry: str | None = None
    date: str | None = None


TokenOut.model_rebuild()
