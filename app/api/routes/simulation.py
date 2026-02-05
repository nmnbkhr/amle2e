"""
Simulation API Routes

Endpoints for starting, stopping, resetting, and monitoring
the standalone real-time AML simulation.
"""

import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from ...simulation.engine import simulation_manager, SimulationConfig
from ...utils.paths import get_run_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])


# ─── Request Model ───────────────────────────────────────

class SimStartRequest(BaseModel):
    source_run_id: str = Field(..., description="ID of completed run with trained models")
    num_batches: int = Field(default=80, ge=1, le=500)
    batch_size: int = Field(default=50, ge=10, le=500)
    batch_interval: float = Field(default=0.5, ge=0.1, le=10.0)
    pattern_prob: float = Field(default=0.10, ge=0.0, le=1.0)
    rescore_interval: int = Field(default=3, ge=1, le=50)
    threshold_percentile: int = Field(default=99, ge=80, le=100)
    seed: int = Field(default=42)


# ─── Endpoints ───────────────────────────────────────────

@router.post("/start")
def start_simulation(req: SimStartRequest):
    """Start a new simulation using models from a completed pipeline run."""
    source_dir = get_run_dir(req.source_run_id)
    if not (source_dir / "models" / "graphsage.pt").exists():
        raise HTTPException(
            status_code=400,
            detail=f"Source run {req.source_run_id[:8]} missing trained models.",
        )

    config = SimulationConfig(
        source_run_id=req.source_run_id,
        num_batches=req.num_batches,
        batch_size=req.batch_size,
        batch_interval=req.batch_interval,
        pattern_prob=req.pattern_prob,
        rescore_interval=req.rescore_interval,
        threshold_percentile=req.threshold_percentile,
        seed=req.seed,
    )

    try:
        result = simulation_manager.start(config)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stop")
def stop_simulation():
    """Signal the running simulation to stop gracefully."""
    result = simulation_manager.stop()
    if result["status"] == "not_running":
        raise HTTPException(status_code=400, detail="No simulation is currently running.")
    return result


@router.post("/reset")
def reset_simulation():
    """Stop the simulation (if running) and clear all state."""
    return simulation_manager.reset()


@router.get("/status")
def get_simulation_status():
    """Get the current simulation state for polling."""
    return simulation_manager.status()
