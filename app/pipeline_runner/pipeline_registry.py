"""
Pipeline Registry

Defines available pipelines (legacy root notebooks, e2e core/dashboards/realtime)
and provides step resolution, listing, and manifest writing.

Pipeline Variants:
  legacy-root   — Existing 12-step pipeline (root *.ipynb, 1-12)
  e2e-core      — Core E2E pipeline (01-08 + conditional 00 based on dataset_mode)
  e2e-dashboards — e2e-core + interactive & analytics dashboards (09, 10)
  e2e-realtime  — Real-time notebooks only (11, 12), on-demand

The two 00_* notebooks are CONDITIONAL:
  dataset_mode == "saml-d" or "external" → 00_map_external_data.ipynb
  dataset_mode == "simulate"             → 00_simulate_transactions.ipynb
  dataset_mode == "demodata"             → neither (data already exists)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..utils.paths import get_repo_root

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role inference — maps notebook filenames to pipeline phases
# ---------------------------------------------------------------------------

ROLE_ORDER = [
    "Ingest",
    "Features",
    "Embeddings",
    "GAN",
    "Scoring",
    "Eval",
    "Dashboards",
    "Realtime",
    "Other",
]

# All e2e notebooks that could exist (used for "excluded" detection)
_ALL_E2E_NOTEBOOKS = [
    "00_map_external_data.ipynb",
    "00_simulate_transactions.ipynb",
    "01_data_loading_and_features.ipynb",
    "02_graph_sage_embeddings.ipynb",
    "03_wgan_gp_anomaly_detector.ipynb",
    "04_scoring_and_visualization.ipynb",
    "05_predict_and_evaluate.ipynb",
    "06_visualize_results.ipynb",
    "07_analytical_dashboard.ipynb",
    "08_pattern_analysis.ipynb",
    "09_interactive_dashboard.ipynb",
    "10_advanced_analytics_dashboard.ipynb",
    "11_realtime_simulator.ipynb",
    "12_simulation_dashboard.ipynb",
]


def infer_role(filename: str) -> str:
    """
    Infer a pipeline role from a notebook filename.

    Returns one of ROLE_ORDER values.  Rules are evaluated in order;
    first match wins.  Only intended for ``.ipynb`` step filenames.
    """
    f = filename.lower()

    # Ingest — 00_* notebooks or data-mapping / simulation generation
    if f.startswith("00_") or "map_external" in f or "simulate_transactions" in f:
        return "Ingest"

    # Features — data loading, feature engineering, prep training
    if "data_loading" in f or "feature" in f or "prep_training" in f or "create_feature_groups" in f:
        return "Features"

    # Embeddings — GraphSAGE or generic embedding
    if "graph_sage" in f or "embedding" in f:
        return "Embeddings"

    # GAN — WGAN-GP or adversarial training
    if "wgan" in f or "adversarial" in f or ("gan" in f and "anomaly" in f):
        return "GAN"

    # Scoring — scoring, anomaly detection, predict_and_create
    if "scoring" in f or "anomaly" in f or "detect" in f or "predict_and_create" in f:
        return "Scoring"

    # Eval — evaluate / predict_and_evaluate / pattern_analysis
    if "evaluate" in f or "pattern_analysis" in f:
        return "Eval"

    # Dashboards — dashboard / visualize
    if "dashboard" in f or "visualize" in f or "analytics" in f:
        return "Dashboards"

    # Realtime — realtime / simulator / model_server
    if "realtime" in f or "simulator" in f or "model_server" in f:
        return "Realtime"

    return "Other"


def get_excluded_notebooks(
    spec: "PipelineSpec",
    included_filenames: List[str],
) -> List[Dict[str, str]]:
    """
    Return notebooks available in the e2e directory but NOT included
    in the current pipeline variant.  Useful for UI display.
    """
    if spec.notebooks_dir != "e2e":
        return []

    included = set(included_filenames)
    excluded = []
    for nb in _ALL_E2E_NOTEBOOKS:
        if nb not in included:
            excluded.append({
                "notebook": nb,
                "role": infer_role(nb),
                "name": nb.replace(".ipynb", "").split("_", 1)[-1].replace("_", " ").title(),
            })
    return excluded


# ---------------------------------------------------------------------------
# Explicit step lists (avoids 00 collision from numeric discovery)
# ---------------------------------------------------------------------------

# E2E core steps (01-08)
_E2E_CORE_STEPS = [
    "01_data_loading_and_features.ipynb",
    "02_graph_sage_embeddings.ipynb",
    "03_wgan_gp_anomaly_detector.ipynb",
    "04_scoring_and_visualization.ipynb",
    "05_predict_and_evaluate.ipynb",
    "06_visualize_results.ipynb",
    "07_analytical_dashboard.ipynb",
    "08_pattern_analysis.ipynb",
]

# Dashboard steps
_E2E_DASHBOARD_STEPS = [
    "09_interactive_dashboard.ipynb",
    "10_advanced_analytics_dashboard.ipynb",
]

# Realtime steps
_E2E_REALTIME_STEPS = [
    "11_realtime_simulator.ipynb",
    "12_simulation_dashboard.ipynb",
]

# Conditional 00 steps
_E2E_00_MAP = "00_map_external_data.ipynb"
_E2E_00_SIM = "00_simulate_transactions.ipynb"


@dataclass
class PipelineSpec:
    """Describes a runnable notebook pipeline."""

    name: str                                   # unique key
    display_name: str                           # human label for UI
    description: str
    notebooks_dir: str                          # relative to repo root ("." or "e2e")
    ordered_steps: List[str] = field(default_factory=list)   # explicit notebook filenames
    conditional_00: bool = False                # whether 00 step is dataset-mode dependent
    optional_markers: List[str] = field(default_factory=lambda: ["maggy", "hp"])
    default_parameters: Dict[str, Any] = field(default_factory=dict)
    kernel_name: str = "python3"
    supports_papermill: bool = True
    cwd_relative: Optional[str] = None          # working dir relative to repo root
    flags: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Built-in pipeline definitions
# ---------------------------------------------------------------------------

PIPELINES: Dict[str, PipelineSpec] = {}


def _register(spec: PipelineSpec) -> PipelineSpec:
    PIPELINES[spec.name] = spec
    return spec


LEGACY_ROOT = _register(PipelineSpec(
    name="legacy-root",
    display_name="Legacy Hopsworks Pipeline",
    description=(
        "Original 12-step pipeline using Hopsworks feature store, "
        "node2vec embeddings, and GAN anomaly detection. "
        "Notebooks 1-12 in the project root."
    ),
    notebooks_dir=".",
    ordered_steps=[],                   # uses numeric discovery (legacy behavior)
    conditional_00=False,
    optional_markers=["maggy", "hp"],
    default_parameters={
        "sample_size": 20000,
        "epochs": 5,
        "threshold": 0.99,
    },
    kernel_name="python3",
    supports_papermill=True,
    cwd_relative=None,
    flags={"include_dashboards": False, "include_realtime": False},
))

E2E_CORE = _register(PipelineSpec(
    name="e2e-core",
    display_name="E2E PyTorch Core",
    description=(
        "Core pipeline: GraphSAGE embeddings + WGAN-GP anomaly detection. "
        "Runs 01-08 in e2e/. Prepends 00_map or 00_simulate based on dataset mode."
    ),
    notebooks_dir="e2e",
    ordered_steps=list(_E2E_CORE_STEPS),
    conditional_00=True,
    optional_markers=[],
    default_parameters={
        "epochs": 10,
        "threshold": 0.99,
    },
    kernel_name="python3",
    supports_papermill=False,
    cwd_relative="e2e",
    flags={"include_dashboards": False, "include_realtime": False},
))

E2E_DASHBOARDS = _register(PipelineSpec(
    name="e2e-dashboards",
    display_name="E2E + Dashboards",
    description=(
        "Core pipeline (01-08) plus interactive dashboards (09, 10). "
        "Includes advanced analytics and risk ranking dashboards."
    ),
    notebooks_dir="e2e",
    ordered_steps=list(_E2E_CORE_STEPS) + list(_E2E_DASHBOARD_STEPS),
    conditional_00=True,
    optional_markers=[],
    default_parameters={
        "epochs": 10,
        "threshold": 0.99,
    },
    kernel_name="python3",
    supports_papermill=False,
    cwd_relative="e2e",
    flags={"include_dashboards": True, "include_realtime": False},
))

E2E_REALTIME = _register(PipelineSpec(
    name="e2e-realtime",
    display_name="E2E Real-Time Only",
    description=(
        "Real-time simulation notebooks (11, 12). "
        "Requires a prior e2e-core run with trained models. On-demand only."
    ),
    notebooks_dir="e2e",
    ordered_steps=list(_E2E_REALTIME_STEPS),
    conditional_00=False,
    optional_markers=[],
    default_parameters={},
    kernel_name="python3",
    supports_papermill=False,
    cwd_relative="e2e",
    flags={"include_dashboards": False, "include_realtime": True},
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pipeline(name: str) -> PipelineSpec:
    """Return a pipeline spec by name, or raise KeyError."""
    if name not in PIPELINES:
        valid = ", ".join(PIPELINES.keys())
        raise KeyError(f"Unknown pipeline '{name}'. Valid: {valid}")
    return PIPELINES[name]


def list_pipelines() -> List[Dict[str, Any]]:
    """Return serialisable list of all registered pipelines."""
    return [spec.to_dict() for spec in PIPELINES.values()]


def register_pipeline(spec: PipelineSpec) -> None:
    """Register a custom pipeline at runtime."""
    PIPELINES[spec.name] = spec
    logger.info(f"Registered pipeline: {spec.name}")


def resolve_steps(
    spec: PipelineSpec,
    dataset_mode: str = "demodata",
    project_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Resolve the ordered list of notebook steps for a pipeline + dataset_mode.

    For e2e pipelines with ``conditional_00=True``:
      - dataset_mode "saml-d" or "external" → prepend 00_map_external_data
      - dataset_mode "simulate"             → prepend 00_simulate_transactions
      - dataset_mode "demodata"             → no 00 step

    For legacy-root: falls back to numeric discovery.

    Returns list of step dicts with keys:
        number, notebook, name, optional, path
    """
    if project_root is None:
        project_root = get_repo_root()

    nb_dir = project_root / spec.notebooks_dir

    # Legacy pipeline: dynamic numeric discovery
    if not spec.ordered_steps:
        return _discover_legacy_steps(nb_dir, spec)

    # Build ordered step list
    filenames: List[str] = []

    # Conditional 00 step
    if spec.conditional_00:
        if dataset_mode in ("saml-d", "external"):
            filenames.append(_E2E_00_MAP)
        elif dataset_mode == "simulate":
            filenames.append(_E2E_00_SIM)
        # demodata → no 00 step

    filenames.extend(spec.ordered_steps)

    steps: List[Dict[str, Any]] = []
    for idx, fname in enumerate(filenames):
        nb_path = nb_dir / fname
        # Extract number and name from filename
        parts = fname.replace(".ipynb", "").split("_", 1)
        try:
            number = int(parts[0])
        except ValueError:
            number = idx
        name_part = parts[1] if len(parts) > 1 else fname
        display_name = name_part.replace("_", " ").title()

        is_optional = any(
            m in fname.lower() for m in spec.optional_markers
        )

        steps.append({
            "number": number,
            "notebook": fname,
            "name": display_name,
            "optional": is_optional,
            "path": str(nb_path),
            "role": infer_role(fname),
        })

    logger.info(
        f"Resolved {len(steps)} steps for '{spec.name}' "
        f"(dataset_mode={dataset_mode})"
    )
    return steps


