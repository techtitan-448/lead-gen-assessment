"""Explainable ICP fit scoring.

Each component returns (score_0_to_1, reason). The final fit score is the
weighted sum (weights from config/icp.yaml) scaled to 0–100. No ML, no black
box: a sales rep can read *exactly* why a lead ranked where it did, and a
manager can retune weights in YAML without touching code.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .models import Enrichment, ICPConfig, Lead, ScoreBreakdown, ScoredLead, Validation


def _contains_any(hay: str, needles: List[str]) -> Optional[str]:
    hay = hay.lower()
    for n in needles:
        if n.lower() in hay:
            return n
    return None


def industry_fit(lead: Lead, enr: Optional[Enrichment], cfg: ICPConfig) -> Tuple[float, str]:
    text = " ".join(filter(None, [lead.industry, enr.description if enr else None, enr.title if enr else None]))
    if not text.strip():
        return 0.3, "Industry unknown — partial credit until enriched"
    ind = cfg.industries
    hit = _contains_any(text, ind.get("exclude", []))
    if hit:
        return 0.0, f"Excluded industry ('{hit}')"
    hit = _contains_any(text, ind.get("target", []))
    if hit:
        return 1.0, f"Target industry match ('{hit}')"
    hit = _contains_any(text, ind.get("adjacent", []))
    if hit:
        return 0.6, f"Adjacent industry ('{hit}')"
    return 0.2, f"Industry '{(lead.industry or text)[:40]}' outside ICP"


def geography_fit(lead: Lead, cfg: ICPConfig) -> Tuple[float, str]:
    geo = cfg.geography
    countries = [c.lower() for c in geo.get("target_countries", [])]
    states = [s.lower() for s in geo.get("target_states", [])]
    country = (lead.country or "").strip().lower()
    state = (lead.state or "").strip().lower()
    if not country and not state:
        return 0.4, "Location unknown"
    if countries and country and country not in countries:
        return 0.0, f"Country '{lead.country}' outside target geography"
    if states:
        if state in states:
            return 1.0, f"Target state ({lead.state})"
        return 0.4, f"State '{lead.state or '?'}' not in target list"
    return 1.0, f"In target geography ({lead.country or lead.state})"


def _band(value: Optional[float], lo: float, hi: float, label: str, fmt=lambda v: f"{v:,.0f}") -> Tuple[float, str]:
    if value is None:
        return 0.4, f"{label} unknown"
    if lo <= value <= hi:
        return 1.0, f"{label} {fmt(value)} inside target band"
    # Soft falloff: 50% off by a factor of 2 outside the band, 0 beyond 4x
    if value < lo:
        ratio = value / lo if lo else 0
    else:
        ratio = hi / value if value else 0
    score = max(0.0, min(1.0, (ratio - 0.25) / 0.75))
    side = "below" if value < lo else "above"
    return round(score, 2), f"{label} {fmt(value)} {side} target band"


def size_fit(lead: Lead, cfg: ICPConfig) -> Tuple[float, str]:
    s = cfg.size
    emp_score, emp_reason = _band(lead.employees, s["employees_min"], s["employees_max"], "Headcount")
    rev_score, rev_reason = _band(lead.revenue, s["revenue_min"], s["revenue_max"], "Revenue", lambda v: f"${v/1e6:.1f}M")
    if lead.employees is None and lead.revenue is None:
        return 0.4, "No size data (headcount/revenue)"
    if lead.employees is None:
        return rev_score, rev_reason
    if lead.revenue is None:
        return emp_score, emp_reason
    return round((emp_score + rev_score) / 2, 2), f"{emp_reason}; {rev_reason.lower()}"


def contact_quality(lead: Lead, v: Validation, enr: Optional[Enrichment]) -> Tuple[float, str]:
    pts, reasons = 0.0, []
    if lead.email:
        if v.email_syntax_ok and v.email_mx_ok:
            pts += 0.30 if (v.email_is_generic or v.email_is_freemail) else 0.45
            note = " — generic inbox" if v.email_is_generic else (" — personal free-mail address" if v.email_is_freemail else "")
            reasons.append("verified email (MX ok)" + note)
        elif v.email_syntax_ok and v.email_mx_ok is None:
            pts += 0.20 if (v.email_is_generic or v.email_is_freemail) else 0.25
            reasons.append("email syntax ok, MX unverified" + (" — free-mail" if v.email_is_freemail else ""))
        elif v.email_syntax_ok:
            reasons.append("email domain has no mail server")
        else:
            reasons.append("invalid email")
    elif enr and enr.emails_found:
        pts += 0.20
        reasons.append("no email on record, but found one on website")
    else:
        reasons.append("no email")
    if v.phone_ok:
        pts += 0.25
        reasons.append("valid phone")
    elif enr and enr.phones_found:
        pts += 0.12
        reasons.append("phone found on website")
    if lead.owner_name:
        pts += 0.20
        reasons.append("owner/decision-maker named")
    if lead.linkedin:
        pts += 0.10
        reasons.append("LinkedIn present")
    return min(1.0, round(pts, 2)), ", ".join(reasons)


def web_presence(enr: Optional[Enrichment], lead: Lead) -> Tuple[float, str]:
    if enr is None:
        return (0.3, "Website not enriched") if (lead.website or lead.domain) else (0.0, "No website")
    if enr.robots_blocked:
        return 0.5, "Site disallows bots (respected) — assumed live"
    if not enr.reachable:
        return 0.0, f"Website unreachable ({enr.error or 'error'})"
    pts, why = 0.5, ["site live"]
    if enr.description:
        pts += 0.2
        why.append("has description")
    if enr.socials:
        pts += 0.15
        why.append(f"{len(enr.socials)} social link(s)")
    if enr.has_careers_page:
        pts += 0.1
        why.append("hiring page (growth signal)")
    if enr.tech_hints:
        pts += 0.05
        why.append("tech: " + ", ".join(enr.tech_hints[:3]))
    return min(1.0, round(pts, 2)), ", ".join(why)


def data_completeness(lead: Lead) -> Tuple[float, str]:
    fields = ["company", "website", "industry", "city", "country", "employees", "revenue", "owner_name", "email", "phone"]
    have = [f for f in fields if getattr(lead, f) not in (None, "", 0)]
    return round(len(have) / len(fields), 2), f"{len(have)}/{len(fields)} key fields present"


def score_lead(lead: Lead, v: Validation, enr: Optional[Enrichment], cfg: ICPConfig) -> ScoredLead:
    comps = {
        "industry_fit": industry_fit(lead, enr, cfg),
        "geography_fit": geography_fit(lead, cfg),
        "size_fit": size_fit(lead, cfg),
        "contact_quality": contact_quality(lead, v, enr),
        "web_presence": web_presence(enr, lead),
        "data_completeness": data_completeness(lead),
    }
    breakdown: List[ScoreBreakdown] = []
    total = 0.0
    for name, (s, reason) in comps.items():
        w = float(cfg.weights.get(name, 0))
        pts = round(w * s, 2)
        total += pts
        breakdown.append(ScoreBreakdown(component=name, weight=w, score=s, points=pts, reason=reason))
    total = round(min(100.0, total), 1)
    sl = ScoredLead(lead=lead, validation=v, enrichment=enr, fit_score=total, tier=cfg.tier_for(total), breakdown=breakdown)
    sl.reasons = [f"{b.component.replace('_', ' ').title()}: {b.reason}" for b in sorted(breakdown, key=lambda b: -b.points)]
    if not lead.email and not (enr and enr.emails_found):
        sl.flags.append("no-email")
    if v.email_syntax_ok is False or v.email_mx_ok is False:
        sl.flags.append("bad-email")
    if enr and not enr.reachable and not enr.robots_blocked:
        sl.flags.append("site-down")
    return sl
