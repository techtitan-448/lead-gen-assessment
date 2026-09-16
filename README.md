# LeadLens — lead quality pipeline for SaaSquatch-style scrapes

> **Caprae Capital · AI-Readiness Pre-Screening Challenge · Full Stack Developer**
> Quality-First submission, ~5 hours of code, 100 % Python.

Turn a raw scraped lead list into a **ranked, deduplicated, verified, enriched shortlist** — with a
plain-English reason for every score — so a searcher or sales rep spends credits and outreach time
only on leads that matter.

```
raw CSV ──▶ dedupe ──▶ validate ──▶ enrich ──▶ score ──▶ ranked shortlist ──▶ CRM-ready export
            (domain +   (email MX,   (website:    (explainable   (Hot / Warm / Cold,   (HubSpot CSV,
             fuzzy name) phone E.164) contacts,    ICP fit 0–100)  "why this score?")   Excel, API)
                                      socials, tech)
```

---

## 1. Why this feature (business rationale)

SaaSquatch Leads is very good at the *top* of the funnel: search by industry/geo, estimate revenue and
headcount, and enrich contact details on a per-credit basis. Watching the tool and its demo, the
biggest leak in value is *after* the scrape:

| Pain in the raw export | What it costs the user | LeadLens answer |
|---|---|---|
| Same company appears 2–3× across scrapes (different casing, `www.`, `Inc.`) | Wasted credits, duplicate outreach, CRM pollution | **Dedupe** by canonical domain, then fuzzy company-name within the same city |
| Emails are unverified; `info@` and Gmail addresses mixed in with owners' | Bounces hurt sender reputation; reps chase dead inboxes | **Validate**: syntax + DNS MX; flag generic and free-mail inboxes; normalise phones to E.164 |
| Lists are undifferentiated — 500 rows, no ordering | Reps cherry-pick by gut feel; the best targets get buried | **Score** every lead 0–100 against an editable Ideal Customer Profile (industry, geography, size band, contact quality, web presence, completeness) |
| No context beyond a name and a number | Every call starts cold | **Enrich** from the company's own website: description, public contact email/phone, socials, careers page (growth signal), tech stack hints |
| "Why is this lead #1?" has no answer | Managers can't tune it; reps don't trust it | Every score ships with a **breakdown and reasons**; weights live in `config/icp.yaml` |
| Export is a flat CSV | Manual column-mapping into the CRM | **CRM-ready CSV** (HubSpot importer column names, rationale in *Notes*), Excel with a *Hot only* sheet, and a JSON **API** for automation |

The default ICP is tuned for Caprae's world — **SMB acquisition targets for ETA / search-fund
buyers** (10–200 employees, $1–30 M revenue, owner-operated service & niche-software businesses in the
US/Canada) — but it is a 40-line YAML file, so a sales team selling SaaS into dental practices can retune
it in a minute without touching code.

## 2. Quick start

```bash
git clone <your-fork-url> leadlens && cd leadlens
python3 -m venv .venv && source .venv/bin/activate      # Python 3.9+ (tested on 3.9.6 and 3.11)
pip install -r requirements.txt

# UI
streamlit run app.py                     # http://localhost:8501

# CLI
python cli.py run data/sample_leads.csv --no-enrich --no-mx --crm --xlsx   # offline demo, ~0.1 s
python cli.py run data/sample_leads_live.csv                              # live enrichment on 8 real sites
python cli.py inspect data/sample_leads.csv "summit"                      # explain one lead

# API
uvicorn api:app --reload                 # http://127.0.0.1:8000/docs

# Tests
pytest -q                                # 12 tests, fully offline (mocked HTTP)

# Notebook
jupyter notebook notebooks/demo.ipynb    # already executed — outputs are committed
```

**Docker:** `docker build -t leadlens . && docker run -p 8501:8501 leadlens`

### Using your own data
Upload any CSV/XLSX. Column names are matched by alias (`Company Name` / `Business` / `Org`,
`Website` / `URL` / `Domain`, `Est. Revenue` / `Annual Revenue` / `Sales`, `Headcount` / `Employees`,
`Owner` / `Contact` / `CEO`, …). Unrecognised columns are preserved as `extra`. See
`COLUMN_ALIASES` in [`leadlens/pipeline.py`](leadlens/pipeline.py).

## 3. What's in the box

