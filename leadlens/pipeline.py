"""Orchestrates: load -> normalise -> dedupe -> validate -> enrich -> score."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import pandas as pd

from .dedupe import dedupe
from .enrich import Enricher
from .models import ICPConfig, Lead, ScoredLead
from .normalize import canonical_domain, email_domain, normalize_email, normalize_website, parse_number
from .score import score_lead
from .storage import Cache
from .validate import validate_lead

DEFAULT_ICP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "icp.yaml")

# Accept the many ways scrapers name the same column.
COLUMN_ALIASES: Dict[str, List[str]] = {
    "company": ["company", "company name", "name", "business", "business name", "organization", "org"],
    "website": ["website", "url", "web", "site", "homepage", "company website", "domain"],
    "industry": ["industry", "sector", "category", "vertical", "niche"],
    "city": ["city", "town"],
    "state": ["state", "region", "province"],
    "country": ["country"],
    "employees": ["employees", "employee count", "headcount", "size", "company size", "staff", "num employees"],
    "revenue": ["revenue", "annual revenue", "est revenue", "estimated revenue", "sales", "turnover"],
    "owner_name": ["owner", "owner name", "contact", "contact name", "first name last name", "decision maker", "ceo", "founder", "full name"],
    "owner_title": ["title", "job title", "position", "role"],
    "email": ["email", "e-mail", "email address", "contact email"],
    "phone": ["phone", "phone number", "telephone", "tel", "mobile"],
    "linkedin": ["linkedin", "linkedin url", "linkedin profile"],
    "source": ["source", "lead source"],
}


def map_columns(df: pd.DataFrame) -> Dict[str, str]:
    """Return {canonical_field: actual_column} using alias matching."""
    def norm(c: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", str(c).lower().replace("_", " ")).strip()

    lower = {norm(c): c for c in df.columns}
    mapping: Dict[str, str] = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in lower and lower[a] not in mapping.values():
                mapping[field_name] = lower[a]
                break
    return mapping


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in {"nan", "none", "null", "n/a"} else None


def dataframe_to_leads(df: pd.DataFrame, mapping: Optional[Dict[str, str]] = None) -> List[Lead]:
    mapping = mapping or map_columns(df)
    used = set(mapping.values())
    leads: List[Lead] = []
    for _, row in df.iterrows():
        data = {f: _clean(row[c]) for f, c in mapping.items()}
        data["employees"] = int(n) if (n := parse_number(data.get("employees"))) is not None else None
        data["revenue"] = parse_number(data.get("revenue"))
        data["email"] = normalize_email(data.get("email"))
        data["website"] = normalize_website(data.get("website"))
        data["domain"] = canonical_domain(data.get("website")) or email_domain(data.get("email"))
        data["extra"] = {c: str(row[c]) for c in df.columns if c not in used and _clean(row[c]) is not None}
        leads.append(Lead(**data))
    return leads


@dataclass
class PipelineResult:
    scored: List[ScoredLead]
    rows_in: int
    rows_after_dedupe: int
    duplicates_removed: int
    enriched: int
    cache_hits: int
    elapsed_s: float
    column_mapping: Dict[str, str]
    stage_times: Dict[str, float] = field(default_factory=dict)

    @property
    def tier_counts(self) -> Dict[str, int]:
        out = {"Hot": 0, "Warm": 0, "Cold": 0}
        for s in self.scored:
            out[s.tier] = out.get(s.tier, 0) + 1
        return out


def run_pipeline(
    df: pd.DataFrame,
    icp: Optional[ICPConfig] = None,
    cache: Optional[Cache] = None,
    enrich: bool = True,
    check_mx: bool = True,
    progress: Optional[Callable[[str, float], None]] = None,
    enricher: Optional[Enricher] = None,
    source: str = "upload",
) -> PipelineResult:
    t0 = time.time()
    times: Dict[str, float] = {}
    icp = icp or ICPConfig.from_yaml(DEFAULT_ICP)
    cache = cache if cache is not None else Cache()
    report = progress or (lambda msg, frac: None)

    report("Parsing rows", 0.05)
    mapping = map_columns(df)
    leads = dataframe_to_leads(df, mapping)
    times["parse"] = time.time() - t0

    report("Deduplicating", 0.15)
    t = time.time()
    uniques, counts = dedupe(leads)
    times["dedupe"] = time.time() - t

    report("Validating contacts", 0.30)
    t = time.time()
    validations = [validate_lead(l, cache, do_mx=check_mx) for l in uniques]
    times["validate"] = time.time() - t

    enrichments = {}
    if enrich:
        report("Enriching from websites", 0.45)
        t = time.time()
        enricher = enricher or Enricher(cache=cache)
        enrichments = enricher.enrich_many([l.domain for l in uniques if l.domain])
        times["enrich"] = time.time() - t

    report("Scoring", 0.85)
    t = time.time()
    scored: List[ScoredLead] = []
    for i, (lead, v) in enumerate(zip(uniques, validations)):
        enr = enrichments.get(lead.domain) if lead.domain else None
        # Back-fill contact info discovered on the website (business-level, public).
        if enr and not lead.email and enr.emails_found:
            lead.email = enr.emails_found[0]
            v = validate_lead(lead, cache, do_mx=check_mx)
        if enr and not lead.phone and enr.phones_found:
            lead.phone = enr.phones_found[0]
            v.phone_ok, v.phone_e164 = True, enr.phones_found[0]
        sl = score_lead(lead, v, enr, icp)
        sl.merged_from = counts.get(i, 1)
        if sl.merged_from > 1:
            sl.flags.append(f"merged-{sl.merged_from}")
        scored.append(sl)
    scored.sort(key=lambda s: -s.fit_score)
    times["score"] = time.time() - t

    result = PipelineResult(
        scored=scored,
        rows_in=len(leads),
        rows_after_dedupe=len(uniques),
        duplicates_removed=len(leads) - len(uniques),
        enriched=sum(1 for e in enrichments.values() if e.reachable),
        cache_hits=sum(1 for e in enrichments.values() if e.from_cache),
        elapsed_s=round(time.time() - t0, 2),
        column_mapping=mapping,
        stage_times={k: round(v, 2) for k, v in times.items()},
    )
    tc = result.tier_counts
    cache.record_run(source, result.rows_in, result.rows_after_dedupe, tc["Hot"], tc["Warm"], tc["Cold"])
    report("Done", 1.0)
    return result
