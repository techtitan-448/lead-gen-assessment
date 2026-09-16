from leadlens.dedupe import dedupe, merge
from leadlens.models import Lead


def test_merge_keeps_richest_and_backfills():
    a = Lead(company="Acme HVAC", website="https://acme.com", email=None, phone="2125550187")
    b = Lead(company="ACME HVAC Inc", website="acme.com", email="j@acme.com")
    m = merge(a, b)
    assert m.email == "j@acme.com" and m.phone == "2125550187"


def test_dedupe_by_domain_then_fuzzy_name():
    leads = [
        Lead(company="Acme HVAC, Inc.", website="https://www.acme-hvac.com/"),
        Lead(company="ACME HVAC", website="acme-hvac.com"),
        Lead(company="Acme HVAC Inc", city="Austin"),                     # no domain -> fuzzy
        Lead(company="Totally Different Co", city="Austin"),
        Lead(company="Beta Plumbing", email="x@gmail.com"),                # free-mail ignored
        Lead(company="Beta Plumbing LLC", email="y@gmail.com"),
    ]
    uniques, counts = dedupe(leads)
    names = sorted(u.company for u in uniques)
    assert len(uniques) == 3, names
    assert counts[0] == 3
