"""Generate a synthetic, messy lead list that mimics a SaaSquatch-style export.

Everything here is fictional: company names are invented, domains use the
reserved `.test` TLD (RFC 2606) so they can never resolve, and owner names are
generated. Safe to publish; safe to run offline.
"""
from __future__ import annotations

import csv
import random

random.seed(42)

INDUSTRIES = [
    ("HVAC", 1.0), ("Plumbing", 1.0), ("Electrical Contractor", 1.0), ("Landscaping", 1.0),
    ("Precision Manufacturing", 1.0), ("Logistics & Freight", 1.0), ("Dental Practice", 1.0),
    ("Veterinary Clinic", 1.0), ("Accounting Firm", 1.0), ("Managed IT Services", 1.0),
    ("B2B SaaS", 1.0), ("Commercial Construction", 0.6), ("Marketing Agency", 0.6),
    ("Staffing", 0.6), ("Insurance Brokerage", 0.6), ("Real Estate", 0.6),
    ("Restaurant", 0.2), ("Retail Boutique", 0.2), ("Crypto Exchange", 0.0), ("Fitness Studio", 0.2),
]
CITIES = [
    ("Austin", "Texas", "United States"), ("Tampa", "Florida", "United States"), ("Denver", "Colorado", "United States"),
    ("Columbus", "Ohio", "United States"), ("Phoenix", "Arizona", "United States"), ("Raleigh", "North Carolina", "United States"),
    ("Nashville", "Tennessee", "United States"), ("Boise", "Idaho", "United States"), ("Toronto", "Ontario", "Canada"),
    ("Calgary", "Alberta", "Canada"), ("Manchester", "", "United Kingdom"), ("Sydney", "NSW", "Australia"),
]
FIRST = ["Maria", "James", "Priya", "Daniel", "Aisha", "Tom", "Elena", "Marcus", "Grace", "Omar", "Linda", "Sam", "Yuki", "Carlos", "Nina"]
LAST = ["Alvarez", "Chen", "Patel", "Okafor", "Nguyen", "Brooks", "Kowalski", "Reyes", "Schmidt", "Hassan", "Fischer", "Murphy", "Tanaka", "Silva", "Ross"]
WORDS = ["Summit", "Blue Ridge", "Ironclad", "Northstar", "Pioneer", "Cedar", "Keystone", "Harbor", "Evergreen", "Granite",
         "Lakeside", "Redwood", "Beacon", "Atlas", "Prairie", "Copper", "Falcon", "Meridian", "Sterling", "Cascade"]
SUFFIX = {"HVAC": "Heating & Air", "Plumbing": "Plumbing", "Electrical Contractor": "Electric", "Landscaping": "Landscapes",
          "Precision Manufacturing": "Machine Works", "Logistics & Freight": "Logistics", "Dental Practice": "Dental",
          "Veterinary Clinic": "Animal Hospital", "Accounting Firm": "CPA Group", "Managed IT Services": "IT Solutions",
          "B2B SaaS": "Software", "Commercial Construction": "Builders", "Marketing Agency": "Media", "Staffing": "Staffing",
          "Insurance Brokerage": "Insurance", "Real Estate": "Realty", "Restaurant": "Kitchen", "Retail Boutique": "Boutique",
          "Crypto Exchange": "Crypto", "Fitness Studio": "Fitness"}
TITLES = ["Owner", "CEO", "Founder", "President", "Managing Partner", "General Manager"]


def fmt_phone(n: str, style: int) -> str:
    return [f"({n[:3]}) {n[3:6]}-{n[6:]}", f"{n[:3]}-{n[3:6]}-{n[6:]}", f"+1 {n[:3]} {n[3:6]} {n[6:]}", n, f"{n[:3]}.{n[3:6]}.{n[6:]}"][style]


def fmt_rev(v: float, style: int) -> str:
    return [f"${v/1e6:.1f}M", f"{int(v):,}", f"{v/1e6:.2f}M", str(int(v)), f"${int(v):,}"][style]


def fmt_emp(v: int, style: int) -> str:
    if style == 0:
        return str(v)
    lo = max(1, (v // 10) * 10)
    return f"{lo}-{lo + 40}" if style == 1 else f"{v}+"


rows = []
for i in range(70):
    ind, _ = random.choice(INDUSTRIES)
    city, state, country = random.choice(CITIES)
    w = random.choice(WORDS)
    company = f"{w} {SUFFIX[ind]}"
    dom = (w + "-" + SUFFIX[ind].split()[0]).lower().replace("&", "and").replace(" ", "-") + ".test"
    emp = int(random.lognormvariate(3.3, 0.9))
    rev = emp * random.uniform(90_000, 220_000)
    first, last = random.choice(FIRST), random.choice(LAST)
    email_style = random.random()
    if email_style < 0.45:
        email = f"{first[0].lower()}{last.lower()}@{dom}"
    elif email_style < 0.65:
        email = f"info@{dom}"
    elif email_style < 0.75:
        email = f"{first.lower()}.{last.lower()}@gmail.com"
    elif email_style < 0.82:
        email = f"{first.lower()}{last.lower()}@@{dom}"  # broken on purpose
    else:
        email = ""
    # Real US area codes + the reserved 555-01XX fictional block: valid format, never a real line.
    phone = random.choice(["212", "305", "512", "614", "720", "813", "919", "615", "208", "480"]) + "555" + f"{random.randrange(100, 200):04d}"
    row = {
        "Company Name": company + random.choice(["", "", "", " LLC", ", Inc.", " Inc"]),
        "Website": random.choice([f"https://www.{dom}", f"http://{dom}", dom, f"{dom}/", f"www.{dom}/about-us", ""]) if random.random() < 0.9 else "",
        "Industry": ind if random.random() < 0.85 else "",
        "City": city, "State": state, "Country": random.choice([country, country, country.upper(), "USA" if country == "United States" else country]),
        "Employees": fmt_emp(emp, random.randrange(3)) if random.random() < 0.8 else "",
        "Est. Revenue": fmt_rev(rev, random.randrange(5)) if random.random() < 0.7 else "",
        "Owner": f"{first} {last}" if random.random() < 0.7 else "",
        "Title": random.choice(TITLES) if random.random() < 0.6 else "",
        "Email": email,
        "Phone": fmt_phone(phone, random.randrange(5)) if random.random() < 0.75 else "",
        "LinkedIn": f"https://www.linkedin.com/company/{dom.split('.')[0]}" if random.random() < 0.4 else "",
        "Source": random.choice(["saasquatch", "google_maps", "yelp", "manual"]),
    }
    rows.append(row)

# Inject duplicates with different formatting / partial info (what real scrapes look like)
for base in random.sample(rows, 12):
    d = dict(base)
    d["Company Name"] = base["Company Name"].replace(" LLC", "").replace(", Inc.", "").upper() if random.random() < 0.5 else base["Company Name"] + " Inc."
    d["Website"] = ("https://" + base["Website"].replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")) if base["Website"] else ""
    d["Email"] = base["Email"] if random.random() < 0.5 else ""
    d["Phone"] = "" if random.random() < 0.5 else base["Phone"]
    d["Employees"] = "" if random.random() < 0.6 else base["Employees"]
    d["Source"] = "linkedin_scrape"
    rows.append(d)
random.shuffle(rows)

with open("data/sample_leads.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"wrote {len(rows)} rows")
