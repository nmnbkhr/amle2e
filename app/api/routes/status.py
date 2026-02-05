"""
Pipeline Status API Routes

Endpoints for checking pipeline run status and step-level progress.
"""

import logging
import asyncio
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...db import get_db, PipelineRun, StepLog, RunStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/status", tags=["status"])


# Response Models
class StepStatus(BaseModel):
    """Status of an individual pipeline step"""
    step_number: int
    step_name: str
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    metrics: dict


class RunStatusDetail(BaseModel):
    """Detailed status of a pipeline run including step-level info"""
    run_id: str
    status: str
    current_step: int
    total_steps: int
    current_step_name: str
    progress_percent: float
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
    steps: List[StepStatus]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    celery: str


# Default fallback step definitions (only used if no manifest exists)
DEFAULT_PIPELINE_STEPS = [
    {"number": 1, "name": "Data Loading And Features", "notebook": "01_data_loading_and_features.ipynb"},
    {"number": 2, "name": "Graph Sage Embeddings", "notebook": "02_graph_sage_embeddings.ipynb"},
    {"number": 3, "name": "WGAN GP Anomaly Detector", "notebook": "03_wgan_gp_anomaly_detector.ipynb"},
    {"number": 4, "name": "Scoring And Visualization", "notebook": "04_scoring_and_visualization.ipynb"},
    {"number": 5, "name": "Predict And Evaluate", "notebook": "05_predict_and_evaluate.ipynb"},
]


def _get_pipeline_steps_for_run(run_id: str) -> list:
    """Get pipeline step definitions for a specific run from its manifest."""
    from pathlib import Path
    import json
    from ...utils.paths import get_run_dir

    manifest_path = get_run_dir(run_id) / "pipeline" / "pipeline_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            steps = manifest.get("steps", [])
            return [
                {"number": s["number"], "name": s["name"], "notebook": s["notebook"]}
                for s in steps
            ]
        except Exception as e:
            logger.warning(f"Failed to read pipeline manifest for {run_id}: {e}")

    return DEFAULT_PIPELINE_STEPS


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.

    Verifies database connectivity and Celery worker availability.
    """
    # Check database
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    # Check Celery (run in thread pool since inspect.ping() is synchronous and slow)
    celery_status = "unknown"
    try:
        def check_celery():
            from ...workers.celery_app import celery_app
            inspect = celery_app.control.inspect()
            return inspect.ping()

        ping_response = await asyncio.wait_for(
            asyncio.to_thread(check_celery),
            timeout=5.0  # 5 second timeout
        )
        if ping_response:
            celery_status = "healthy"
        else:
            celery_status = "no_workers"
    except asyncio.TimeoutError:
        logger.warning("Celery health check timed out")
        celery_status = "timeout"
    except Exception as e:
        logger.warning(f"Celery health check failed: {e}")
        celery_status = "unhealthy"

    overall = "healthy" if db_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        celery=celery_status,
    )


@router.get("/steps")
async def get_pipeline_steps():
    """
    Get the list of all pipeline steps.

    Returns the default step definitions without run-specific status.
    """
    return {"steps": DEFAULT_PIPELINE_STEPS, "total_steps": len(DEFAULT_PIPELINE_STEPS)}


@router.get("/{run_id}", response_model=RunStatusDetail)
async def get_run_status(run_id: str, db: Session = Depends(get_db)):
    """
    Get detailed status of a specific run.

    Includes step-level progress information.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Get step logs for this run
    step_logs = (
        db.query(StepLog)
        .filter(StepLog.run_id == run_id)
        .order_by(StepLog.step_number)
        .all()
    )

    # Build step status list, merging with step definitions from manifest
    steps = []
    logged_steps = {log.step_number: log for log in step_logs}
    pipeline_steps = _get_pipeline_steps_for_run(run_id)

    for step_def in pipeline_steps:
        step_num = step_def["number"]
        if step_num in logged_steps:
            log = logged_steps[step_num]
            steps.append(StepStatus(
                step_number=step_num,
                step_name=step_def["name"],
                status=log.status,
                started_at=log.started_at.isoformat() if log.started_at else None,
                completed_at=log.completed_at.isoformat() if log.completed_at else None,
                metrics=log.metrics or {},
            ))
        else:
            # Step not yet logged
            status = "pending"
            if run.current_step > step_num:
                status = "completed"  # Assume completed if we're past it
            elif run.current_step == step_num and run.status == RunStatus.RUNNING:
                status = "running"

            steps.append(StepStatus(
                step_number=step_num,
                step_name=step_def["name"],
                status=status,
                started_at=None,
                completed_at=None,
                metrics={},
            ))

    return RunStatusDetail(
        run_id=run.id,
        status=run.status.value if run.status else "unknown",
        current_step=run.current_step,
        total_steps=run.total_steps,
        current_step_name=run.current_step_name,
        progress_percent=run.progress_percent,
        created_at=run.created_at.isoformat() if run.created_at else None,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        error_message=run.error_message,
        steps=steps,
    )


@router.get("/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    step: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Get execution logs for a run.

    Optionally filter by step number.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    query = db.query(StepLog).filter(StepLog.run_id == run_id)

    if step is not None:
        query = query.filter(StepLog.step_number == step)

    logs = query.order_by(StepLog.step_number).all()

    return {
        "run_id": run_id,
        "logs": [log.to_dict() for log in logs],
    }
