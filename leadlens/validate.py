"""Contact validation: email syntax + MX, phone validity, website sanity.

Network calls (DNS) are cached per domain and fail *soft*: a DNS timeout
returns None (unknown), never False, so a flaky network can't tank a score.
"""
from __future__ import annotations

from typing import Optional

from email_validator import EmailNotValidError, validate_email

from .models import Lead, Validation
from .normalize import FREE_MAIL_DOMAINS, canonical_domain, normalize_phone
from .storage import Cache

GENERIC_LOCALPARTS = {
    "info", "sales", "contact", "hello", "support", "admin", "office", "team",
    "marketing", "help", "enquiries", "inquiries", "mail", "service", "billing",
}


def check_mx(domain: str, cache: Optional[Cache] = None, timeout: float = 3.0) -> Optional[bool]:
    """True/False if resolvable; None if DNS unavailable (treated as unknown)."""
    if cache is not None:
        hit = cache.get_mx(domain)
        if hit is not None:
            return hit
    try:
        import dns.resolver

        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        try:
            answers = resolver.resolve(domain, "MX")
            has_mx = len(answers) > 0
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            # Some domains accept mail on their A record; treat A-only as weak-true.
            try:
                resolver.resolve(domain, "A")
                has_mx = True
            except Exception:
                has_mx = False
    except Exception:
        return None  # timeout / no network -> unknown
    if cache is not None:
        cache.put_mx(domain, has_mx)
    return has_mx


def validate_lead(lead: Lead, cache: Optional[Cache] = None, do_mx: bool = True) -> Validation:
    v = Validation()

    # Email
    if lead.email:
        try:
            info = validate_email(lead.email, check_deliverability=False, test_environment=True)
            lead.email = info.normalized
            v.email_syntax_ok = True
            local, _, dom = info.normalized.partition("@")
            v.email_is_generic = local.lower() in GENERIC_LOCALPARTS
            v.email_is_freemail = dom.lower() in FREE_MAIL_DOMAINS
            if do_mx:
                v.email_mx_ok = check_mx(dom, cache)
        except EmailNotValidError:
            v.email_syntax_ok = False
            v.email_mx_ok = False
    # Phone
    if lead.phone:
        e164 = normalize_phone(lead.phone)
        v.phone_ok = e164 is not None
        v.phone_e164 = e164
    # Website — structural check only here; reachability comes from enrichment
    if lead.website or lead.domain:
        v.website_ok = canonical_domain(lead.website or lead.domain) is not None
    return v
