"""Pydantic models shared across the pipeline."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """A raw lead as it arrives from a scrape / CSV upload.

    All fields are optional on purpose: real scraped data is messy and the
    pipeline's job is to fill gaps, not reject rows.
    """

    company: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    employees: Optional[int] = None
    revenue: Optional[float] = None
    owner_name: Optional[str] = None
    owner_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    source: Optional[str] = None
    extra: Dict[str, str] = Field(default_factory=dict)


class Enrichment(BaseModel):
    """Signals discovered from the company website (public, business-level only)."""

    domain: str
    reachable: bool = False
    status_code: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    emails_found: List[str] = Field(default_factory=list)
    phones_found: List[str] = Field(default_factory=list)
    socials: Dict[str, str] = Field(default_factory=dict)
    tech_hints: List[str] = Field(default_factory=list)
    has_careers_page: bool = False
    fetched_at: Optional[str] = None
    from_cache: bool = False
    error: Optional[str] = None
    robots_blocked: bool = False


class Validation(BaseModel):
    email_syntax_ok: Optional[bool] = None
    email_mx_ok: Optional[bool] = None
    email_is_generic: Optional[bool] = None   # info@, sales@ ...
    email_is_freemail: Optional[bool] = None  # gmail.com, yahoo.com ...
    phone_ok: Optional[bool] = None
    phone_e164: Optional[str] = None
    website_ok: Optional[bool] = None


class ScoreBreakdown(BaseModel):
    component: str
    weight: float
    score: float          # 0..1
    points: float         # weight * score
    reason: str


class ScoredLead(BaseModel):
    lead: Lead
    validation: Validation = Field(default_factory=Validation)
    enrichment: Optional[Enrichment] = None
    fit_score: float = 0.0
    tier: str = "Cold"
    breakdown: List[ScoreBreakdown] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)   # e.g. "duplicate-merged", "no-email"
    merged_from: int = 1   # number of raw rows merged into this lead


class ICPConfig(BaseModel):
    name: str = "default"
    weights: Dict[str, float]
    industries: Dict[str, List[str]]
    geography: Dict[str, List[str]]
    size: Dict[str, float]
    tiers: Dict[str, float]

    @classmethod
    def from_yaml(cls, path: str) -> "ICPConfig":
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return cls(**raw)

    def tier_for(self, score: float) -> str:
        if score >= self.tiers.get("hot", 75):
            return "Hot"
        if score >= self.tiers.get("warm", 50):
            return "Warm"
        return "Cold"
