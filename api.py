"""LeadLens HTTP API (FastAPI) — the integration surface for CRMs / webhooks.

    uvicorn api:app --reload
    open http://127.0.0.1:8000/docs

POST /score      JSON list of leads -> scored leads (sync, small batches)
POST /score/csv  multipart CSV       -> scored CSV download
GET  /health     liveness + cache stats
"""
from __future__ import annotations

import io
import warnings
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from leadlens import __version__
from leadlens.export import to_csv_bytes, to_dataframe
from leadlens.models import ICPConfig, Lead
from leadlens.pipeline import DEFAULT_ICP, run_pipeline
from leadlens.storage import Cache

warnings.filterwarnings("ignore")

app = FastAPI(title="LeadLens API", version=__version__, description=__doc__)
_cache = Cache()
_icp = ICPConfig.from_yaml(DEFAULT_ICP)


class ScoreRequest(BaseModel):
    leads: List[Lead] = Field(..., min_length=1, max_length=500)
    enrich: bool = True
    check_mx: bool = True


class ScoredOut(BaseModel):
    fit_score: float
    tier: str
    company: Optional[str]
    domain: Optional[str]
    email: Optional[str]
    email_verified: bool
    phone: Optional[str]
    merged_from: int
    flags: List[str]
    reasons: List[str]


class ScoreResponse(BaseModel):
    rows_in: int
    rows_out: int
    duplicates_removed: int
    elapsed_s: float
    leads: List[ScoredOut]


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "icp": _icp.name, **_cache.stats()}


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest):
    df = pd.DataFrame([l.model_dump(exclude={"extra"}) for l in req.leads])
    res = run_pipeline(df, icp=_icp, cache=_cache, enrich=req.enrich, check_mx=req.check_mx, source="api")
    return ScoreResponse(
        rows_in=res.rows_in, rows_out=res.rows_after_dedupe, duplicates_removed=res.duplicates_removed, elapsed_s=res.elapsed_s,
        leads=[
            ScoredOut(
                fit_score=s.fit_score, tier=s.tier, company=s.lead.company, domain=s.lead.domain, email=s.lead.email,
                email_verified=bool(s.validation.email_syntax_ok and s.validation.email_mx_ok),
                phone=s.validation.phone_e164 or s.lead.phone, merged_from=s.merged_from, flags=s.flags, reasons=s.reasons,
            )
            for s in res.scored
        ],
    )


@app.post("/score/csv")
async def score_csv(file: UploadFile = File(...), enrich: bool = Query(True), check_mx: bool = Query(True), crm: bool = Query(False)):
    raw = await file.read()
    df = pd.read_excel(io.BytesIO(raw)) if file.filename.lower().endswith("xlsx") else pd.read_csv(io.BytesIO(raw))
    res = run_pipeline(df, icp=_icp, cache=_cache, enrich=enrich, check_mx=check_mx, source=file.filename)
    out = to_csv_bytes(to_dataframe(res.scored), crm=crm)
    return StreamingResponse(io.BytesIO(out), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=leadlens_scored.csv"})
