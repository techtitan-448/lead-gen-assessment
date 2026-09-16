# Submission pack — Full Stack Developer handbook

Everything the handbook asks for beyond the code, in one place. Items marked **[YOU]** need your
personal input before sending; everything else is drafted from the handbook and this repo.

---

## 1. Email

- **To:** recruiting@capraecapital.com
- **Subject (exact format):** `Full Stack Developer - Handbook Submission - <Your Name>`
- **Attach / link:**
  - [ ] GitHub repository URL (public, or add access) — **[YOU]** push this folder
  - [ ] 1–2 minute video link (Loom / YouTube unlisted / Drive) — **[YOU]** record
  - [ ] Demo: link to `notebooks/demo.ipynb` on GitHub (renders with outputs) and/or a hosted Streamlit URL
  - [ ] Up-to-date resume (PDF) — **[YOU]**
  - [ ] Business-understanding answers (section 3 below, pasted in the email body or as PDF)
  - [ ] Employment-expectation confirmations (section 4)
  - [ ] Reapplicant questions (section 5) — only if you have applied before

## 2. Video script (target 1:45 – 2:00)

| t | Beat | On screen |
|---|------|-----------|
| 0:00–0:15 | **Problem.** "SaaSquatch is great at finding companies. But the export is a flat list: duplicates across scrapes, unverified emails, and no way to tell the best 20 leads from the other 480. Reps waste credits and outreach on junk." | Raw `sample_leads.csv` in the *Preview raw input* expander — point at duplicate rows & messy revenue formats |
| 0:15–0:30 | **What I built.** "LeadLens is a quality-first layer on top: dedupe → validate → enrich → score, with a reason for every score." | Header + the four numbered steps |
| 0:30–0:55 | **Run it.** Click *Run pipeline* on the synthetic sample. "82 rows in, 19 duplicates merged, 22 Hot leads. Every email was syntax- and MX-checked, phones normalised to E.164." | KPI tiles; ranked table with score bars |
| 0:55–1:20 | **Why this score.** Pick the top lead. "Six explainable components — industry fit, size band, contact quality… Weights are a YAML file, or sliders here, so a manager tunes it for their ICP in a minute. No black box." | Inspector: reasons + bar chart; drag a weight slider, re-run |
| 1:20–1:35 | **Live enrichment.** Switch to the live sample. "For real sites it reads the company's own homepage — description, public contact email, socials, a careers page as a growth signal — respecting robots.txt, one request per second, cached for seven days: 4.7 s cold, 0.02 s warm." | Live sample run; show a lead's *From the website* panel |
| 1:35–1:50 | **Into the workflow.** "Filter to Hot + verified email, export a HubSpot-ready CSV, or hit the FastAPI endpoint from Zapier." | Filters → download button; flash `/docs` page |
| 1:50–2:00 | **Why it matters for Caprae.** "Default ICP is SMB acquisition targets for searchers: 10–200 people, $1–30 M, owner-operated. Production: Postgres on RDS, Redis cache, App Runner + Lambda on AWS — all in the README." | README architecture diagram |

Tips: record at 1440×900, hide bookmarks bar, pre-run the live sample once so the cache is warm.

## 3. Business Understanding (3–4 paragraphs each) — **[YOU]** to finalise

> Draft these in your own voice. Below are the facts the handbook itself gives you, plus prompts.
> Read the linked founder post, webinar and Substack pieces before writing — the reviewers will
> notice whether you did.

### 3.1 What is Caprae's Mission?
Facts from the handbook to anchor on:
- Caprae's vision "extends beyond traditional investing — unlike most PE firms, which heavily rely on
  financial engineering, we're dedicated to transforming businesses through strategic initiatives."
- A critical piece is "helping companies embrace and leverage AI to unlock new growth opportunities."
- **SaaS + MaaS (M&A as a Service)** models "empower businesses post-acquisition."
- M&A is a **seven-year journey** — "the greater value creation is post-acquisition, not at the time
  of acquisition."
- "Although we are a finance firm, we are a founder/operator first company… culture remains."
- Practical AI → better decision-making, streamlined operations, lasting value; "turn good
  businesses into great ones."

Prompts: state the mission in one sentence, then explain *how* (operator-first, AI, MaaS), then
what that means for the businesses they buy, then why that's different.

### 3.2 Why do you want to work at Caprae Capital?
Prompts (be specific and personal):
- Which of **character, courage, creativity, crazy** do you identify with, with one concrete story?
- "Horsepower vs mileage" — what have you built/learned fast that shows horsepower?
- Why a founder/operator-first firm rather than a pure tech company? Why does building internal
  tools (SaaSQuatch, not renting) appeal to you?
- Tie back to this project: what did you enjoy about solving a real lead-quality problem?

### 3.3 How is Caprae changing the ETA space and broader PE?
Facts to anchor on:
- ETA = Entrepreneurship Through Acquisition (search funds: an individual raises capital to buy and
  run one SMB). Caprae supports searchers with sourcing tooling (SaaSQuatch) and post-close operating
  support (MaaS), rather than only capital.
- Traditional PE: leverage/financial engineering, short hold. Caprae: strategic transformation, AI
  adoption, 7-year horizon, value created after close.
- Builds its own tools; SaaSQuatch got 1,200+ users and 30+ paying customers in 3 weeks — a live
  product, not a side project.
- Reference material to cite: "Search Fund CEO Termination Issues", "#BleedandBuild", the founder's
  corporate-governance post.

Prompts: contrast old model → Caprae model; the role of software (sourcing + operations) in that
shift; what the searcher's experience becomes; what "broader PE" can learn.

## 4. Brief answers — **[YOU]**

| Question | Your answer |
|---|---|
| Current working status in the US? | |
| Willing and able to work a minimum of 40 hours/week? | |
| Why Caprae Capital? (1–2 sentences) | |
| Expected salary? | |

**Confirm you understand and accept:**
- [ ] 3-month probationary period.
- [ ] 9 AM – 6 PM EST with a 1-hour lunch during the initial 2–3 month training program; more
      flexible hours in your local time zone afterwards.
- [ ] Availability during off-hours for customer-service emergencies and time-sensitive projects
      (< ~2 hrs/week, if any) — state whether this is an issue.
- [ ] Able to start immediately if selected.

## 5. Reapplicants only — **[YOU]**
1. What do you think is Caprae's unfair advantage?
2. What does "To become a legend, you must take down legends" mean to you?
3. What do you think Caprae's culture will be like?

## 6. Pre-send checklist
- [ ] `pytest -q` passes (12 tests)
- [ ] `streamlit run app.py` boots; both samples run
- [ ] `notebooks/demo.ipynb` has outputs committed
- [ ] `data/leadlens.db` and `data/output_*` are **not** committed (see `.gitignore`)
- [ ] README setup instructions tested on a clean clone
- [ ] Video ≤ 2:00, audio clear, link permission = anyone with link
- [ ] Subject line exactly `Full Stack Developer - Handbook Submission - <Your Name>`
