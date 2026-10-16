"""Valuation Router for Phase 3B: Investment Valuation & Decision Support.

Provides API endpoints for:
- Full valuation workspace retrieval (Enterprise DCF, FCFE, Scenarios, Sensitivity, Margin of Safety, Multiples, Peers, Provenance)
- Dynamic scenario recalculation without full page reload
- Reset to source-derived default assumptions
- Peer comparison between GOOGL and META
- Input provenance and audit verification
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.services.valuation import valuation_service

router = APIRouter(prefix="/api/valuation", tags=["Valuation & Decision Support"])


class RecalculateRequest(BaseModel):
    scenario_name: str = Field(default="Custom Scenario", description="Name of the scenario being evaluated")
    revenue_growth: float = Field(..., ge=-50.0, le=100.0, description="Annual revenue growth rate (%)")
    operating_margin: float = Field(..., ge=-50.0, le=90.0, description="Target operating margin (%)")
    effective_tax_rate: float = Field(default=15.0, ge=0.0, le=50.0, description="Effective tax rate (%)")
    reinvestment_rate: float = Field(default=8.0, ge=-20.0, le=50.0, description="CapEx and reinvestment (% of revenue)")
    working_capital_pct: float = Field(default=1.5, ge=-10.0, le=20.0, description="Incremental NWC (% of revenue change)")
    sbc_pct_of_revenue: float = Field(default=6.0, ge=0.0, le=30.0, description="Stock-based compensation (% of revenue)")
    annual_share_dilution_rate: float = Field(default=-0.5, ge=-10.0, le=15.0, description="Net share count change (% per year)")
    discount_rate: float = Field(..., gt=0.0, le=30.0, description="Discount rate / WACC (%)")
    cost_of_equity: Optional[float] = Field(default=None, description="Cost of equity for FCFE (%)")
    terminal_growth_rate: float = Field(..., ge=-5.0, le=10.0, description="Perpetual terminal growth rate (%)")
    sbc_treatment: str = Field(default="conventional", description="'conventional' (share dilution) or 'expensed' (cash outflow)")
    forecast_years: int = Field(default=5, ge=5, le=10, description="Forecast horizon in years (5 or 10)")
    required_return_pct: Optional[float] = Field(default=12.0, ge=1.0, le=40.0, description="Investor required hurdle rate (%)")


class MultiScenarioRecalculateRequest(BaseModel):
    scenarios: Dict[str, Dict[str, Any]] = Field(..., description="Bear, Base, and Bull scenario assumption objects")
    forecast_years: int = Field(default=5, ge=5, le=10, description="Forecast horizon in years (5 or 10)")
    required_return_pct: float = Field(default=12.0, ge=1.0, le=40.0, description="Investor required hurdle rate (%)")
    active_scenario: str = Field(default="base", description="Currently focused scenario ('bear', 'base', or 'bull')")


@router.get("/{ticker}/workspace")
def get_valuation_workspace(
    ticker: str,
    forecast_years: int = Query(default=5, ge=5, le=10),
    required_return_pct: float = Query(default=12.0, ge=1.0, le=40.0),
):
    """Retrieve complete institutional valuation workspace for a stock."""
    ticker = ticker.strip().upper()
    try:
        workspace = valuation_service.get_full_workspace(
            ticker=ticker,
            forecast_years=forecast_years,
            required_return_pct=required_return_pct,
        )
        return workspace
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate valuation workspace for {ticker}: {str(e)}")


@router.post("/{ticker}/recalculate")
def recalculate_valuation(ticker: str, request: RecalculateRequest):
    """Recalculate DCF, forecast table, valuation bridge, sensitivity heatmap, and margin of safety with custom parameters."""
    ticker = ticker.strip().upper()
    assumptions = request.model_dump()
    try:
        result = valuation_service.recalculate_custom(
            ticker=ticker,
            assumptions=assumptions,
            scenario_name=request.scenario_name,
            forecast_years=request.forecast_years,
            required_return_pct=request.required_return_pct,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Valuation calculation failed for {ticker}: {str(e)}")


@router.post("/{ticker}/recalculate-scenarios")
def recalculate_multi_scenarios(ticker: str, request: MultiScenarioRecalculateRequest):
    """Recalculate Bear, Base, and Bull scenarios independently with unified matrix inputs."""
    ticker = ticker.strip().upper()
    try:
        result = valuation_service.recalculate_multi_scenario(
            ticker=ticker,
            scenarios=request.scenarios,
            forecast_years=request.forecast_years,
            required_return_pct=request.required_return_pct,
            active_scenario=request.active_scenario,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multi-scenario calculation failed for {ticker}: {str(e)}")


@router.get("/{ticker}/matrix")
def get_historical_matrix(ticker: str):
    """Retrieve 10-row historical fundamentals matrix benchmarked against SEC Form 10-K facts."""
    ticker = ticker.strip().upper()
    try:
        matrix = valuation_service.get_historical_matrix(ticker)
        return matrix
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve historical matrix for {ticker}: {str(e)}")


@router.get("/{ticker}/defaults")
def get_default_assumptions(ticker: str):
    """Reset to audited fundamental source-derived defaults."""
    ticker = ticker.strip().upper()
    try:
        defaults = valuation_service.get_default_assumptions(ticker)
        return defaults
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve default assumptions for {ticker}: {str(e)}")


@router.get("/{ticker}/peers")
def get_peer_comparison(ticker: str, peers: Optional[str] = Query(None, description="Comma-separated peer tickers")):
    """Retrieve side-by-side peer valuation comparison."""
    ticker = ticker.strip().upper()
    peer_list = [p.strip().upper() for p in peers.split(",")] if peers else None
    try:
        data = valuation_service.get_peer_comparison(ticker, peer_list)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch peer comparison for {ticker}: {str(e)}")


@router.get("/{ticker}/provenance")
def get_valuation_provenance(ticker: str):
    """Retrieve complete regulatory input provenance audit table."""
    ticker = ticker.strip().upper()
    try:
        rows = valuation_service.get_input_provenance_table(ticker)
        return {"ticker": ticker, "provenance": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch provenance for {ticker}: {str(e)}")
