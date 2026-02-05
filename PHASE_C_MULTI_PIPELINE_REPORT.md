# Multi-Pipeline Runner + Dataset Profiles — Implementation Report

**Branch:** `v3-phase-c`
**Date:** 2026-02-05
**Scope:** Steps 1–7 of the Multi-Pipeline Runner + Dataset Profiles specification

---

## 1. Executive Summary

Integrated the `/e2e/` notebook pipeline as a selectable option in the existing AML app (FastAPI + Celery + Streamlit + SQLite) without breaking existing behavior. The implementation adds:

- **4 pipeline variants** with conditional notebook selection
- **3 dataset modes** with sampling profiles
- **DuckDB out-of-core ingestion** for large datasets
- **Pipeline manifest** and prepared dataset metadata per run
- **Guardrails** for Full sampling confirmation and `/mnt` path warnings
- **Mermaid pipeline map** in the Streamlit UI
- **Role Map** with automatic role inference, colored pipeline visualization, and `/pipeline-manifest` API
- **Server-side paginated `/table` endpoint** via DuckDB

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (:8501)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────────────┐  │
│  │ 4 Pipeline│ │ 3 Dataset│ │  Sampling    │ │  Mermaid Pipeline │  │
│  │  Cards    │ │  Radio   │ │  Dropdown    │ │  Map              │  │
│  └─────┬────┘ └────┬─────┘ └──────┬───────┘ └───────────────────┘  │
└────────┼───────────┼──────────────┼──────────────────────────────────┘
         │           │              │
         ▼           ▼              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI API (:8000)                             │
