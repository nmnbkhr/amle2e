"""
Pipelines & Datasets API Routes

Endpoints for listing available pipelines and dataset profiles.
"""

import logging
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...pipeline_runner.pipeline_registry import (
    list_pipelines,
    get_pipeline,
    resolve_steps,
    get_excluded_notebooks,
    ROLE_ORDER,
)
from ...datasets.dataset_registry import (
    list_datasets,
    get_dataset,
    validate_dataset,
    SAMPLING_PROFILES,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pipelines"])


# --- Pipeline endpoints ---


@router.get("/pipelines")
def get_pipelines():
    """
    List all registered pipelines.

    Returns pipeline specs including name, description, notebook directory,
    and default parameters.
    """
    return {"pipelines": list_pipelines()}


@router.get("/pipelines/{pipeline_name}")
def get_pipeline_detail(pipeline_name: str, dataset_mode: str = "demodata"):
    """
    Get details of a specific pipeline including resolved notebook steps.

    The dataset_mode param controls conditional 00 step inclusion.
    """
    try:
        spec = get_pipeline(pipeline_name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    steps = resolve_steps(spec, dataset_mode=dataset_mode)

    # Build role counts
    role_counts = {}
    for s in steps:
        r = s.get("role", "Other")
        role_counts[r] = role_counts.get(r, 0) + 1

    # Notebooks available but excluded from this variant
    included_filenames = [s["notebook"] for s in steps]
    excluded = get_excluded_notebooks(spec, included_filenames)

    return {
        "pipeline": spec.to_dict(),
        "steps": steps,
        "total_steps": len(steps),
        "role_order": ROLE_ORDER,
        "role_counts": role_counts,
        "excluded_notebooks": excluded,
    }


@router.get("/sampling-profiles")
def get_sampling_profiles():
    """Return available sampling profiles with their max_rows values."""
    return {
        "profiles": {
            name: {"max_rows": val, "description": f"Up to {val:,} rows" if val else "All rows (no limit)"}
            for name, val in SAMPLING_PROFILES.items()
        }
    }


# --- Dataset endpoints ---


@router.get("/datasets")
def get_datasets():
    """
    List all registered dataset profiles.

    Returns dataset specs including name, description, approximate size,
    and ingestion requirements.
    """
    return {"datasets": list_datasets()}


@router.get("/datasets/{dataset_name}")
def get_dataset_detail(dataset_name: str):
    """
    Get details of a specific dataset including validation status.
    """
    try:
        spec = get_dataset(dataset_name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    validation = validate_dataset(spec)

    return {
        "dataset": spec.to_dict(),
        "validation": validation,
    }
