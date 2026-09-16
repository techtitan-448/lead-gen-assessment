"""Canonicalisation helpers: domains, company names, phones, numbers."""
from __future__ import annotations

import re
from typing import Optional

import phonenumbers
import tldextract

# Suffixes that carry no identity information for matching purposes.
_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|"
    r"plc|gmbh|pty|llp|lp|group|holdings|the)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# Offline extractor: never hit the network for the public-suffix list.
_extract = tldextract.TLDExtract(suffix_list_urls=(), fallback_to_snapshot=True)


def canonical_domain(value: Optional[str]) -> Optional[str]:
    """'https://www.Acme-HVAC.com/about?x=1' -> 'acme-hvac.com'. Emails work too."""
    if not value:
        return None
    value = value.strip().lower()
    if "@" in value and "://" not in value:
        value = value.split("@", 1)[1]
    ext = _extract(value)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    # Unknown / reserved TLD (.test, .invalid, .local): fall back to last two labels
    host = re.sub(r"^[a-z]+://", "", value).split("/")[0].split(":")[0]
    labels = [l for l in host.split(".") if l]
    if len(labels) >= 2 and labels[-1].isalpha():
        return ".".join(labels[-2:])
    return None


def canonical_company(name: Optional[str]) -> str:
    """Strip legal suffixes/punctuation so 'Acme HVAC, Inc.' == 'ACME hvac'."""
    if not name:
        return ""
    s = name.lower()
    s = s.replace("&", " and ")
    s = _COMPANY_SUFFIXES.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    return _WS.sub(" ", s).strip()


def normalize_phone(raw: Optional[str], default_region: str = "US") -> Optional[str]:
    """Return E.164 ('+12125551234') or None if the number is not valid."""
    if not raw:
        return None
    try:
        num = phonenumbers.parse(str(raw), default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


_NUM = re.compile(r"[-+]?\d[\d,]*\.?\d*")
_MULT = {"k": 1e3, "m": 1e6, "mm": 1e6, "b": 1e9, "bn": 1e9}


def parse_number(value) -> Optional[float]:
    """Accepts 150, '150', '1,500', '$2.5M', '10-50' (midpoint), '500+'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None  # NaN guard
    s = str(value).strip().lower().replace("$", "").replace("usd", "")
    if not s or s in {"nan", "none", "null", "n/a", "-"}:
        return None
    if "-" in s and not s.startswith("-"):
        lo, hi = s.split("-", 1)
        a, b = parse_number(lo), parse_number(hi)
        if a is not None and b is not None:
            return (a + b) / 2
    m = _NUM.search(s)
    if not m:
        return None
    n = float(m.group().replace(",", ""))
    suffix = s[m.end():].strip().rstrip("+").strip()
    return n * _MULT.get(suffix, 1)


def normalize_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    e = str(email).strip().lower()
    return e if "@" in e else None


def normalize_website(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    u = str(url).strip()
    if not u or u.lower() in {"nan", "none", "n/a"}:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com",
    "live.com", "msn.com", "protonmail.com", "me.com", "mail.com", "ymail.com",
}


def email_domain(email: Optional[str]) -> Optional[str]:
    """Company domain implied by an email, or None for free-mail providers."""
    dom = canonical_domain(email) if email and "@" in email else None
    return None if dom in FREE_MAIL_DOMAINS else dom
