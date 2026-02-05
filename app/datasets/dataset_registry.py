"""
Dataset Registry

Three dataset modes:
  demodata  — Small synthetic data bundled in repo (demodata/)
  simulate  — Generate fresh synthetic data via 00_simulate_transactions
  saml-d    — Realistic 9.5M-row dataset at /mnt/e/xx/demodata

Each mode is described by a DatasetSpec.  For saml-d the orchestrator
runs DuckDB ingestion (saml_d_ingest.py) BEFORE any notebooks.

Sampling profiles constrain row counts:
  Quick     200 K rows
  Standard  1 M rows
  Heavy     3 M rows
  Full      all rows (requires explicit confirm)
"""

import hashlib
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sampling profiles
# ---------------------------------------------------------------------------

SAMPLING_PROFILES: Dict[str, Optional[int]] = {
    "Quick": 200_000,
    "Standard": 1_000_000,
    "Heavy": 3_000_000,
    "Full": None,             # None == no limit
}


def get_max_rows(profile: str, override: Optional[int] = None) -> Optional[int]:
    """Resolve max_rows from a sampling profile name and optional override."""
    if override is not None:
        return override
    return SAMPLING_PROFILES.get(profile)


# ---------------------------------------------------------------------------
# DatasetSpec
# ---------------------------------------------------------------------------

@dataclass
class DatasetSpec:
    """Describes a dataset that can be fed into a pipeline."""

    name: str                               # "demodata" | "simulate" | "saml-d"
    display_name: str
    description: str
    dataset_root: Optional[str] = None      # absolute or relative to repo root
    expected_files: List[str] = field(default_factory=lambda: [
        "party.csv", "transactions.csv", "alert_transactions.csv",
    ])
    approx_rows: Optional[int] = None
    default_sampling: str = "Standard"
    cache_root: Optional[str] = None        # Linux-side parquet cache
    requires_ingest: bool = False
    requires_dataset_root: bool = False     # user must supply dataset_root
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sampling_profiles"] = list(SAMPLING_PROFILES.keys())
        return d


# ---------------------------------------------------------------------------
# Built-in datasets
# ---------------------------------------------------------------------------

DATASETS: Dict[str, DatasetSpec] = {}


def _reg(spec: DatasetSpec) -> DatasetSpec:
    DATASETS[spec.name] = spec
    return spec


DEMODATA = _reg(DatasetSpec(
    name="demodata",
    display_name="Demo Data",
    description="Small synthetic dataset (~7.5K parties, ~67K txns) in demodata/.",
    dataset_root="demodata",
    approx_rows=67_000,
    default_sampling="Full",        # small enough for full load
    requires_ingest=False,
))

SIMULATE = _reg(DatasetSpec(
    name="simulate",
    display_name="Generate Synthetic",
    description=(
        "Generate fresh synthetic AML data via 00_simulate_transactions. "
        "Creates transactions/party/alert CSVs in demodata/ before pipeline runs."
    ),
    dataset_root="demodata",
    approx_rows=None,               # depends on generation params
    default_sampling="Full",
    requires_ingest=False,
    notes="The 00_simulate_transactions notebook will generate the data.",
))

SAML_D = _reg(DatasetSpec(
    name="saml-d",
    display_name="SAML-D (9.5M rows)",
    description=(
        "Realistic AML dataset (~230K parties, ~9.5M transactions). "
        "Located at /mnt/e/xx/demodata. DuckDB out-of-core ingest "
        "with Linux-side parquet caching."
    ),
    dataset_root="/mnt/e/xx/demodata",
    approx_rows=9_500_000,
    default_sampling="Quick",
    cache_root="/tmp/aml-saml-d-cache",
    requires_ingest=True,
    requires_dataset_root=False,     # has default, but user can override
    notes="IO from /mnt/ is slow; parquet cache on Linux recommended.",
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_dataset(name: str) -> DatasetSpec:
    if name not in DATASETS:
        valid = ", ".join(DATASETS.keys())
        raise KeyError(f"Unknown dataset '{name}'. Valid: {valid}")
    return DATASETS[name]


def list_datasets() -> List[Dict[str, Any]]:
    return [spec.to_dict() for spec in DATASETS.values()]


def register_dataset(spec: DatasetSpec) -> None:
    DATASETS[spec.name] = spec
    logger.info(f"Registered dataset: {spec.name}")


def validate_dataset(
    spec: DatasetSpec,
    repo_root: Optional[Path] = None,
    dataset_root_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check that expected files exist and are readable.

    Returns {"valid": bool, "data_root": str, "missing": [...], "sizes": {...}}
    """
    from ..utils.paths import get_repo_root as _repo_root

    if repo_root is None:
        repo_root = _repo_root()

    root_str = dataset_root_override or spec.dataset_root or "demodata"
    data_root = Path(root_str)
    if not data_root.is_absolute():
        data_root = repo_root / data_root

    missing, sizes = [], {}
    for fname in spec.expected_files:
        fp = data_root / fname
        if fp.exists():
            sizes[fname] = fp.stat().st_size
        else:
            missing.append(fname)

    return {
        "valid": len(missing) == 0,
        "data_root": str(data_root),
        "missing": missing,
        "sizes": sizes,
    }


def compute_cache_key(
    data_root: Path,
    max_rows: Optional[int] = None,
) -> str:
    """
    Fingerprint based on file sizes + mtimes + max_rows.
    Cache auto-invalidates when source data or sampling changes.
    """
    parts = []
    for fname in ["party.csv", "transactions.csv", "alert_transactions.csv"]:
        fp = data_root / fname
        if fp.exists():
            stat = fp.stat()
            parts.append(f"{fname}:{stat.st_size}:{int(stat.st_mtime)}")
        else:
            parts.append(f"{fname}:missing")
    if max_rows is not None:
        parts.append(f"max_rows:{max_rows}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
