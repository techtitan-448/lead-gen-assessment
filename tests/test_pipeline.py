import pandas as pd

from leadlens.export import HUBSPOT_COLUMNS, to_csv_bytes, to_dataframe, to_excel_bytes
from leadlens.pipeline import map_columns, run_pipeline
from leadlens.storage import Cache


def test_column_aliases_are_flexible():
    df = pd.DataFrame(columns=["Business Name", "URL", "Est. Revenue", "Headcount", "E-mail", "Random"])
    m = map_columns(df)
    assert m == {"company": "Business Name", "website": "URL", "revenue": "Est. Revenue",
                 "employees": "Headcount", "email": "E-mail"}


def test_pipeline_on_sample_dataset_offline():
    df = pd.read_csv("data/sample_leads.csv")
    r = run_pipeline(df, cache=Cache(":memory:"), enrich=False, check_mx=False)
    assert r.rows_in == len(df)
    assert r.duplicates_removed >= 10
    assert r.scored[0].fit_score >= r.scored[-1].fit_score
    out = to_dataframe(r.scored)
    assert len(out) == r.rows_after_dedupe
    crm = to_csv_bytes(out, crm=True).decode()
    assert crm.splitlines()[0].startswith("Company name,Company domain name")
    assert len(to_excel_bytes(out)) > 1000
    assert set(HUBSPOT_COLUMNS) - set(out.columns) == set()
