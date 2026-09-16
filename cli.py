"""LeadLens command line.

    python cli.py run data/sample_leads.csv                # full pipeline, writes data/output_<name>.csv
    python cli.py run leads.csv --no-enrich --no-mx        # offline mode
    python cli.py run leads.csv --crm --xlsx --top 25      # HubSpot CSV + Excel, print top 25
    python cli.py inspect leads.csv "Summit Electric"      # explain one lead's score
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

import pandas as pd

from leadlens.export import to_csv_bytes, to_dataframe, to_excel_bytes
from leadlens.models import ICPConfig
from leadlens.pipeline import DEFAULT_ICP, run_pipeline
from leadlens.storage import Cache

warnings.filterwarnings("ignore")


def _load(path: str) -> pd.DataFrame:
    return pd.read_excel(path) if path.lower().endswith("xlsx") else pd.read_csv(path)


def _run(args) -> None:
    df = _load(args.input)
    icp = ICPConfig.from_yaml(args.icp)
    res = run_pipeline(
        df, icp=icp, cache=Cache(), enrich=not args.no_enrich, check_mx=not args.no_mx,
        progress=lambda m, f: print(f"  [{f:>4.0%}] {m}", file=sys.stderr), source=os.path.basename(args.input),
    )
    table = to_dataframe(res.scored)
    tc = res.tier_counts
    print(f"\n{res.rows_in} rows → {res.rows_after_dedupe} unique ({res.duplicates_removed} duplicates merged) in {res.elapsed_s}s")
    print(f"Hot {tc['Hot']} · Warm {tc['Warm']} · Cold {tc['Cold']} · verified emails {int(table['email_verified'].sum())}")
    print(f"Stages: {res.stage_times}\n")
    cols = ["fit_score", "tier", "company", "industry", "country", "employees", "email", "email_verified", "phone_e164"]
    with pd.option_context("display.width", 200, "display.max_colwidth", 32):
        print(table[cols].head(args.top).to_string(index=False))
    stem = os.path.splitext(os.path.basename(args.input))[0]
    out_dir = args.out or "data"
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"output_{stem}.csv")
    open(p, "wb").write(to_csv_bytes(table))
    written = [p]
    if args.crm:
        p = os.path.join(out_dir, f"output_{stem}_hubspot.csv")
        open(p, "wb").write(to_csv_bytes(table, crm=True))
        written.append(p)
    if args.xlsx:
        p = os.path.join(out_dir, f"output_{stem}.xlsx")
        open(p, "wb").write(to_excel_bytes(table))
        written.append(p)
    print("\nWrote:", *written, sep="\n  ")


def _inspect(args) -> None:
    df = _load(args.input)
    res = run_pipeline(df, icp=ICPConfig.from_yaml(args.icp), cache=Cache(), enrich=not args.no_enrich, check_mx=not args.no_mx)
    q = args.query.lower()
    hits = [s for s in res.scored if q in (s.lead.company or "").lower() or q in (s.lead.domain or "")]
    if not hits:
        sys.exit(f"No lead matching '{args.query}'")
    s = hits[0]
    print(f"\n{s.lead.company} — {s.tier} · {s.fit_score}/100  (merged from {s.merged_from} rows)")
    for b in sorted(s.breakdown, key=lambda b: -b.points):
        print(f"  {b.points:5.1f}/{b.weight:<3.0f} {b.component:<18} {b.reason}")
    if s.flags:
        print("  flags:", ", ".join(s.flags))
    if s.enrichment and s.enrichment.reachable:
        e = s.enrichment
        print(f"  site: {e.title!r} | emails {e.emails_found} | phones {e.phones_found} | tech {e.tech_hints}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="leadlens", description="Dedupe, validate, enrich and score scraped leads.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("run", _run), ("inspect", _inspect)):
        p = sub.add_parser(name)
        p.add_argument("input", help="CSV or XLSX file")
        if name == "inspect":
            p.add_argument("query", help="company name or domain substring")
        p.add_argument("--icp", default=DEFAULT_ICP)
        p.add_argument("--no-enrich", action="store_true", help="skip website enrichment")
        p.add_argument("--no-mx", action="store_true", help="skip DNS MX verification")
        if name == "run":
            p.add_argument("--top", type=int, default=15)
            p.add_argument("--out", help="output directory (default: data/)")
            p.add_argument("--crm", action="store_true", help="also write HubSpot-ready CSV")
            p.add_argument("--xlsx", action="store_true", help="also write Excel workbook")
        p.set_defaults(fn=fn)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
