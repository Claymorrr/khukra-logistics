"""FastAPI surface for Khukra."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from khukra import __version__
from khukra.disruption.service import get_disruption_service
from khukra.registry import get_model, list_models

app = FastAPI(
    title="Khukra API",
    description="Global disruption forecast, data ingest, and statistical risk discovery",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3020", "http://127.0.0.1:3020"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

disruption = APIRouter(prefix="/api/disruption", tags=["disruption"])


class RunRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


class RefreshRequest(BaseModel):
    signal_ids: list[str] | None = None
    years: int | None = Field(None, ge=1, le=20)


class DiscoverRequest(BaseModel):
    signal_ids: list[str] | None = None


class ForecastRequest(BaseModel):
    signal_ids: list[str] | None = None
    horizon_days: int = Field(30, ge=7, le=180)


class EvaluateRequest(BaseModel):
    signal_ids: list[str] | None = None
    horizon_days: int = Field(30, ge=7, le=180)
    persist: bool = True


class PanelRequest(BaseModel):
    signal_ids: list[str] | None = None
    tail_days: int | None = Field(504, ge=30, le=5000)
    scale: Literal["raw", "rebased", "zscore"] = "raw"
    table_rows: int = Field(50, ge=10, le=500)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "platform": "khukra",
        "version": __version__,
        "capabilities": [
            "catalog",
            "refresh",
            "discover",
            "forecast",
            "evaluate",
            "production-model",
            "index-decomposition",
            "forecast-check",
            "forecast-optimization",
            "panel",
            "explore",
            "news",
        ],
    }


@app.get("/api/models")
def models() -> dict[str, Any]:
    return {"models": list_models(), "total": len(list_models())}


@app.post("/api/models/{model_id}/run")
def run_model(model_id: str, body: RunRequest) -> dict[str, Any]:
    try:
        result = get_model(model_id).run(body.parameters)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "domain": result.domain,
        "subdomain": result.subdomain,
        "model_name": result.model_name,
        "parameters": result.parameters,
        "metrics": result.metrics,
        "series": result.series,
        "metadata": result.metadata,
    }


@disruption.get("/catalog")
def disruption_catalog() -> dict[str, Any]:
    return get_disruption_service().catalog()


@disruption.get("/status")
def disruption_status() -> dict[str, Any]:
    return get_disruption_service().status()


@disruption.post("/refresh")
def disruption_refresh(body: RefreshRequest) -> dict[str, Any]:
    return get_disruption_service().refresh(body.signal_ids, body.years or 5)


@disruption.post("/discover")
def disruption_discover(body: DiscoverRequest) -> dict[str, Any]:
    try:
        return get_disruption_service().discover(body.signal_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.post("/forecast")
def disruption_forecast(body: ForecastRequest) -> dict[str, Any]:
    try:
        return get_disruption_service().forecast(body.signal_ids, body.horizon_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.get("/index-decomposition")
def disruption_index_decomposition() -> dict[str, Any]:
    try:
        return get_disruption_service().index_decomposition()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.get("/forecast-check")
def disruption_forecast_check() -> dict[str, Any]:
    try:
        return get_disruption_service().yesterday_forecast_check()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.get("/forecast-optimization")
def disruption_forecast_optimization() -> dict[str, Any]:
    try:
        return get_disruption_service().forecast_optimization()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.post("/forecast-optimization/apply")
def disruption_apply_forecast_optimization() -> dict[str, Any]:
    try:
        return get_disruption_service().apply_forecast_optimization()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.get("/production-model")
def disruption_production_model(horizon_days: int = 30) -> dict[str, Any]:
    try:
        return get_disruption_service().production_model(None, horizon_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.post("/evaluate")
def disruption_evaluate(body: EvaluateRequest) -> dict[str, Any]:
    try:
        return get_disruption_service().evaluate(
            body.signal_ids,
            body.horizon_days,
            body.persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.get("/evaluation")
def disruption_evaluation_history(days: int = 30) -> dict[str, Any]:
    return get_disruption_service().evaluation_history(days=min(max(days, 1), 365))


@disruption.post("/panel")
def disruption_panel(body: PanelRequest) -> dict[str, Any]:
    try:
        return get_disruption_service().panel_data(
            body.signal_ids,
            body.tail_days,
            body.scale,
            body.table_rows,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.post("/explore")
def disruption_explore(body: DiscoverRequest) -> dict[str, Any]:
    try:
        return get_disruption_service().explore(body.signal_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@disruption.post("/refresh-news")
def disruption_refresh_news() -> dict[str, Any]:
    return get_disruption_service().refresh_news()


@disruption.get("/news")
def disruption_news_status() -> dict[str, Any]:
    return get_disruption_service().get_news_status()


app.include_router(disruption)