```
leadlens/            core package (pure Python, no framework coupling)
  normalize.py       canonical domain / company name / phone (E.164) / "$2.5M" → 2 500 000
  dedupe.py          domain identity → fuzzy name (rapidfuzz), richest-record merge with back-fill
  validate.py        email syntax + MX (cached), generic/free-mail detection, phone validity
  enrich.py          async httpx crawler: robots.txt, UA, 1 req/s/host, bounded concurrency, SQLite cache
  score.py           six explainable components → weighted 0–100 + reasons + flags
  pipeline.py        column mapping, orchestration, timing, run log
  export.py          DataFrame / CSV / HubSpot CSV / Excel
  storage.py         SQLite cache (enrichment, MX, run history)
app.py               Streamlit UI (4 numbered steps: Load → Run → Review → Export)
api.py               FastAPI: POST /score (JSON), POST /score/csv (file), GET /health
cli.py               run / inspect
config/icp.yaml      Ideal Customer Profile — weights, industries, geography, size bands, tiers
data/                sample_leads.csv (82 synthetic rows, 19 planted duplicates), sample_leads_live.csv, make_sample.py
notebooks/demo.ipynb executed walkthrough
tests/               12 pytest cases incl. mocked-network enrichment
```

## 4. UX design choices

* **One page, four numbered steps, top to bottom.** No tabs to discover, no settings buried behind
  modals. The primary action is the only blue button on the page and is disabled until there is data.
* **KPI tiles answer the first three questions a rep asks**: how many rows, how many were junk
  (duplicates), how many contacts can I actually email — then how many are Hot.
* **Ranked table with a progress-bar score column** so ordering is visible at a glance; checkbox
  columns for *email ok* / *site live*; a *Merged* column so users see the dedupe working.
* **Filters mirror how people work a list**: tier, minimum score, industry, country, and a
  contact-readiness selector (*Verified email / Has phone / Owner named*). Exports respect filters,
  so "give me Hot leads with a verified email as a HubSpot CSV" is three clicks.
* **"Why this score?" inspector** turns the number into trust: reasons sorted by contribution, a
  per-component bar chart, badges for verified/valid/live, and the raw website findings.
* **Weights and size bands are sliders in the sidebar** — a manager can tune the ICP live and
  re-run; the defaults come from `config/icp.yaml` so tuning is reproducible.
* **Restrained visual system**: one accent colour (blue) for actions, semantic colours only for
  tiers (red = Hot, amber = Warm, slate = Cold) and flags (red chips) vs. confirmations (green chips).
  System font, generous whitespace, no decorative elements.
* **Graceful degradation**: enrichment and MX can be switched off for offline use; unreachable
  sites and DNS timeouts produce *unknown* (partial credit), never crashes or zero scores.

## 5. Backend architecture

### 5.1 Local (what runs today)

| Concern | Implementation |
|---|---|
| Language / runtime | Python 3.9+; all I/O typed with **pydantic v2** models |
| Data processing | **pandas** for I/O and filtering; scoring is per-row pure functions (trivially vectorisable) |
| Scraping | **httpx** async client, bounded semaphore (8), per-host delay 1 s, 8 s timeout, HTTPS→HTTP fallback, `robots.txt` honoured via `urllib.robotparser`; **BeautifulSoup + lxml** parsing |
| Validation | **email-validator** (syntax/IDN), **dnspython** MX→A fallback, **phonenumbers** (E.164) |
| Dedupe | **tldextract** (offline snapshot) for canonical domains, **rapidfuzz** `token_set_ratio ≥ 90` for names |
| Storage / cache | **SQLite** (`data/leadlens.db`, WAL not needed at this scale): `enrichment_cache` (7-day TTL, JSON payload), `mx_cache`, `runs` (audit trail shown in the UI) |
| UI | **Streamlit** with `@st.cache_resource` for the DB handle; results kept in session state |
| API | **FastAPI** + uvicorn; `POST /score` (≤ 500 leads) and `POST /score/csv`; OpenAPI docs auto-generated |
| Tests | **pytest**; network mocked with `httpx.MockTransport`, DNS off |

### 5.2 Caching & performance

* **Domain-level enrichment cache** — the expensive step is fetching pages; 8 live sites take ~4.7 s
  cold and **0.02 s warm** (measured). Re-running with new weights costs nothing.
* **MX memoised per domain**, not per email — 300 leads at 40 companies = 40 lookups.
* **Dedupe first** so validation/enrichment run on unique companies only (23 % fewer calls on the sample).
* **Concurrency with courtesy** — global semaphore + per-host sleep keeps throughput high without
  hammering any one site. 1 000 unique domains ≈ 2–3 min cold on a laptop.
* Scoring is O(n) pure Python; 10 k rows score in well under a second.

### 5.3 Production target (AWS)

