import httpx

from leadlens.enrich import Enricher, parse_html
from leadlens.models import ICPConfig, Lead
from leadlens.pipeline import DEFAULT_ICP
from leadlens.score import score_lead
from leadlens.storage import Cache
from leadlens.validate import validate_lead

HTML = """<html><head><title>Summit Heating &amp; Air</title>
<meta name="description" content="Family-owned HVAC contractor serving Austin since 1998."></head>
<body><a href="mailto:office@summit-heating.test">Email us</a>
<a href="tel:+1-512-555-0100">Call</a>
<a href="https://www.facebook.com/summitheating">FB</a><a href="/careers">Join our team</a>
<script src="/wp-content/themes/x.js"></script></body></html>"""


def test_parse_html_extracts_signals():
    e = parse_html("summit-heating.test", HTML)
    assert e.title.startswith("Summit Heating")
    assert "HVAC" in e.description
    assert e.emails_found == ["office@summit-heating.test"]
    assert e.phones_found == ["+15125550100"]
    assert "facebook" in e.socials and e.has_careers_page
    assert "WordPress" in e.tech_hints


def _mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            if request.url.host == "blocked.test":
                return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
            return httpx.Response(404)
        if request.url.host == "down.test":
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
    return httpx.MockTransport(handler)


def test_enricher_respects_robots_caches_and_handles_errors():
    cache = Cache(":memory:")
    enr = Enricher(cache=cache, transport=_mock_transport(), per_host_delay=0)
    out = enr.enrich_many(["summit-heating.test", "blocked.test", "down.test"])
    assert out["summit-heating.test"].reachable and out["summit-heating.test"].emails_found
    assert out["blocked.test"].robots_blocked and not out["blocked.test"].reachable
    assert out["down.test"].error == "ConnectError"
    again = enr.enrich_many(["summit-heating.test"])
    assert again["summit-heating.test"].from_cache


def test_score_is_explainable_and_bounded():
    icp = ICPConfig.from_yaml(DEFAULT_ICP)
    good = Lead(company="Summit Heating", website="summit-heating.test", domain="summit-heating.test",
                industry="HVAC", country="United States", employees=45, revenue=6_000_000,
                owner_name="Maria Alvarez", email="malvarez@summit-heating.test", phone="5125550100")
    bad = Lead(company="Moon Crypto", industry="Crypto Exchange", country="Cayman Islands")
    e = parse_html("summit-heating.test", HTML)
    sg = score_lead(good, validate_lead(good, do_mx=False), e, icp)
    sb = score_lead(bad, validate_lead(bad, do_mx=False), None, icp)
    assert 0 <= sb.fit_score < sg.fit_score <= 100
    assert sg.tier == "Hot" and sb.tier == "Cold"
    assert any("Target industry" in r for r in sg.reasons)
    assert any("Excluded industry" in r for r in sb.reasons)
    assert abs(sum(b.points for b in sg.breakdown) - sg.fit_score) < 0.2
