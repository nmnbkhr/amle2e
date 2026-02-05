# AML Pipeline Runner Application

A web-based interface for running and monitoring the AML end-to-end detection pipeline.

## Overview

This application provides:
- **Web UI** (Streamlit): Start runs, monitor progress, view dashboards and reports
- **REST API** (FastAPI): Programmatic access to all functionality
- **Background Processing** (Celery + Redis): Non-blocking notebook execution
- **Artifact Management**: Organized storage of all pipeline outputs

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit UI  │────▶│   FastAPI API   │────▶│  Celery Worker  │
│   (Port 8501)   │     │   (Port 8000)   │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                │                        │
                                ▼                        ▼
                        ┌───────────────┐      ┌─────────────────┐
                        │    SQLite     │      │   Notebooks     │
                        │   Database    │      │  (Papermill)    │
                        └───────────────┘      └────────┬────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │    Artifacts    │
                                               │  /artifacts/    │
                                               └─────────────────┘
```

## Quick Start

### Option A: One Command (Makefile)

```bash
make run          # Starts Redis → API → Celery → Streamlit
make status       # Check what's running
make stop         # Stop everything
make logs         # Tail all logs
```

### Option B: Manual (4 terminals)

```bash
conda activate amgan2

# Terminal 1 - Redis
redis-server

# Terminal 2 - API Server (port 8000)
uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# Terminal 3 - Celery Worker
celery -A app.workers.celery_app worker --loglevel=info

# Terminal 4 - Streamlit UI (port 8501)
streamlit run app/ui/streamlit_app.py
```

### Install Dependencies

```bash
conda activate amgan2
pip install -r requirements.txt
pip install -r app/requirements.txt
```

### Access the Application

- **Web UI**: http://localhost:8501
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/status/health

## Pipelines

| Pipeline | Notebooks | Description |
|----------|-----------|-------------|
| `legacy-root` | Root 1-12 | Original Hopsworks pipeline (papermill) |
| `e2e-core` | e2e/ 01-08 | PyTorch GraphSAGE + WGAN-GP core (env vars) |
| `e2e-dashboards` | e2e/ 01-10 | Core + interactive dashboards |
| `e2e-realtime` | e2e/ 11-12 | Real-time simulation (requires prior core run) |

Conditional step: `00_map_external_data` (saml-d) or `00_simulate_transactions` (simulate) prepended automatically.

## Datasets

| Dataset | Source | Size | Default Sampling |
|---------|--------|------|------------------|
| `demodata` | `demodata/` | ~67K rows | Full |
| `simulate` | `demodata/` | Generated fresh | Full |
| `saml-d` | `/mnt/e/xx/demodata` | ~9.5M rows | Quick (200K) |

Sampling profiles: Quick (200K), Standard (1M), Heavy (3M), Full (all).

## Role Map

Each notebook step is auto-classified into a pipeline phase:

`Ingest → Features → Embeddings → GAN → Scoring → Eval → Dashboards → Realtime`

Roles are shown in the Streamlit Pipeline Map (colored ribbon + Mermaid diagram) and persisted in `pipeline_manifest.json`.

## Directory Structure

```
/app
├── api/                    # FastAPI REST API
│   ├── main.py            # App entry point
│   └── routes/            # API endpoints
│       ├── runs.py        # Run management + pipeline-manifest
│       ├── pipelines.py   # Pipeline & dataset listing
│       ├── status.py      # Status monitoring
│       └── artifacts.py   # Artifact access
├── workers/               # Celery background tasks
│   ├── celery_app.py     # Celery configuration
│   └── tasks.py          # Task definitions
├── pipeline_runner/       # Notebook orchestration
│   ├── orchestrator.py   # Main execution logic
│   ├── pipeline_registry.py # 4 pipeline variants + role inference
│   ├── artifacts_index.py # Artifact indexing
│   ├── metrics_builder.py # Metrics extraction
│   └── output_map.yaml   # Deterministic output mapping
├── datasets/              # Dataset registry + ingestion
│   ├── dataset_registry.py # 3 dataset modes + sampling profiles
│   └── saml_d_ingest.py  # DuckDB out-of-core ingestion
├── db/                    # Database models
│   ├── models.py         # SQLAlchemy models
│   └── session.py        # Session management
├── reports/              # Report generation
│   ├── generator.py      # Report builder
│   └── templates/        # Jinja2 templates
├── ui/                   # Streamlit interface
│   └── streamlit_app.py  # Single-file app (9 tabs)
├── requirements.txt      # Dependencies
└── README_APP.md        # This file

