"""Flatten ScoredLeads into DataFrames / CRM-ready files."""
from __future__ import annotations

import io
from typing import List

import pandas as pd

from .models import ScoredLead

# Column names chosen to import straight into HubSpot's contact/company importer.
HUBSPOT_COLUMNS = {
    "company": "Company name", "domain": "Company domain name", "industry": "Industry",
    "city": "City", "state": "State/Region", "country": "Country/Region",
    "employees": "Number of Employees", "revenue": "Annual Revenue",
    "owner_name": "Contact name", "owner_title": "Job Title", "email": "Email",
    "phone_e164": "Phone Number", "linkedin": "LinkedIn URL", "website": "Website URL",
    "fit_score": "Lead Score", "tier": "Lead Status", "reasons": "Notes",
}


def to_dataframe(scored: List[ScoredLead]) -> pd.DataFrame:
    rows = []
    for s in scored:
        l, v, e = s.lead, s.validation, s.enrichment
        rows.append({
            "fit_score": s.fit_score,
            "tier": s.tier,
            "company": l.company,
            "domain": l.domain,
            "website": l.website,
            "industry": l.industry,
            "city": l.city,
            "state": l.state,
            "country": l.country,
            "employees": l.employees,
            "revenue": l.revenue,
            "owner_name": l.owner_name,
            "owner_title": l.owner_title,
            "email": l.email,
            "email_verified": bool(v.email_syntax_ok and v.email_mx_ok),
            "email_generic": v.email_is_generic,
            "email_freemail": v.email_is_freemail,
            "phone_e164": v.phone_e164 or l.phone,
            "phone_valid": v.phone_ok,
            "linkedin": l.linkedin,
            "site_live": (e.reachable if e else None),
            "site_title": (e.title if e else None),
            "site_description": (e.description if e else None),
            "socials": ", ".join(e.socials.keys()) if e else None,
            "tech": ", ".join(e.tech_hints) if e else None,
            "hiring": (e.has_careers_page if e else None),
            "merged_from": s.merged_from,
            "flags": ", ".join(s.flags),
            "reasons": " | ".join(s.reasons),
            "source": l.source,
        })
    return pd.DataFrame(rows)


def to_csv_bytes(df: pd.DataFrame, crm: bool = False) -> bytes:
    if crm:
        df = df[[c for c in HUBSPOT_COLUMNS if c in df.columns]].rename(columns=HUBSPOT_COLUMNS)
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Leads")
        hot = df[df["tier"] == "Hot"] if "tier" in df.columns else df.iloc[0:0]
        hot.to_excel(xw, index=False, sheet_name="Hot only")
    return buf.getvalue()
