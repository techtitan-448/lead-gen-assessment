from leadlens.normalize import canonical_company, canonical_domain, email_domain, normalize_phone, parse_number


def test_canonical_domain_variants():
    assert canonical_domain("https://www.Acme-HVAC.com/about?x=1") == "acme-hvac.com"
    assert canonical_domain("acme.co.uk") == "acme.co.uk"
    assert canonical_domain("john@mail.acme.io") == "acme.io"
    assert canonical_domain("summit-plumbing.test") == "summit-plumbing.test"
    assert canonical_domain("not a domain") is None
    assert canonical_domain("") is None


def test_email_domain_skips_freemail():
    assert email_domain("a@gmail.com") is None
    assert email_domain("a@acme.com") == "acme.com"


def test_canonical_company():
    assert canonical_company("The Acme HVAC, Inc.") == canonical_company("ACME hvac llc")
    assert canonical_company("Smith & Sons Plumbing Co.") == "smith and sons plumbing"


def test_phone():
    assert normalize_phone("(212) 555-0187") == "+12125550187"
    assert normalize_phone("212.555.0187") == "+12125550187"
    assert normalize_phone("12") is None


def test_parse_number():
    assert parse_number("$2.5M") == 2_500_000
    assert parse_number("1,500+") == 1500
    assert parse_number("10-50") == 30
    assert parse_number("n/a") is None
    assert parse_number(float("nan")) is None