def _discover_legacy_steps(
    nb_dir: Path,
    spec: PipelineSpec,
) -> List[Dict[str, Any]]:
    """
    Numeric discovery for legacy-root pipeline (existing behaviour).
    Skips 0 and 13.
    """
    import re

    pattern = re.compile(r"^(\d+)_(.+)\.ipynb$")
    skip = {0, 13}
    steps: List[Dict[str, Any]] = []

    for nb_file in sorted(nb_dir.glob("*.ipynb")):
        match = pattern.match(nb_file.name)
        if not match:
            continue
        number = int(match.group(1))
        if number in skip:
            continue

        name_part = match.group(2)
        display_name = name_part.replace("_", " ").title()
        is_optional = any(
            m in nb_file.name.lower() or m in display_name.lower()
            for m in spec.optional_markers
        )

        steps.append({
            "number": number,
            "notebook": nb_file.name,
            "name": display_name,
            "optional": is_optional,
            "path": str(nb_file),
            "role": infer_role(nb_file.name),
        })

    steps.sort(key=lambda s: s["number"])
    return steps


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def write_manifest(
    run_dir: Path,
    pipeline_spec: PipelineSpec,
    steps: List[Dict[str, Any]],
    params: Dict[str, Any],
    env_vars: Dict[str, str],
) -> Path:
    """
    Write pipeline_manifest.json into the run's artifact directory.

    Returns the path to the written file.
    """
    manifest_dir = run_dir / "pipeline"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "pipeline_manifest.json"

    # Build role counts from steps
    role_counts: Dict[str, int] = {}
    for s in steps:
        role = s.get("role", infer_role(s["notebook"]))
        role_counts[role] = role_counts.get(role, 0) + 1

    manifest = {
        "pipeline_name": pipeline_spec.name,
        "pipeline_display_name": pipeline_spec.display_name,
        "notebooks_dir": pipeline_spec.notebooks_dir,
        "cwd_relative": pipeline_spec.cwd_relative,
        "supports_papermill": pipeline_spec.supports_papermill,
        "role_order": ROLE_ORDER,
        "role_counts": role_counts,
        "steps": [
            {
                "number": s["number"],
                "notebook": s["notebook"],
                "name": s["name"],
                "optional": s.get("optional", False),
                "role": s.get("role", infer_role(s["notebook"])),
            }
            for s in steps
        ],
        "params": {k: str(v) if not isinstance(v, (int, float, bool, type(None))) else v
                   for k, v in params.items()},
        "env_vars": env_vars,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    logger.info(f"Pipeline manifest written to {manifest_path}")
    return manifest_path
