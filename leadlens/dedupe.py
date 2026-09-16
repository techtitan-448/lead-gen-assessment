"""Deduplicate leads by canonical domain, then by fuzzy company name.

Strategy (in order):
1. Exact match on canonical domain (the strongest identity signal for a company).
2. Exact match on normalised email domain (when website is missing).
3. Fuzzy match on canonical company name within the same city/state (or globally
   when location is missing) using token_set_ratio >= threshold.

When two records collide we keep the *richest* one (most non-empty fields) and
back-fill its gaps from the other, so merging never loses information.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from .models import Lead
from .normalize import FREE_MAIL_DOMAINS, canonical_company, canonical_domain

MERGEABLE = [
    "company", "website", "domain", "industry", "city", "state", "country",
    "employees", "revenue", "owner_name", "owner_title", "email", "phone", "linkedin", "source",
]


def _richness(lead: Lead) -> int:
    return sum(1 for f in MERGEABLE if getattr(lead, f) not in (None, "", 0))


def merge(a: Lead, b: Lead) -> Lead:
    """Return a new Lead: the richer of a/b with gaps filled from the other."""
    primary, secondary = (a, b) if _richness(a) >= _richness(b) else (b, a)
    data = primary.model_dump()
    for f in MERGEABLE:
        if data.get(f) in (None, "", 0) and getattr(secondary, f) not in (None, "", 0):
            data[f] = getattr(secondary, f)
    extra = dict(secondary.extra)
    extra.update(primary.extra)
    data["extra"] = extra
    return Lead(**data)


def _location_key(lead: Lead) -> str:
    return f"{(lead.city or '').strip().lower()}|{(lead.state or '').strip().lower()}"


def dedupe(leads: List[Lead], name_threshold: int = 90) -> Tuple[List[Lead], Dict[int, int]]:
    """Return (unique_leads, merged_counts) where merged_counts[i] = rows folded into unique i."""
    by_domain: Dict[str, int] = {}
    uniques: List[Lead] = []
    counts: Dict[int, int] = {}

    # Pass 1: domain identity (website or email domain)
    leftovers: List[Lead] = []
    for lead in leads:
        dom = canonical_domain(lead.website) or canonical_domain(lead.domain) or canonical_domain(lead.email)
        if dom and dom not in FREE_MAIL_DOMAINS:
            lead.domain = dom
            if dom in by_domain:
                idx = by_domain[dom]
                uniques[idx] = merge(uniques[idx], lead)
                counts[idx] += 1
            else:
                by_domain[dom] = len(uniques)
                uniques.append(lead)
                counts[len(uniques) - 1] = 1
        else:
            leftovers.append(lead)

    # Pass 2: fuzzy company name for rows without a usable domain
    name_index: List[Tuple[str, str, int]] = [
        (canonical_company(u.company), _location_key(u), i) for i, u in enumerate(uniques)
    ]
    for lead in leftovers:
        cname = canonical_company(lead.company)
        loc = _location_key(lead)
        match: Optional[int] = None
        if cname:
            for other_name, other_loc, idx in name_index:
                if not other_name:
                    continue
                same_place = loc == other_loc or loc == "|" or other_loc == "|"
                if same_place and fuzz.token_set_ratio(cname, other_name) >= name_threshold:
                    match = idx
                    break
        if match is None:
            uniques.append(lead)
            idx = len(uniques) - 1
            counts[idx] = 1
            name_index.append((cname, loc, idx))
        else:
            uniques[match] = merge(uniques[match], lead)
            counts[match] += 1
    return uniques, counts

