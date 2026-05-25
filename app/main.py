from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_search import router as search_router
from app.api.routes_score import router as score_router
from app.api.routes_history import router as history_router

app = FastAPI(
    title="Flight Intel API",
    description="智能机票评分看板后端接口",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(score_router)
app.include_router(history_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