│  POST /runs/ {pipeline_name, dataset_mode, sampling_profile, ...}   │
│  GET  /pipelines, /datasets, /sampling-profiles                     │
│  GET  /runs/{id}/table/{name}  (DuckDB pagination, 2000-row cap)    │
└────────┬─────────────────────────────────────────────────────────────┘
         │  Celery task dispatch
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    PipelineOrchestrator                               │
│  1. _extract_params() → dataset_mode, sampling_profile, max_rows     │
│  2. resolve_steps(spec, dataset_mode) → conditional 00 + ordered     │
│  3. write_manifest() → pipeline/pipeline_manifest.json               │
│  4. prepare_dataset() → prepared_data/*.parquet (if requires_ingest) │
│  5. _set_env_parameters() → AML_RUN_DIR, AML_PREPARED_DATA_DIR, ... │
│  6. Execute notebooks sequentially (papermill or nbclient)           │
│  7. Post-processing: metrics, artifact index, risk queue, cases      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Files Modified

| # | File | Lines | Changes |
|---|------|-------|---------|
| 1 | `app/pipeline_runner/pipeline_registry.py` | 362 | **Rewritten.** 4 pipeline variants, explicit ordered step lists, conditional 00 logic, `resolve_steps()`, `write_manifest()` |
| 2 | `app/datasets/dataset_registry.py` | 204 | **Rewritten.** 3 dataset modes, sampling profiles, `get_max_rows()`, `validate_dataset()`, `compute_cache_key()` |
| 3 | `app/datasets/saml_d_ingest.py` | 260 | **Rewritten.** `prepare_dataset()` (renamed from `ingest_saml_d`), output to `prepared_data/`, `prepared_dataset_meta.json`, `query_large_table` with 2000-row hard cap |
| 4 | `app/datasets/__init__.py` | 23 | Updated exports: added `validate_dataset`, `get_max_rows`, `compute_cache_key`, `SAMPLING_PROFILES` |
| 5 | `app/pipeline_runner/orchestrator.py` | ~960 | Import fixes, `dataset_mode`/`sampling_profile`/`max_rows` support, `_build_env_vars()`, `write_manifest()` call, `prepared_data/` dir, `prepare_dataset` ingestion |
| 6 | `app/api/routes/runs.py` | ~1000 | `RunParams` with `dataset_mode`, `sampling_profile`, `max_rows`, `confirm_full`, `seed`; Full sampling guardrail; `/mnt` path warning; `/table` searches `prepared_data/` |
| 7 | `app/api/routes/pipelines.py` | 91 | `resolve_steps` import (was `discover_pipeline_steps`), `dataset_mode` query param, new `/sampling-profiles` endpoint |
| 8 | `app/ui/streamlit_app.py` | ~3500 | 4 pipeline cards, 3 dataset radio, sampling profile dropdown, Full confirm checkbox, `/mnt` warning, Mermaid pipeline map, updated params |

---

## 4. Pipeline Registry

### 4.1 Pipeline Variants

| Name | Display Name | Notebooks Dir | Steps | Conditional 00 | CWD |
|------|-------------|---------------|-------|-----------------|-----|
| `legacy-root` | Legacy Hopsworks Pipeline | `.` | 12 (numeric discovery) | No | repo root |
| `e2e-core` | E2E PyTorch Core | `e2e` | 8 (01–08) + conditional 00 | Yes | `e2e/` |
| `e2e-dashboards` | E2E + Dashboards | `e2e` | 10 (01–10) + conditional 00 | Yes | `e2e/` |
| `e2e-realtime` | E2E Real-Time Only | `e2e` | 2 (11–12) | No | `e2e/` |

### 4.2 Conditional 00 Logic

| Dataset Mode | 00 Notebook Prepended |
|-------------|----------------------|
| `demodata` | None (data already exists) |
| `simulate` | `00_simulate_transactions.ipynb` |
| `saml-d` / `external` | `00_map_external_data.ipynb` |

### 4.3 Explicit Step Lists

```python
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

_E2E_DASHBOARD_STEPS = [
    "09_interactive_dashboard.ipynb",
    "10_advanced_analytics_dashboard.ipynb",
]

_E2E_REALTIME_STEPS = [
    "11_realtime_simulator.ipynb",
    "12_simulation_dashboard.ipynb",
]
```

### 4.4 Pipeline Manifest

Written to `{run_dir}/pipeline/pipeline_manifest.json` at orchestrator init:

```json
{
  "pipeline_name": "e2e-core",
  "pipeline_display_name": "E2E PyTorch Core",
  "notebooks_dir": "e2e",
  "cwd_relative": "e2e",
  "supports_papermill": false,
  "steps": [...],
  "params": {...},
  "env_vars": {
    "AML_RUN_ID": "...",
    "AML_RUN_DIR": "...",
    "AML_PREPARED_DATA_DIR": "...",
    "AML_DATASET_MODE": "demodata",
    ...
  },
  "created_at": "2026-02-05T..."
}
```

---

## 5. Dataset Registry

### 5.1 Dataset Modes

| Name | Display Name | Root | Approx Rows | Default Sampling | Requires Ingest | Cache |
|------|-------------|------|-------------|-----------------|-----------------|-------|
| `demodata` | Demo Data | `demodata/` | 67,000 | Full | No | — |
| `simulate` | Generate Synthetic | `demodata/` | varies | Full | No | — |
| `saml-d` | SAML-D (9.5M rows) | `/mnt/e/xx/demodata` | 9,500,000 | Quick | Yes (DuckDB) | `/tmp/aml-saml-d-cache` |

### 5.2 Sampling Profiles

| Profile | Max Rows | Description |
|---------|---------|-------------|
| Quick | 200,000 | Fast iteration |
| Standard | 1,000,000 | Balanced |
| Heavy | 3,000,000 | Thorough |
| Full | None (all) | Requires `confirm_full=true` on large datasets |

### 5.3 DatasetSpec Fields

```python
@dataclass
class DatasetSpec:
    name: str                          # "demodata" | "simulate" | "saml-d"
    display_name: str
    description: str
    dataset_root: Optional[str]        # absolute or relative to repo root
    expected_files: List[str]          # ["party.csv", "transactions.csv", "alert_transactions.csv"]
    approx_rows: Optional[int]
    default_sampling: str              # "Standard", "Quick", "Full"
    cache_root: Optional[str]          # Linux-side parquet cache path
    requires_ingest: bool              # True for saml-d (DuckDB)
    requires_dataset_root: bool        # user must supply dataset_root
    notes: str
```

---

## 6. SAML-D Ingestion (DuckDB Out-of-Core)

### 6.1 Function: `prepare_dataset()`

```python
prepare_dataset(
    data_root: Path,          # e.g. /mnt/e/xx/demodata
    prepared_dir: Path,       # e.g. artifacts/runs/<id>/prepared_data
    max_rows: Optional[int],  # from sampling profile
    cache_root: Optional[Path],  # /tmp/aml-saml-d-cache
) -> Dict[str, Any]
```

**Flow:**
1. Compute cache key (SHA256 of file sizes + mtimes + max_rows)
2. If cache hit → copy parquet files from cache to `prepared_dir/`
3. If cache miss → DuckDB ingestion:
   - `party.csv` → `party.parquet` (always full)
   - `transactions.csv` → `transactions.parquet` (sampled by `max_rows` via `USING SAMPLE`)
   - `alert_transactions.csv` → `alert_transactions.parquet` (always full)
4. Write `prepared_dataset_meta.json`
5. Populate cache for next time

**Memory guardrails:**
- DuckDB memory limit: 2GB
- DuckDB threads: 4
- `query_large_table()` hard cap: 2000 rows per request

### 6.2 Output: `prepared_dataset_meta.json`

```json
{
  "source": "/mnt/e/xx/demodata",
  "party_rows": 230000,
  "txn_rows": 200000,
  "alert_rows": 15000,
  "max_rows": 200000,
  "cached": false,
  "ingest_elapsed_s": 45.2,
  "created_at": "2026-02-05T..."
}
```

---

## 7. Orchestrator Enhancements

### 7.1 New Parameters Accepted

| Param | Default | Source |
|-------|---------|--------|
| `pipeline_name` | `"legacy-root"` | RunParams |
| `dataset_mode` | `"demodata"` | RunParams |
| `sampling_profile` | dataset default | RunParams or DatasetSpec.default_sampling |
| `max_rows` | from sampling profile | RunParams or `get_max_rows()` |
| `dataset_root` | from DatasetSpec | RunParams override |
| `confirm_full` | `false` | RunParams |
| `seed` | None | RunParams |

### 7.2 Environment Variables Set

For e2e pipelines (non-papermill), the orchestrator sets these env vars before each notebook:

| Variable | Example Value |
|----------|--------------|
| `AML_RUN_ID` | `abc123-...` |
| `AML_RUN_DIR` | `/path/to/artifacts/runs/abc123` |
| `AML_PREPARED_DATA_DIR` | `/path/to/artifacts/runs/abc123/prepared_data` |
| `AML_DATASET_MODE` | `demodata` |
| `AML_DATA_PATH` | `/path/to/demodata` |
| `AML_ARTIFACTS_DIR` | `/path/to/artifacts/runs/abc123` |
| `AML_SAMPLE_SIZE` | `20000` |
| `AML_EPOCHS` | `5` |
| `AML_THRESHOLD` | `0.99` |
| `AML_MAX_ROWS` | `200000` (if set) |
| `AML_SAMPLING_PROFILE` | `Quick` (if set) |
| `AML_SEED` | `42` (if set) |

### 7.3 Artifact Directory Structure

```
artifacts/runs/<run_id>/
├── pipeline/
│   └── pipeline_manifest.json       ← NEW
├── prepared_data/                    ← NEW (SAML-D parquet files)
│   ├── party.parquet
│   ├── transactions.parquet
│   ├── alert_transactions.parquet
│   └── prepared_dataset_meta.json
├── data/
├── models/
├── plots/
├── report/
├── logs/
├── notebooks_executed/
├── metrics/
├── queues/
└── cases/
```

---

## 8. API Changes

### 8.1 RunParams (POST /runs/)

```python
class RunParams(BaseModel):
    pipeline_name: str = "legacy-root"          # NEW default
    profile: str = "standard"
    dataset_mode: str = "demodata"              # NEW (was data_source)
    dataset_root: Optional[str] = None          # NEW
    sampling_profile: Optional[str] = None      # NEW
    max_rows: Optional[int] = None              # NEW
    confirm_full: bool = False                  # NEW
    sample_size: Optional[int] = None           # legacy compat
    epochs: Optional[int] = None
    threshold: Optional[float] = None
    notebook_timeout: Optional[int] = None
    skip_hyperparameter_tuning: bool = True
    generate_visualizations: bool = True
    generate_report: bool = True
    seed: Optional[int] = None                  # NEW
```

### 8.2 New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/pipelines` | List all 4 pipeline variants |
| GET | `/pipelines/{name}?dataset_mode=...` | Get pipeline detail with resolved steps |
| GET | `/datasets` | List all 3 dataset modes |
| GET | `/datasets/{name}` | Get dataset detail with validation |
| GET | `/sampling-profiles` | List sampling profiles with max_rows |
| GET | `/runs/{id}/table/{name}` | DuckDB paginated parquet access (searches `data/`, `prepared_data/`, `queues/`, `cases/`) |

### 8.3 Guardrails in API

1. **Pipeline validation:** 400 if `pipeline_name` not in registry
2. **Dataset validation:** 400 if `dataset_mode` not in registry
3. **Sampling profile validation:** 400 if `sampling_profile` not in `SAMPLING_PROFILES`
4. **Full confirm:** 400 if `sampling_profile=Full` on datasets with >500K rows without `confirm_full=true`
5. **`/mnt` path warning:** Server-side log warning when dataset root starts with `/mnt`
6. **Table name sanitization:** Only alphanumeric + underscore allowed (prevents path traversal)
7. **Row cap:** `query_large_table` hard cap of 2000 rows

---

## 9. Streamlit UI Changes

### 9.1 Pipeline Selection

4 pipeline cards in a row (was 2):
- Legacy Hopsworks Pipeline (`legacy-root`)
- E2E PyTorch Core (`e2e-core`)
- E2E + Dashboards (`e2e-dashboards`)
- E2E Real-Time Only (`e2e-realtime`)

### 9.2 Dataset Selection

3 radio options (was 2):
- Demo Data (`demodata`) — local demodata/ (~67K txns)
- Generate Synthetic (`simulate`) — Fresh synthetic data via 00_simulate_transactions
- SAML-D (9.5M rows) (`saml-d`) — /mnt/e/xx/demodata/ (realistic AML dataset)

### 9.3 Sampling Profile

Dropdown with: Quick, Standard, Heavy, Full

### 9.4 Guardrails in UI

- **Full confirm checkbox:** Appears when `sampling_profile=Full` and dataset has >500K rows. Start button is disabled until checkbox is checked.
- **`/mnt` warning:** Orange warning banner when dataset root starts with `/mnt`.
- **Heavy profile warning:** Warns about 12GB+ VRAM requirement.

### 9.5 Mermaid Pipeline Map

Expandable section renders a Mermaid `graph LR` flowchart of all resolved steps. Optional steps use slanted node shapes with yellow dashed borders. Falls back to a table view inside a nested expander.

---

## 10. Verification Results

### 10.1 Syntax Check (all 10 files)

```
OK: app/pipeline_runner/pipeline_registry.py
OK: app/pipeline_runner/orchestrator.py
OK: app/pipeline_runner/__init__.py
OK: app/datasets/dataset_registry.py
OK: app/datasets/saml_d_ingest.py
OK: app/datasets/__init__.py
OK: app/api/routes/runs.py
OK: app/api/routes/pipelines.py
OK: app/api/main.py
OK: app/ui/streamlit_app.py
```

### 10.2 Module Import Tests

```
1. Pipeline registry: OK
   Pipelines: ['legacy-root', 'e2e-core', 'e2e-dashboards', 'e2e-realtime']

2. Dataset registry: OK
   Datasets: ['demodata', 'simulate', 'saml-d']
   Sampling: {'Quick': 200000, 'Standard': 1000000, 'Heavy': 3000000, 'Full': None}

3. SAML-D ingest: OK (prepare_dataset, query_large_table)

4. Step resolution:
   legacy-root:     12 steps (demodata)
   e2e-core:         8 steps (demodata)
   e2e-dashboards:  10 steps (demodata)
   e2e-realtime:     2 steps (demodata)

5. Conditional 00 (saml-d):
   e2e-core + saml-d: 9 steps
   First step: 00_map_external_data.ipynb

6. Conditional 00 (simulate):
   e2e-core + simulate: 9 steps
   First step: 00_simulate_transactions.ipynb

7. get_max_rows:
   Quick:           200000
   Full:            None
   Quick + override: 50000

8. Dataset validation:
   demodata: valid=True, missing=[]
```

### 10.3 Orchestrator Import

```
Orchestrator import: OK
RUN_PROFILES: ['quick', 'standard', 'heavy']
```

### 10.4 API Model Import

```
RunParams defaults:
  pipeline_name: legacy-root
  dataset_mode: demodata
  sampling_profile: None
  confirm_full: False
```

### 10.5 FastAPI Route Count

```
Total: 46 routes (all loading correctly)

Key new routes:
  /pipelines
  /pipelines/{pipeline_name}
  /datasets
  /datasets/{dataset_name}
  /sampling-profiles
  /runs/{run_id}/table/{table_name}
```

---

## 11. Verification Curl Commands

```bash
# ── Discovery ──

# List all pipelines
curl http://localhost:8000/pipelines | python -m json.tool

# Get e2e-core steps with demodata (no 00)
curl "http://localhost:8000/pipelines/e2e-core?dataset_mode=demodata" | python -m json.tool

# Get e2e-core steps with saml-d (prepends 00_map)
curl "http://localhost:8000/pipelines/e2e-core?dataset_mode=saml-d" | python -m json.tool

# Get e2e-core steps with simulate (prepends 00_simulate)
curl "http://localhost:8000/pipelines/e2e-core?dataset_mode=simulate" | python -m json.tool

# List all datasets
curl http://localhost:8000/datasets | python -m json.tool

# Get demodata detail with validation
curl http://localhost:8000/datasets/demodata | python -m json.tool

# List sampling profiles
curl http://localhost:8000/sampling-profiles | python -m json.tool

# ── Run Creation ──

# Start legacy pipeline with demodata (backward compatible)
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name":"legacy-root","dataset_mode":"demodata"}' | python -m json.tool

# Start e2e-core with demodata, Full sampling (small dataset, no confirm needed)
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name":"e2e-core","dataset_mode":"demodata","sampling_profile":"Full"}' | python -m json.tool

# Start e2e-core with SAML-D, Quick sampling
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name":"e2e-core","dataset_mode":"saml-d","sampling_profile":"Quick"}' | python -m json.tool

# Start e2e-dashboards with simulate
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name":"e2e-dashboards","dataset_mode":"simulate"}' | python -m json.tool

# ── Guardrail Tests ──

# SHOULD FAIL (400): Full on SAML-D without confirm
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name":"e2e-core","dataset_mode":"saml-d","sampling_profile":"Full"}'

# SHOULD SUCCEED: Full on SAML-D with confirm
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name":"e2e-core","dataset_mode":"saml-d","sampling_profile":"Full","confirm_full":true}' | python -m json.tool

# SHOULD FAIL (400): Invalid pipeline name
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name":"nonexistent"}'

# SHOULD FAIL (400): Invalid dataset mode
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"dataset_mode":"nonexistent"}'

# SHOULD FAIL (400): Invalid sampling profile
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"sampling_profile":"SuperHeavy"}'

# ── Table Pagination ──

# Paginated table access (after a completed run)
curl "http://localhost:8000/runs/{run_id}/table/transactions?limit=50&offset=0" | python -m json.tool

# With sorting
curl "http://localhost:8000/runs/{run_id}/table/risk_queue?limit=100&sort_by=aml_score&sort_order=desc" | python -m json.tool

# SHOULD FAIL (400): Path traversal attempt
curl "http://localhost:8000/runs/{run_id}/table/../../etc/passwd"
```

---

## 12. Breaking Changes & Migration

### 12.1 API Parameter Renames

| Old (v1) | New (v2) | Notes |
|----------|----------|-------|
| `data_source: "demo-data"` | `dataset_mode: "demodata"` | Hyphen removed for consistency |
| `data_source: "saml-d"` | `dataset_mode: "saml-d"` | Unchanged |
| `pipeline_name: "legacy"` | `pipeline_name: "legacy-root"` | More descriptive |
| `pipeline_name: "e2e"` | `pipeline_name: "e2e-core"` | Distinguishes from dashboards/realtime |
| `data_path` | `dataset_root` | Clearer semantics |
| — | `sampling_profile` | New field |
| — | `max_rows` | New field |
| — | `confirm_full` | New guardrail field |
| — | `seed` | New field |

### 12.2 Internal Function Renames

| Old | New | Module |
|-----|-----|--------|
| `discover_pipeline_steps()` | `resolve_steps()` | pipeline_registry.py |
| `ingest_saml_d()` | `prepare_dataset()` | saml_d_ingest.py |
| `LEGACY_PIPELINE` | `LEGACY_ROOT` | pipeline_registry.py |

### 12.3 Artifact Directory Changes

| Old | New |
|-----|-----|
| `{run}/data/` (SAML-D parquet output) | `{run}/prepared_data/` |
| — | `{run}/pipeline/pipeline_manifest.json` |
| — | `{run}/prepared_data/prepared_dataset_meta.json` |

---

## 13. What Was NOT Changed

- **No notebook modifications.** All notebooks run unmodified.
- **No database schema changes.** `PipelineRun` still uses `params` JSON field for pipeline_name, dataset_mode, etc.
- **No Docker changes.** No Dockerfile or docker-compose modifications.
- **No Celery worker changes.** `tasks.py` passes `run.params` to orchestrator unchanged; orchestrator handles new params internally.
- **No existing endpoint signatures changed.** All existing GET endpoints remain backward compatible.
- **No `requirements.txt` changes** (DuckDB was already added in a prior session).

---

## 14. Known Limitations

1. **SAML-D requires `/mnt/e/xx/demodata` accessible.** If the mount is unavailable, the run will fail at ingestion.
2. **Mermaid rendering in Streamlit** depends on Streamlit version supporting Mermaid in markdown blocks (Streamlit >= 1.23).
3. **`e2e-realtime` pipeline** requires a prior `e2e-core` run with trained models in `e2e/models/`.
4. **Legacy pipeline** still uses numeric discovery (not explicit step list) for backward compatibility with arbitrary root notebooks.
5. **No automatic migration** for existing runs created with old `data_source`/`pipeline_name` values. The `params` JSON in SQLite still has old field names for historical runs.

---

## 15. Role Map for Pipeline Steps

### 15.1 Overview

Added an automatic **Role Map** that classifies every notebook step into a pipeline phase (role) based on filename pattern matching. Roles provide a higher-level view of the pipeline flow — from data ingestion through model training to dashboards — and are surfaced in the manifest, API, and Streamlit UI.

### 15.2 Role Definitions

Pipeline phases are defined in `ROLE_ORDER` in [pipeline_registry.py](app/pipeline_runner/pipeline_registry.py):

| Order | Role | Color | Matches |
|-------|------|-------|---------|
| 1 | Ingest | `#3B82F6` Blue | `00_*`, `map_external`, `simulate_transactions` |
| 2 | Features | `#8B5CF6` Purple | `data_loading`, `feature`, `prep_training`, `create_feature_groups` |
| 3 | Embeddings | `#EC4899` Pink | `graph_sage`, `embedding` |
| 4 | GAN | `#EF4444` Red | `wgan`, `adversarial`, `gan` + `anomaly` |
| 5 | Scoring | `#F59E0B` Amber | `scoring`, `anomaly`, `detect`, `predict_and_create` |
| 6 | Eval | `#10B981` Green | `evaluate`, `pattern_analysis` |
| 7 | Dashboards | `#06B6D4` Cyan | `dashboard`, `visualize`, `analytics` |
| 8 | Realtime | `#6366F1` Indigo | `realtime`, `simulator`, `model_server` |
| 9 | Other | `#6B7280` Gray | Fallback for unmatched filenames |

Rules are evaluated in order; first match wins.

### 15.3 Role Inference Results

**E2E Core (01–08):**

| Notebook | Role |
|----------|------|
| `01_data_loading_and_features.ipynb` | Features |
| `02_graph_sage_embeddings.ipynb` | Embeddings |
| `03_wgan_gp_anomaly_detector.ipynb` | GAN |
| `04_scoring_and_visualization.ipynb` | Scoring |
| `05_predict_and_evaluate.ipynb` | Eval |
| `06_visualize_results.ipynb` | Dashboards |
| `07_analytical_dashboard.ipynb` | Dashboards |
| `08_pattern_analysis.ipynb` | Eval |

**E2E Dashboards (adds 09–10):**

| Notebook | Role |
|----------|------|
| `09_interactive_dashboard.ipynb` | Dashboards |
| `10_advanced_analytics_dashboard.ipynb` | Dashboards |

**E2E Realtime (11–12):**

| Notebook | Role |
|----------|------|
| `11_realtime_simulator.ipynb` | Realtime |
| `12_simulation_dashboard.ipynb` | Realtime |

**Conditional 00 steps:**

| Notebook | Role |
|----------|------|
| `00_map_external_data.ipynb` | Ingest |
| `00_simulate_transactions.ipynb` | Ingest |

**Legacy Root (1–12):** All legacy notebooks also receive role annotations via the same `infer_role()` function applied in `_discover_legacy_steps()`.

### 15.4 Role Counts by Pipeline

| Pipeline | Ingest | Features | Embeddings | GAN | Scoring | Eval | Dashboards | Realtime |
|----------|--------|----------|------------|-----|---------|------|------------|----------|
| e2e-core (demodata) | 0 | 1 | 1 | 1 | 1 | 2 | 2 | 0 |
| e2e-core (saml-d) | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 0 |
| e2e-dashboards (demodata) | 0 | 1 | 1 | 1 | 1 | 2 | 4 | 0 |
| e2e-realtime | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |

### 15.5 Files Modified

| File | Changes |
|------|---------|
| `app/pipeline_runner/pipeline_registry.py` | Added `ROLE_ORDER`, `_ALL_E2E_NOTEBOOKS`, `infer_role()`, `get_excluded_notebooks()`; injected `role` into step dicts in `resolve_steps()` and `_discover_legacy_steps()`; added `role_order`, `role_counts`, per-step `role` to `write_manifest()` |
| `app/api/routes/pipelines.py` | `GET /pipelines/{name}` now returns `role_order`, `role_counts`, `excluded_notebooks` |
| `app/api/routes/runs.py` | Added `GET /runs/{run_id}/pipeline-manifest` endpoint returning the saved manifest JSON |
| `app/ui/streamlit_app.py` | Replaced Pipeline Map with Role Map: colored role ribbon, Mermaid flowchart with role-based styling, grouped steps by role, excluded notebooks list, step details table with Role column |

### 15.6 API Changes

#### `GET /pipelines/{pipeline_name}?dataset_mode=demodata`

New fields in response:

```json
{
  "role_order": ["Ingest", "Features", "Embeddings", "GAN", "Scoring", "Eval", "Dashboards", "Realtime", "Other"],
  "role_counts": {"Features": 1, "Embeddings": 1, "GAN": 1, "Scoring": 1, "Eval": 2, "Dashboards": 2},
  "excluded_notebooks": [
    {"notebook": "00_map_external_data.ipynb", "role": "Ingest", "name": "Map External Data"},
    {"notebook": "09_interactive_dashboard.ipynb", "role": "Dashboards", "name": "Interactive Dashboard"},
    ...
  ],
  "steps": [
    {"number": 1, "notebook": "01_data_loading_and_features.ipynb", "name": "Data Loading And Features", "optional": false, "path": "...", "role": "Features"},
    ...
  ]
}
```

#### `GET /runs/{run_id}/pipeline-manifest` (NEW)

Returns the saved `pipeline_manifest.json` from a completed run's artifact directory. Includes the full manifest with step roles, role counts, env vars, and creation timestamp.

```bash
curl http://localhost:8000/runs/<run-id>/pipeline-manifest | python -m json.tool
```

### 15.7 Pipeline Manifest Format

`{run_dir}/pipeline/pipeline_manifest.json` now includes:

```json
{
  "pipeline_name": "e2e-core",
  "pipeline_display_name": "E2E PyTorch Core",
  "notebooks_dir": "e2e",
  "cwd_relative": "e2e",
  "supports_papermill": false,
  "role_order": ["Ingest", "Features", "Embeddings", "GAN", "Scoring", "Eval", "Dashboards", "Realtime", "Other"],
  "role_counts": {"Features": 1, "Embeddings": 1, "GAN": 1, "Scoring": 1, "Eval": 2, "Dashboards": 2},
  "steps": [
    {"number": 1, "notebook": "01_data_loading_and_features.ipynb", "name": "Data Loading And Features", "optional": false, "role": "Features"},
    ...
  ],
  "params": {...},
  "env_vars": {...},
  "created_at": "2026-02-05T..."
}
```

### 15.8 Streamlit Role Map UI

The Pipeline Map section in `render_run_tab()` now shows:

1. **Role Ribbon** — Horizontal row of colored pills for each active role, connected by `→` arrows. Each pill shows the role name and step count.

2. **Mermaid Flowchart** — Directed graph with role-colored nodes. Each node shows step number and name. `classDef` styles match the role color palette.

3. **Grouped Steps** — Steps organized by role in `ROLE_ORDER` sequence. Each group shows the role badge, step number, and notebook name.

4. **Excluded Notebooks** — For e2e variants, lists notebooks available in the `e2e/` directory but not included in the selected pipeline variant (e.g., e2e-core excludes dashboards 09–10 and realtime 11–12).

5. **Step Details Table** — Full table with columns: Step, Notebook, Name, Role, Optional.

### 15.9 Verification Results

```text
Syntax check:     5/5 files pass (pipeline_registry, pipelines, runs, streamlit_app, orchestrator)
Role inference:   26/26 notebooks classified correctly (14 e2e + 12 legacy)
Pipeline steps:   All 4 pipelines return steps with "role" key
Excluded list:    e2e-core correctly excludes 6 notebooks (00_map, 00_sim, 09, 10, 11, 12)
Role counts:      e2e-dashboards = {Features:1, Embeddings:1, GAN:1, Scoring:1, Eval:2, Dashboards:4}
FastAPI routes:   47 routes loaded (up from 46, new /runs/{id}/pipeline-manifest)
New endpoint:     GET /runs/{run_id}/pipeline-manifest returns 200 with role data
```

### 15.10 Design Decisions

- **Filename-based inference** chosen over manual annotation to avoid maintaining a separate mapping. Rules are ordered by specificity to prevent false positives.
- **`_ALL_E2E_NOTEBOOKS` list** maintained manually (not glob-discovered) to ensure deterministic excluded-notebook detection even when files are missing.
- **Role colors** chosen for distinctiveness and accessibility, following Tailwind CSS palette conventions.
- **Mermaid rendering** preferred over heavy JS charting libraries to keep the Streamlit app lightweight and avoid additional dependencies.