/artifacts
└── runs/
    └── <run_id>/
        ├── data/              # Data files (CSV, Parquet)
        ├── prepared_data/     # DuckDB-ingested parquet (SAML-D)
        ├── pipeline/          # pipeline_manifest.json
        ├── models/            # Trained models
        ├── plots/             # Visualizations (PNG)
        ├── logs/              # Execution logs
        ├── notebooks_executed/ # Executed notebooks
        ├── metrics/           # metrics.json
        ├── queues/            # Risk-ranked tier queues
        ├── cases/             # Investigation cases
        ├── report/            # HTML report
        └── artifact_index.json
```

## Run Profiles

| Profile  | Sample Size | Epochs | Threshold | Use Case |
|----------|-------------|--------|-----------|----------|
| Quick    | 5,000       | 2      | 0.99      | Testing  |
| Standard | 20,000      | 5      | 0.99      | Normal   |
| Heavy    | 100,000     | 10     | 0.995     | Full (12GB+ VRAM) |

## API Endpoints

### Pipelines & Datasets

- `GET /pipelines` - List all registered pipelines
- `GET /pipelines/{name}?dataset_mode=...` - Pipeline detail with steps, roles, excluded notebooks
- `GET /datasets` - List all dataset profiles
- `GET /datasets/{name}` - Dataset detail with validation status
- `GET /sampling-profiles` - Sampling profiles (Quick/Standard/Heavy/Full)

### Runs
- `POST /runs/` - Start new pipeline run
- `GET /runs/` - List all runs
- `GET /runs/{run_id}` - Get run details
- `GET /runs/{run_id}/metrics` - Get run metrics
- `GET /runs/{run_id}/artifact-index` - Get artifact index
- `GET /runs/{run_id}/pipeline-manifest` - Get pipeline manifest (steps, roles, env vars)
- `GET /runs/{run_id}/table/{name}` - DuckDB-paginated parquet table (2000-row cap)
- `POST /runs/{run_id}/cancel` - Cancel running pipeline
- `GET /runs/profiles` - Get available run profiles

### Status
- `GET /status/health` - Health check
- `GET /status/{run_id}` - Detailed run status with steps
- `GET /status/{run_id}/logs` - Execution logs

### Artifacts
- `GET /artifacts/{run_id}` - List all artifacts
- `GET /artifacts/{run_id}/plots` - List visualizations
- `GET /artifacts/{run_id}/tables` - List data tables
- `GET /artifacts/{run_id}/table/{name}` - Get paginated table data with sorting
- `GET /artifacts/{run_id}/anomalies` - Get anomaly data (score filtering)
- `GET /artifacts/{run_id}/report` - Get HTML report
- `GET /artifacts/{run_id}/bundle` - Download run bundle ZIP
- `GET /artifacts/{run_id}/summary` - Get run summary with artifact counts
- `GET /artifacts/{run_id}/file/{path}` - Download file

## Run Bundle Download

Each completed run can be exported as a portable ZIP bundle containing all key artifacts:

**Bundle Contents:**
- `metrics/metrics.json` - Pipeline metrics and statistics
- `artifact_index.json` - Index of all generated artifacts
- `report/report.html` - Full HTML report
- `data/alert_nodes_td.csv` - Primary anomalies table (if available)
- `plots/` - Key visualizations:
  - `dashboard_executive.png`
  - `anomaly_distribution.png`
  - `top_anomalies.png`
  - `top_suspicious_by_volume.png`
- `logs/*.log` - Execution logs

**Download Methods:**
1. **Web UI**: Report tab → "Download Run Bundle" button
2. **API**: `GET /artifacts/{run_id}/bundle`

## Output Mapping

The pipeline uses `app/pipeline_runner/output_map.yaml` for deterministic file lookups:

- Maps artifact types to expected file paths
- Provides column aliases for flexible data handling
- Configures bundle contents and key plots
- Falls back to heuristics when exact paths not found

## Troubleshooting

### Redis Connection Failed
```
Error: Cannot connect to Redis at localhost:6379
```
**Solution:** Ensure Redis is running:
```bash
redis-server
# Or check if already running:
redis-cli ping
```

### Celery Worker Not Found
```
Error: No workers available
```
**Solution:** Start the Celery worker:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

### Notebook Execution Failed
Check the logs at:
```
artifacts/runs/<run_id>/logs/<notebook_name>.log
```

Common issues:
- **Kernel not found**: Install ipykernel in your environment
  ```bash
  pip install ipykernel
  python -m ipykernel install --user --name amgan2
  ```
- **Timeout**: Increase timeout in run parameters
- **Memory**: Reduce sample_size or use "quick" profile

### Database Errors
The SQLite database is stored at `app/aml_pipeline.db`. To reset:
```bash
rm app/aml_pipeline.db
# Restart the API server - it will recreate the database
```

## Adding New Notebooks/Steps

**Legacy pipeline** (`legacy-root`): Auto-discovers `<number>_<name>.ipynb` in root. Add a new numbered notebook and restart.

**E2E pipelines** (`e2e-core`, `e2e-dashboards`, `e2e-realtime`): Steps are explicitly listed in `app/pipeline_runner/pipeline_registry.py`. To add a step:

1. Create the notebook in `e2e/` (e.g., `08b_new_analysis.ipynb`)
2. Add the filename to the relevant `_E2E_*_STEPS` list in `pipeline_registry.py`
3. Add it to `_ALL_E2E_NOTEBOOKS` for excluded-notebook tracking
4. Restart the API server

**E2E notebooks** read parameters via environment variables (no papermill cells):

```python
import os
run_dir = os.environ.get("AML_RUN_DIR", "artifacts/runs/local")
data_path = os.environ.get("AML_DATA_PATH", "../demodata")
max_rows = int(os.environ.get("AML_MAX_ROWS", "0")) or None
```

**Legacy notebooks** use papermill parameter cells:

```python
# First cell tagged with "parameters"
run_id = ""
artifacts_dir = ""
sample_size = 20000
epochs = 5
threshold = 0.99
```

## Development

### Running Tests
```bash
pytest app/tests/
```

### Code Style
```bash
# Format
black app/

# Lint
flake8 app/
```

### Database Migrations
Currently using SQLite with auto-creation. For production, consider:
- Alembic for migrations
- PostgreSQL for concurrent access

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `API_URL` | `http://localhost:8000` | API URL for Streamlit |
| `AML_RUN_ID` | (set per run) | Run identifier |
| `AML_RUN_DIR` | (set per run) | Artifact directory for current run |
| `AML_DATASET_MODE` | `demodata` | Dataset mode: demodata, simulate, saml-d |
| `AML_DATA_PATH` | `demodata/` | Resolved dataset root path |
| `AML_PREPARED_DATA_DIR` | (set per run) | DuckDB-ingested output dir |
| `AML_MAX_ROWS` | (from profile) | Row limit for sampling |
| `AML_SAMPLING_PROFILE` | (from dataset) | Quick, Standard, Heavy, or Full |
| `AML_SAMPLE_SIZE` | `20000` | Legacy sample size param |
| `AML_EPOCHS` | `5` | Training epochs |
| `AML_THRESHOLD` | `0.99` | Anomaly threshold |
| `AML_SEED` | (optional) | Random seed for reproducibility |

## License

Part of the AML End-to-End Detection Pipeline project.