```
                     ┌──────────────── AWS ─────────────────────────────────────┐
 browser ──HTTPS──▶  │ CloudFront ─▶ App Runner (Streamlit container, 1–4 inst.) │
 CRM / Zapier ─────▶ │ API Gateway ─▶ Lambda (FastAPI via Mangum)                │
                     │        │                 │                                │
                     │        ▼                 ▼                                │
                     │   SQS "enrich" queue ─▶ Lambda / Fargate workers (httpx)   │
                     │        │                 │                                │
                     │        ▼                 ▼                                │
                     │   RDS PostgreSQL   ElastiCache Redis    S3 (uploads,      │
                     │   (leads, runs)    (enrichment + MX,    exports, datasets)│
                     │                     7-day TTL)                            │
                     └──────────────────────────────────────────────────────────┘
```

| Concern | Choice | Rationale |
|---|---|---|
| **Database** | **PostgreSQL on Amazon RDS** (same schema as the SQLite tables + `leads`, `scores` with JSONB `breakdown`) | Relational fits the data; JSONB keeps the rationale queryable; RDS handles backups/HA |
| **Cache** | **Redis (ElastiCache)** keyed `enrich:{domain}` / `mx:{domain}`, TTL 7 d | Shared across workers; the SQLite `Cache` class already isolates this behind `get_*/put_*` |
| **Hosting** | UI: **App Runner** (container, scales to zero-ish, HTTPS out of the box). API: **Lambda + API Gateway** (serverless — bursty CRM webhooks). Static assets/exports: **S3 + CloudFront** | Streamlit needs a long-lived process (websocket) → container; the API is stateless → serverless |
| **Async enrichment** | **SQS** queue + worker Lambdas (or Fargate for long crawls) | Large uploads shouldn't block a request; results stream back to the UI via polling on `runs` |
| **Anti-blocking** | Rotating residential proxy pool behind an env var (`HTTP_PROXY`), UA rotation, exponential back-off on 429/403; CAPTCHA'd pages are *skipped and flagged*, never solved | Keeps collection ethical while staying resilient |
| **Deployment** | `Dockerfile` → **GitHub Actions** (ruff + pytest on PR; on `main`: build → push to **ECR** → App Runner auto-deploy; Lambda via SAM). Secrets in **SSM Parameter Store** | One image, two entrypoints (`streamlit run` / `uvicorn`) |
| **Observability** | CloudWatch logs + a `runs` dashboard (rows in/out, tier mix, cache-hit ratio, p95 fetch time) | Cache-hit ratio is the cost lever |
| **Cost** | ≈ $40–60/mo idle (App Runner min instance + micro RDS + Redis t4g.micro); enrichment cost is bandwidth only — no paid data vendor in the loop | |

## 6. Ethical data collection

* Only **business-level, publicly published** information is collected (company site title/description,
  the contact email/phone the company itself puts on its homepage, social links). No personal
  profiles are crawled.
* `robots.txt` is fetched first and **honoured**; disallowed sites are marked "blocked (respected)".
* Descriptive **User-Agent** identifies the bot; **1 request/second/host**; short timeouts; 7-day
  cache so sites are not re-hit.
* Free-mail (Gmail etc.) and generic (`info@`) inboxes are **flagged** so reps can respect
  personal-address boundaries and opt-out norms (CAN-SPAM / GDPR legitimate-interest posture).
* Sample dataset is **synthetic** (`.test` reserved TLD, 555-01XX fictional numbers, generated names).

## 7. Results on the sample

| Metric | Value |
|---|---|
| Input rows | 82 (synthetic, 12 planted duplicate pairs + formatting noise) |
| Unique after dedupe | 63 (19 rows merged, 23 %) |
| Hot / Warm / Cold | 22 / 37 / 4 with default ICP |
| Offline run time | ~0.1 s |
| Live enrichment (8 real SaaS sites) | 4.7 s cold → 0.02 s cached; 2 verified emails discovered on-site |

## 8. What I'd build next (roadmap)

1. **Owner-signal enrichment** — LinkedIn/state business registry lookups (years in business, owner
   age band) to surface *succession-ready* SMBs, the highest-value ETA signal.
2. **Feedback loop** — thumbs-up/down on leads in the UI feeds a logistic-regression layer on top of
   the rule score (keeping explanations via coefficients).
3. **Direct CRM push** — HubSpot/Pipedrive OAuth instead of CSV.
4. **Scheduled re-scoring** — nightly re-validate Hot leads' MX and site liveness; alert on changes.
5. **Multi-source enrichment** — Google Maps ratings/review counts and Crunchbase-style funding as
   extra components.

## 9. Video & submission

See [`SUBMISSION.md`](SUBMISSION.md) for the 2-minute video script outline and the email checklist.
