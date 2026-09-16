"""LeadLens — Streamlit UI.

Flow (top to bottom, no hidden menus):
  1. Load leads  (upload CSV/XLSX or use the sample)
  2. Run pipeline (dedupe → validate → enrich → score)
  3. Review       (KPIs, filters, ranked table, "why this score?")
  4. Export       (CSV / CRM-ready CSV / Excel)
"""
from __future__ import annotations

import io
import warnings

import pandas as pd
import streamlit as st

from leadlens.export import to_csv_bytes, to_dataframe, to_excel_bytes
from leadlens.models import ICPConfig
from leadlens.pipeline import DEFAULT_ICP, run_pipeline
from leadlens.storage import Cache

warnings.filterwarnings("ignore")

st.set_page_config(page_title="LeadLens", page_icon="🔎", layout="wide")

# ----------------------------------------------------------------------------
# Styling: a restrained palette, one accent, tier colours that mean something.
# ----------------------------------------------------------------------------
st.markdown(
    """
<style>
:root { --accent:#2563eb; --hot:#dc2626; --warm:#d97706; --cold:#64748b; --muted:#6b7280; }
.block-container { padding-top: 1.6rem; max-width: 1280px; }
h1 { font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0; }
.subtitle { color: var(--muted); margin: 0 0 1.2rem 0; font-size: 1.02rem; }
.step { display:inline-block; background:var(--accent); color:#fff; border-radius:999px; width:1.6rem; height:1.6rem;
        text-align:center; line-height:1.6rem; font-weight:700; margin-right:.5rem; font-size:.9rem; }
.kpi { border:1px solid #e5e7eb; border-radius:12px; padding:.9rem 1rem; background:#fff; }
.kpi .label { color:var(--muted); font-size:.8rem; text-transform:uppercase; letter-spacing:.06em; }
.kpi .value { font-size:1.7rem; font-weight:700; line-height:1.2; }
.kpi .sub { color:var(--muted); font-size:.8rem; }
.tier-Hot { color:var(--hot); font-weight:700; } .tier-Warm { color:var(--warm); font-weight:700; } .tier-Cold { color:var(--cold); font-weight:700; }
.reason { padding:.35rem .6rem; border-left:3px solid var(--accent); background:#f8fafc; margin:.25rem 0; border-radius:4px; font-size:.92rem; }
.flag { display:inline-block; background:#fee2e2; color:#991b1b; border-radius:6px; padding:.1rem .45rem; font-size:.78rem; margin-right:.3rem; }
.ok { display:inline-block; background:#dcfce7; color:#166534; border-radius:6px; padding:.1rem .45rem; font-size:.78rem; margin-right:.3rem; }
small.hint { color:var(--muted); }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_cache() -> Cache:
    return Cache()


def kpi(col, label: str, value, sub: str = ""):
    col.markdown(
        f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
st.markdown("# 🔎 LeadLens")
st.markdown(
    '<p class="subtitle">Turn a raw scraped lead list into a <b>ranked, deduplicated, verified</b> shortlist — '
    "with a plain-English reason for every score.</p>",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Sidebar: ICP + run options
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Ideal Customer Profile")
    icp = ICPConfig.from_yaml(DEFAULT_ICP)
    st.caption(f"Profile: **{icp.name}** · edit `config/icp.yaml` for industries & bands")
    with st.expander("Score weights", expanded=False):
        new_weights = {}
        for k, v in icp.weights.items():
            new_weights[k] = st.slider(k.replace("_", " ").title(), 0, 50, int(v), 5)
        total = sum(new_weights.values())
        if total != 100:
            st.warning(f"Weights sum to {total} (scores are still capped at 100).")
        icp.weights = {k: float(v) for k, v in new_weights.items()}
    with st.expander("Target size band", expanded=False):
        emp = st.slider("Employees", 1, 1000, (int(icp.size["employees_min"]), int(icp.size["employees_max"])))
        rev = st.slider("Revenue ($M)", 0.0, 100.0, (icp.size["revenue_min"] / 1e6, icp.size["revenue_max"] / 1e6), 0.5)
        icp.size.update({"employees_min": emp[0], "employees_max": emp[1], "revenue_min": rev[0] * 1e6, "revenue_max": rev[1] * 1e6})

    st.markdown("### Run options")
    do_enrich = st.toggle("Enrich from company websites", value=True, help="Fetches homepage (robots.txt respected, 1 req/s/host, cached 7 days).")
    do_mx = st.toggle("Verify email domains (MX lookup)", value=True, help="DNS check that the domain can receive mail.")
    st.markdown("---")
    cs = get_cache().stats()
    st.caption(f"Cache: {cs['enrichment_cached']} sites · {cs['mx_cached']} MX records")
    if st.button("Clear session results", use_container_width=True):
        st.session_state.pop("result", None)
        st.rerun()

# ----------------------------------------------------------------------------
# Step 1 — Load
# ----------------------------------------------------------------------------
st.markdown('<span class="step">1</span> **Load leads**', unsafe_allow_html=True)
c1, c2 = st.columns([3, 2])
with c1:
    upload = st.file_uploader("Upload a CSV or Excel export (SaaSquatch, Apollo, Google Maps scrape…)", type=["csv", "xlsx"])
with c2:
    st.write("")
    st.write("")
    sample_choice = st.radio(
        "…or use a sample", ["None", "Synthetic (82 messy rows, offline)", "Live SaaS companies (8 rows, real websites)"],
        horizontal=False, label_visibility="collapsed",
    )

df: pd.DataFrame | None = None
source_name = "upload"
if upload is not None:
    df = pd.read_excel(upload) if upload.name.lower().endswith("xlsx") else pd.read_csv(upload)
    source_name = upload.name
elif sample_choice.startswith("Synthetic"):
    df = pd.read_csv("data/sample_leads.csv")
    source_name = "sample_leads.csv"
elif sample_choice.startswith("Live"):
    df = pd.read_csv("data/sample_leads_live.csv")
    source_name = "sample_leads_live.csv"

if df is not None:
    st.caption(f"Loaded **{len(df):,} rows × {len(df.columns)} columns** from `{source_name}`")
    with st.expander("Preview raw input", expanded=False):
        st.dataframe(df.head(20), use_container_width=True, height=240)

# ----------------------------------------------------------------------------
# Step 2 — Run
# ----------------------------------------------------------------------------
st.markdown('<span class="step">2</span> **Run the quality pipeline**', unsafe_allow_html=True)
run_col, hint_col = st.columns([1, 4])
run_clicked = run_col.button("▶ Run pipeline", type="primary", disabled=df is None, use_container_width=True)
hint_col.markdown("<small class='hint'>dedupe → validate contacts → enrich from website → score against ICP</small>", unsafe_allow_html=True)

if run_clicked and df is not None:
    bar = st.progress(0, text="Starting…")
    result = run_pipeline(
        df, icp=icp, cache=get_cache(), enrich=do_enrich, check_mx=do_mx,
        progress=lambda msg, frac: bar.progress(frac, text=msg), source=source_name,
    )
    bar.empty()
    st.session_state["result"] = result
    st.session_state["table"] = to_dataframe(result.scored)

result = st.session_state.get("result")
if result is None:
    st.info("Load a file (or pick a sample) and press **Run pipeline**.")
    st.stop()

table: pd.DataFrame = st.session_state["table"]
tc = result.tier_counts

# ----------------------------------------------------------------------------
# Step 3 — Review
# ----------------------------------------------------------------------------
st.markdown('<span class="step">3</span> **Review ranked leads**', unsafe_allow_html=True)
k = st.columns(6)
kpi(k[0], "Rows in", f"{result.rows_in:,}")
kpi(k[1], "Duplicates removed", f"{result.duplicates_removed:,}", f"{result.duplicates_removed / max(result.rows_in, 1):.0%} of input")
kpi(k[2], "Verified emails", f"{int(table['email_verified'].sum()):,}", f"of {int(table['email'].notna().sum())} with email")
kpi(k[3], "🔥 Hot", tc["Hot"], f"score ≥ {icp.tiers['hot']:.0f}")
kpi(k[4], "Warm", tc["Warm"], f"score ≥ {icp.tiers['warm']:.0f}")
kpi(k[5], "Run time", f"{result.elapsed_s}s", f"{result.cache_hits} cache hits" if do_enrich else "enrichment off")

if result.column_mapping:
    unmapped = [c for c in df.columns if c not in result.column_mapping.values()] if df is not None else []
    with st.expander(f"Column mapping ({len(result.column_mapping)} recognised{', ' + str(len(unmapped)) + ' kept as extra' if unmapped else ''})"):
        st.json(result.column_mapping)

# Filters
f = st.columns([1.2, 1.2, 1.4, 1.4, 1.2])
tiers_sel = f[0].multiselect("Tier", ["Hot", "Warm", "Cold"], default=["Hot", "Warm"])
min_score = f[1].slider("Min score", 0, 100, 0, 5)
industries = sorted(x for x in table["industry"].dropna().unique())
ind_sel = f[2].multiselect("Industry", industries)
countries = sorted(x for x in table["country"].dropna().unique())
cty_sel = f[3].multiselect("Country", countries)
contact_req = f[4].selectbox("Contact", ["Any", "Verified email", "Has email", "Has phone", "Owner named"])

view = table[table["tier"].isin(tiers_sel) & (table["fit_score"] >= min_score)]
if ind_sel:
    view = view[view["industry"].isin(ind_sel)]
if cty_sel:
    view = view[view["country"].isin(cty_sel)]
if contact_req == "Verified email":
    view = view[view["email_verified"]]
elif contact_req == "Has email":
    view = view[view["email"].notna()]
elif contact_req == "Has phone":
    view = view[view["phone_e164"].notna()]
elif contact_req == "Owner named":
    view = view[view["owner_name"].notna()]

left, right = st.columns([3, 1.1])
with right:
    st.markdown("**Score distribution**")
    hist = pd.cut(table["fit_score"], bins=range(0, 101, 10), right=False).value_counts().sort_index()
    hist.index = [f"{int(i.left)}–{int(i.right)}" for i in hist.index]
    st.bar_chart(hist, height=200, color="#2563eb")
    st.markdown("**Flags**")
    flag_counts = table["flags"].str.split(", ").explode().replace("", pd.NA).dropna().value_counts()
    if flag_counts.empty:
        st.caption("No data-quality flags 🎉")
    else:
        for name, n in flag_counts.items():
            st.markdown(f"<span class='flag'>{name}</span> {n}", unsafe_allow_html=True)

with left:
    st.caption(f"Showing **{len(view):,}** of {len(table):,} leads · sorted by fit score")
    show_cols = ["fit_score", "tier", "company", "industry", "city", "country", "employees", "revenue", "owner_name",
                 "email", "email_verified", "phone_e164", "site_live", "merged_from"]
    st.dataframe(
        view[show_cols],
        use_container_width=True,
        height=420,
        hide_index=True,
        column_config={
            "fit_score": st.column_config.ProgressColumn("Fit", min_value=0, max_value=100, format="%.0f"),
            "tier": st.column_config.TextColumn("Tier", width="small"),
            "company": st.column_config.TextColumn("Company", width="medium"),
            "email_verified": st.column_config.CheckboxColumn("✉︎ ok", width="small"),
            "site_live": st.column_config.CheckboxColumn("Site", width="small"),
            "merged_from": st.column_config.NumberColumn("Merged", width="small", help="Raw rows folded into this lead"),
            "revenue": st.column_config.NumberColumn("Revenue", format="$%d"),
            "phone_e164": "Phone",
            "owner_name": "Owner",
        },
    )

# Lead inspector
st.markdown("**Why this score?**")
options = [f"{row.fit_score:.0f} · {row.company or row.domain or '(unnamed)'}" for row in view.itertuples()]
if options:
    pick = st.selectbox("Pick a lead to inspect", options, label_visibility="collapsed")
    idx = view.index[options.index(pick)]
    sl = result.scored[idx]
    a, b = st.columns([1.2, 1])
    with a:
        st.markdown(
            f"### {sl.lead.company or sl.lead.domain}  <span class='tier-{sl.tier}'>{sl.tier} · {sl.fit_score:.0f}/100</span>",
            unsafe_allow_html=True,
        )
        badges = []
        badges.append("<span class='ok'>email verified</span>" if (sl.validation.email_mx_ok) else "<span class='flag'>email unverified</span>")
        badges.append("<span class='ok'>phone valid</span>" if sl.validation.phone_ok else "<span class='flag'>no valid phone</span>")
        if sl.enrichment and sl.enrichment.reachable:
            badges.append("<span class='ok'>site live</span>")
        if sl.merged_from > 1:
            badges.append(f"<span class='ok'>merged {sl.merged_from} rows</span>")
        st.markdown(" ".join(badges), unsafe_allow_html=True)
        for r in sl.reasons:
            st.markdown(f"<div class='reason'>{r}</div>", unsafe_allow_html=True)
        bd = pd.DataFrame([{"component": x.component.replace("_", " "), "points": x.points, "max": x.weight} for x in sl.breakdown]).set_index("component")
        st.bar_chart(bd[["points"]], height=180, color="#2563eb")
    with b:
        st.markdown("**Contact**")
        st.write({k: v for k, v in {
            "Owner": sl.lead.owner_name, "Title": sl.lead.owner_title, "Email": sl.lead.email,
            "Phone": sl.validation.phone_e164 or sl.lead.phone, "LinkedIn": sl.lead.linkedin, "Website": sl.lead.website or sl.lead.domain,
        }.items() if v})
        if sl.enrichment:
            e = sl.enrichment
            st.markdown("**From the website**")
            if e.robots_blocked:
                st.caption("Site disallows crawlers — respected, not fetched.")
            elif not e.reachable:
                st.caption(f"Unreachable: {e.error}")
            else:
                st.write({k: v for k, v in {
                    "Title": e.title, "Description": e.description, "Emails on site": ", ".join(e.emails_found) or None,
                    "Phones on site": ", ".join(e.phones_found) or None, "Socials": ", ".join(e.socials) or None,
                    "Tech": ", ".join(e.tech_hints) or None, "Hiring page": "yes" if e.has_careers_page else None,
                }.items() if v})

# ----------------------------------------------------------------------------
# Step 4 — Export
# ----------------------------------------------------------------------------
st.markdown('<span class="step">4</span> **Export**', unsafe_allow_html=True)
st.caption("Exports respect the filters above. The CRM CSV uses HubSpot import column names and puts the score rationale in *Notes*.")
e1, e2, e3, _ = st.columns([1, 1, 1, 2])
e1.download_button("⬇ Filtered CSV", to_csv_bytes(view), "leadlens_leads.csv", "text/csv", use_container_width=True)
e2.download_button("⬇ CRM-ready CSV", to_csv_bytes(view, crm=True), "leadlens_hubspot.csv", "text/csv", use_container_width=True)
e3.download_button(
    "⬇ Excel (all + Hot sheet)", to_excel_bytes(view), "leadlens_leads.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True,
)

with st.expander("Recent runs (SQLite)"):
    runs = get_cache().recent_runs()
    if runs:
        rdf = pd.DataFrame(runs)
        rdf["created_at"] = pd.to_datetime(rdf["created_at"], unit="s").dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(rdf, hide_index=True, use_container_width=True)
