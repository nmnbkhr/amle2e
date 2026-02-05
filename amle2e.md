# AML End-to-End: Complete Project Summary

## Overview

This project implements a **Graph Neural Network-based Anti-Money Laundering (AML) detection system** that analyzes transaction networks to identify suspicious activities. It includes two pipeline generations, a full web application stack, and interactive dashboards.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                       AML DETECTION SYSTEM                                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌──────────────┐  │
│  │  Data    │ → │  Graph   │ → │ Embedding │ → │ Anomaly  │ → │  Scoring &   │  │
│  │  Ingest  │   │ Features │   │ (SAGE/N2V)│   │ Detector │   │  Dashboards  │  │
│  └─────────┘   └──────────┘   └───────────┘   └──────────┘   └──────────────┘  │
│                                                                                  │
│  Web App:  Streamlit UI  ←→  FastAPI API  ←→  Celery + Redis  ←→  Notebooks     │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Key capabilities:**

- Two pipeline generations: Legacy (Node2Vec + Autoencoder) and E2E (GraphSAGE + WGAN-GP)
- Multi-dataset support: demo data, synthetic generation, and SAML-D (9.5M rows)
- Web application with Streamlit UI, FastAPI REST API, Celery background processing
- 12+ interactive dashboards and visualizations
- Real-time transaction simulation with live scoring
- Risk ranking, case building, and pattern-based rule extraction

---

## Environment

| Component | Version |
|-----------|---------|
| Conda environment | `amgan2` |
| Python | 3.10 |
| PyTorch | 2.6.0+cu124 |
| PyTorch Geometric | 2.7.0 |
| TensorFlow | >= 2.15.0 (legacy pipeline) |
| DuckDB | 1.4.4 |
| OS | Linux (WSL2 supported) |

### Setup

```bash
# Option 1: Automated setup
chmod +x setup_env.sh
./setup_env.sh          # CPU-only
./setup_env.sh --gpu    # With CUDA support

# Option 2: Manual
conda create -n amgan2 python=3.10 -y
conda activate amgan2
pip install -r requirements.txt
pip install -e .
python -m ipykernel install --user --name amgan2
```

### Key Dependencies

| Category | Packages |
|----------|----------|
| ML/AI | torch>=2.5.0, torch_geometric>=2.4.0, scikit-learn>=1.3.0, tensorflow>=2.15.0 |
| Graph | networkx>=3.0, stellargraph==1.2.1, node2vec>=0.4.6 |
| Visualization | plotly>=5.10.0, matplotlib>=3.7.0, seaborn>=0.13.0, dash>=2.14.0 |
| Web stack | fastapi>=0.95.0, streamlit>=1.20.0, celery>=5.2.0, redis>=4.5.0 |
| Data | pandas>=2.0.0, pyarrow>=14.0.0, duckdb>=0.9.0, sqlalchemy>=2.0.0 |
| Jupyter | ipykernel>=6.0.0, ipywidgets>=8.0.0, papermill |

---

## Project Structure

```
amle2e/
├── e2e/                              # E2E Pipeline (PyTorch GraphSAGE + WGAN-GP)
│   ├── 00_map_external_data.ipynb    #   Map SAML-D/external datasets
│   ├── 00_simulate_transactions.ipynb#   Generate synthetic AML data
│   ├── 01_data_loading_and_features  #   Load CSVs, 9 node features
│   ├── 02_graph_sage_embeddings      #   PyG SAGEConv 2-layer (9→128→64)
│   ├── 03_wgan_gp_anomaly_detector   #   WGAN-GP: Discriminator/Generator/Encoder
│   ├── 04_scoring_and_visualization  #   Score nodes, ROC/PR curves
│   ├── 05_predict_and_evaluate       #   Train/test accuracy, confusion matrix
│   ├── 06_visualize_results          #   Network graph analysis
│   ├── 07_analytical_dashboard       #   Financial analysis dashboard
│   ├── 08_pattern_analysis           #   Rule extraction
│   ├── 09_interactive_dashboard      #   Dash 5-tab dashboard (port 8050)
│   ├── 10_advanced_analytics_dashboard#  AML Scores + Cases + Risk Ranking
│   ├── 11_realtime_simulator         #   Live transaction stream + scoring
│   ├── 12_simulation_dashboard       #   Dash Start/Stop/Reset dashboard (port 8052)
│   └── gan_anomaly.py                #   PyTorch WGAN-GP module
│
├── 1_create_feature_groups.ipynb     # Legacy Pipeline (Node2Vec + Autoencoder)
├── 2_prep_training_dataset_for_embeddings.ipynb
├── 3_maggy_node_embeddings.ipynb
├── ...through...
├── 12_aml_pattern_analysis.ipynb
├── 13_interactive_dashboard.ipynb
│
├── app/                              # Web Application
│   ├── api/                          #   FastAPI REST API (port 8000)
│   │   ├── main.py                   #     App entry point
│   │   └── routes/                   #     Endpoints: runs, pipelines, status, artifacts
│   ├── workers/                      #   Celery background tasks
│   │   ├── celery_app.py             #     Celery configuration
│   │   └── tasks.py                  #     Task definitions
│   ├── pipeline_runner/              #   Notebook orchestration
│   │   ├── orchestrator.py           #     Main execution logic
│   │   ├── pipeline_registry.py      #     4 pipeline variants + role inference
│   │   ├── artifacts_index.py        #     Artifact indexing
│   │   ├── metrics_builder.py        #     Metrics extraction
│   │   └── output_map.yaml           #     Deterministic output mapping
│   ├── datasets/                     #   Dataset registry + ingestion
│   │   ├── dataset_registry.py       #     3 dataset modes + sampling profiles
│   │   └── saml_d_ingest.py          #     DuckDB out-of-core ingestion
│   ├── db/                           #   SQLAlchemy + SQLite
│   ├── reports/                      #   Jinja2 HTML report generation
│   └── ui/                           #   Streamlit interface (port 8501)
│       └── streamlit_app.py          #     Single-file app (9 tabs)
│
├── demodata/                         # Bundled demo dataset (~67K transactions)
│   ├── party.csv                     #   partyId, partyType
│   ├── transactions.csv              #   tran_id, tx_type, base_amt, tran_timestamp, src, dst
│   └── alert_transactions.csv        #   alert_id, alert_type, is_sar, tran_id
│
├── artifacts/runs/<run_id>/          # Per-run output (auto-created)
│   ├── data/                         #   CSV, Parquet data files
│   ├── prepared_data/                #   DuckDB-ingested parquet (SAML-D)
│   ├── pipeline/                     #   pipeline_manifest.json
│   ├── models/                       #   Trained model weights
│   ├── plots/                        #   Visualization PNGs
│   ├── logs/                         #   Execution logs
│   ├── notebooks_executed/           #   Executed .ipynb files
│   ├── metrics/                      #   metrics.json
│   ├── queues/                       #   Risk-ranked tier queues
│   ├── cases/                        #   Investigation cases
│   ├── report/                       #   HTML report
│   └── artifact_index.json
│
├── Makefile                          # make run / stop / status / logs
├── setup_env.sh                      # Automated environment setup
├── setup.py                          # pip install -e .
└── requirements.txt                  # All Python dependencies
```

---

## Two Pipeline Generations

### Legacy Pipeline (Root Notebooks 1-12)

Uses **Node2Vec graph embeddings** + **TensorFlow Autoencoder** anomaly detection.

| Step | Notebook | Purpose |
|------|----------|---------|
| 0 | `0_map_saml_d_to_demodata` | Map external data (optional) |
| 1 | `1_create_feature_groups` | Load data, create transaction graph |
| 2 | `2_prep_training_dataset_for_embeddings` | Format edges for Node2Vec |
| 3 | `3_maggy_node_embeddings` | Hyperparameter tuning (walk_length, emb_size) |
| 4 | `4_compute_node_embeddings` | Generate Node2Vec embeddings (32-dim) |
| 5 | `5_predict_and_create_node_embeddings_fg` | Merge embeddings + labels |
| 6 | `6_create_anomaly_detection_td` | Train/eval split |
| 7 | `7_maggy_adversarial_aml` | Autoencoder hyperparameter tuning |
| 8 | `8_train_adversarial_aml` | Train autoencoder (Input→16→8→Latent→16→32) |
| 9 | `9_aml_model_server` | Model serving & inference |
| 10 | `10_visualize_results` | Network visualization |
| 11 | `11_analytical_dashboard` | Multi-tab analytics |
| 12 | `12_aml_pattern_analysis` | Rule extraction |

**Parameterization:** Papermill parameter cells (run_id, artifacts_dir, sample_size, epochs, threshold).

### E2E Pipeline (e2e/ Notebooks 00-12)

Uses **PyTorch Geometric GraphSAGE** (2-layer, 9→128→64) + **WGAN-GP** (Wasserstein GAN with Gradient Penalty) anomaly detection.

| Step | Notebook | Role | Purpose |
|------|----------|------|---------|
| 00 | `00_map_external_data` | Ingest | Map SAML-D/external data (conditional) |
| 00 | `00_simulate_transactions` | Ingest | Generate synthetic data (conditional) |
| 01 | `01_data_loading_and_features` | Features | Load CSVs, engineer 9 node features |
| 02 | `02_graph_sage_embeddings` | Embeddings | PyG SAGEConv 2-layer embeddings |
| 03 | `03_wgan_gp_anomaly_detector` | GAN | WGAN-GP: Discriminator + Generator + Encoder |
| 04 | `04_scoring_and_visualization` | Scoring | Score nodes, ROC/PR curves |
| 05 | `05_predict_and_evaluate` | Eval | Train/test accuracy, confusion matrix |
| 06 | `06_visualize_results` | Dashboards | Network graph analysis |
| 07 | `07_analytical_dashboard` | Dashboards | Financial analysis |
| 08 | `08_pattern_analysis` | Eval | Rule extraction |
| 09 | `09_interactive_dashboard` | Dashboards | Dash 5-tab interactive dashboard |
| 10 | `10_advanced_analytics_dashboard` | Dashboards | AML Scores + Cases + Risk Ranking |
| 11 | `11_realtime_simulator` | Realtime | Live transaction stream + scoring |
| 12 | `12_simulation_dashboard` | Realtime | Dash Start/Stop/Reset simulation |

**Parameterization:** Environment variables (no papermill cells):
```python
run_dir   = os.environ.get("AML_RUN_DIR", "artifacts/runs/local")
data_path = os.environ.get("AML_DATA_PATH", "../demodata")
max_rows  = int(os.environ.get("AML_MAX_ROWS", "0")) or None
```

**WGAN-GP Model** (`e2e/gan_anomaly.py`):
- **Discriminator**: input_dim → dense layers → 1 (Wasserstein critic)
- **Generator**: latent_dim → dense layers → input_dim
- **Encoder**: input_dim → dense layers → latent_dim
- **Anomaly score**: `||x - G(E(x))||^2` (reconstruction error through encoder→generator)

---

## Pipeline Registry

The app supports 4 pipeline variants, registered in `app/pipeline_runner/pipeline_registry.py`:

| Pipeline | Notebooks | Description | Conditional 00 |
|----------|-----------|-------------|-----------------|
| `legacy-root` | Root 1-12 | Node2Vec + TF Autoencoder (papermill) | No |
| `e2e-core` | e2e/ 01-08 | GraphSAGE + WGAN-GP core | Yes |
| `e2e-dashboards` | e2e/ 01-10 | Core + interactive dashboards | Yes |
| `e2e-realtime` | e2e/ 11-12 | Real-time simulation (requires prior core run) | No |

**Conditional step 00 logic:**

- Dataset mode `saml-d` or `external` → prepend `00_map_external_data.ipynb`
- Dataset mode `simulate` → prepend `00_simulate_transactions.ipynb`
- Dataset mode `demodata` → skip (data already exists)

**Role Map** — each step is auto-classified into a pipeline phase:
```
Ingest → Features → Embeddings → GAN → Scoring → Eval → Dashboards → Realtime
```
Roles are visualized in the Streamlit Pipeline Map tab with a colored ribbon, Mermaid diagram, and grouped step table.

---

## Dataset Registry

Three dataset modes with configurable sampling profiles, in `app/datasets/dataset_registry.py`:

| Dataset | Source | Size | Default Sampling | Requires Ingest |
|---------|--------|------|------------------|-----------------|
| `demodata` | `demodata/` | ~7.5K parties, ~67K txns | Full | No |
| `simulate` | `demodata/` | Variable (generated) | Full | No |
| `saml-d` | `/mnt/e/xx/demodata` | ~230K parties, ~9.5M txns | Quick (200K) | Yes (DuckDB) |

**Sampling Profiles:**

| Profile | Max Rows | Use Case |
|---------|----------|----------|
| Quick | 200,000 | Fast testing |
| Standard | 1,000,000 | Normal runs |
| Heavy | 3,000,000 | Deep analysis |
| Full | No limit | Complete dataset (requires `confirm_full=true` on large datasets) |

**SAML-D Ingestion:** DuckDB out-of-core processing (`app/datasets/saml_d_ingest.py`) with 2GB memory limit, SHA256 fingerprint caching, output to `prepared_data/` as Parquet.

**Data Format Contract:**

- `party.csv`: `partyId` (8-char hex), `partyType`
- `transactions.csv`: `tran_id, tx_type, base_amt, tran_timestamp, src, dst`
- `alert_transactions.csv`: `alert_id, alert_type, is_sar, tran_id`
- tx_type encoding: CASH_IN=0, CASH_OUT=1, DEBIT=2, PAYMENT=3, TRANSFER=4

---

## Web Application

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit UI  │────▶│   FastAPI API   │────▶│  Celery Worker  │
│   (Port 8501)   │     │   (Port 8000)   │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                               │                         │
                               ▼                         ▼
                       ┌───────────────┐       ┌─────────────────┐
                       │    SQLite     │       │   Notebooks     │
                       │   Database    │       │  (Papermill /   │
                       └───────────────┘       │   Env Vars)     │
                                               └────────┬────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │   Artifacts     │
                                               │ /artifacts/runs │
                                               └─────────────────┘
```

### Running the App

```bash
conda activate amgan2

# Option 1: One command (recommended)
make run          # Starts Redis → API → Celery → Streamlit
make status       # Check what's running
make stop         # Stop everything
make logs         # Tail all logs

# Option 2: Manual (4 terminals)
redis-server                                                    # Terminal 1
uvicorn app.api.main:app --host 0.0.0.0 --port 8000           # Terminal 2
celery -A app.workers.celery_app worker --loglevel=info        # Terminal 3
streamlit run app/ui/streamlit_app.py                          # Terminal 4
```

**Access points:**

- Web UI: <http://localhost:8501>
- API Docs: <http://localhost:8000/docs>
- Health Check: <http://localhost:8000/status/health>

### API Endpoints

| Category | Endpoint | Description |
|----------|----------|-------------|
| **Pipelines** | `GET /pipelines` | List all 4 pipeline variants |
| | `GET /pipelines/{name}?dataset_mode=...` | Pipeline detail with steps, roles, excluded notebooks |
| | `GET /datasets` | List all dataset profiles |
| | `GET /sampling-profiles` | Sampling profiles (Quick/Standard/Heavy/Full) |
| **Runs** | `POST /runs/` | Start new pipeline run |
| | `GET /runs/` | List all runs |
| | `GET /runs/{run_id}` | Run details |
| | `GET /runs/{run_id}/metrics` | Run metrics |
| | `GET /runs/{run_id}/pipeline-manifest` | Steps, roles, env vars |
| | `GET /runs/{run_id}/table/{name}` | DuckDB-paginated parquet table (2000-row cap) |
| | `POST /runs/{run_id}/cancel` | Cancel running pipeline |
| **Status** | `GET /status/health` | Health check |
| | `GET /status/{run_id}` | Detailed run status with steps |
| | `GET /status/{run_id}/logs` | Execution logs |
| **Artifacts** | `GET /artifacts/{run_id}` | List all artifacts |
| | `GET /artifacts/{run_id}/plots` | List visualizations |
| | `GET /artifacts/{run_id}/anomalies` | Anomaly data (score filtering) |
| | `GET /artifacts/{run_id}/report` | HTML report |
| | `GET /artifacts/{run_id}/bundle` | Download run bundle ZIP |

### Streamlit UI Tabs

The Streamlit app (`app/ui/streamlit_app.py`) has 9 tabs:

1. **Launch** — Select pipeline, dataset, sampling profile, start run
2. **Progress** — Live step-by-step progress with status badges
3. **Pipeline Map** — Role ribbon, Mermaid diagram, grouped steps, excluded notebooks
4. **Metrics** — Key pipeline metrics (AUC, precision, recall)
5. **Plots** — Generated visualizations gallery
6. **Tables** — DuckDB-paginated data exploration
7. **Anomalies** — Filtered anomaly results
8. **Report** — Full HTML report with download bundle
9. **History** — All past runs with status

---

## Scoring & Risk Ranking

### Anomaly Score Interpretation

| Score Range | Risk Level | Action |
|-------------|-----------|--------|
| < threshold | LOW | Monitor |
| threshold – 2x | MEDIUM | Review |
| 2x – 3x threshold | HIGH | Investigate |
| > 3x threshold | CRITICAL | Escalate |

### Risk Tiers (Case Builder)

| Tier | Percentile | Description |
|------|-----------|-------------|
| T1 | Top 0.5% | Highest risk — immediate investigation |
| T2 | 0.5 – 2% | High risk — prioritized review |
| T3 | 2 – 5% | Medium risk — scheduled review |
| T4 | Remainder | Low risk — monitoring |

### Detection Pattern Rules (from NB 08/12)

```text
AMOUNT RULES:
├── Total volume > $150,000 → 98% suspicious
├── Max single transaction > $2,500 → 96% suspicious
└── High variance in amounts → 94% suspicious

NETWORK RULES:
├── Sends to > 15 unique recipients → 97% suspicious (STRUCTURING)
├── Receives from > 10 unique senders → 95% suspicious (COLLECTION)
└── Flow imbalance > 80% → 93% suspicious (LAYERING)

FREQUENCY RULES:
├── Total transactions > 50 → 96% suspicious
└── Repeated transactions to same target > 5 → 94% suspicious
```

### Key Thresholds (Case Builder)

| Threshold | Value |
|-----------|-------|
| FAN_RATIO_THRESHOLD | 3.0 |
| HUB_DOMINANCE_THRESHOLD | 5.0 |
| CYCLE_MAX_LENGTH | 3 |

---

## Run Profiles

| Profile | Sample Size | Epochs | Threshold | Use Case |
|---------|-------------|--------|-----------|----------|
| Quick | 5,000 | 2 | 0.99 | Testing |
| Standard | 20,000 | 5 | 0.99 | Normal |
| Heavy | 100,000 | 10 | 0.995 | Full (12GB+ VRAM) |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `API_URL` | `http://localhost:8000` | API URL for Streamlit |
| `AML_RUN_ID` | (per run) | Run identifier |
| `AML_RUN_DIR` | (per run) | Artifact directory for current run |
| `AML_DATASET_MODE` | `demodata` | Dataset: demodata, simulate, saml-d |
| `AML_DATA_PATH` | `demodata/` | Resolved dataset root path |
| `AML_PREPARED_DATA_DIR` | (per run) | DuckDB-ingested output dir |
| `AML_MAX_ROWS` | (from profile) | Row limit for sampling |
| `AML_SAMPLING_PROFILE` | (from dataset) | Quick, Standard, Heavy, Full |
| `AML_SAMPLE_SIZE` | `20000` | Legacy sample size param |
| `AML_EPOCHS` | `5` | Training epochs |
| `AML_THRESHOLD` | `0.99` | Anomaly threshold |
| `AML_SEED` | (optional) | Random seed for reproducibility |

---

## Implementation Phases

### Phase A — Core Pipeline Runner

- Celery + Redis background processing
- Papermill notebook execution for legacy pipeline
- SQLite run metadata storage
- Artifact collection and indexing
- HTML report generation (Jinja2 templates)
- Streamlit UI with Launch, Progress, Metrics, Plots, Tables, Report tabs

### Phase B — Scoring, Risk Ranking & Case Builder

- Risk ranking with tier-based queues (T1-T4)
- Case builder with automated investigation case generation
- AML scoring integration across pipelines
- Progress tracking improvements
- Advanced analytics dashboard (NB 10)

### Phase C — Multi-Pipeline Runner + Dataset Profiles

- Pipeline Registry: 4 pipeline variants with conditional notebook selection
- Dataset Registry: 3 dataset modes with sampling profiles
- DuckDB out-of-core ingestion for SAML-D (9.5M rows)
- Pipeline manifest and prepared dataset metadata per run
- Role Map with automatic role inference and colored visualization
- Mermaid pipeline diagram in Streamlit
- `/pipeline-manifest` and `/table` API endpoints (DuckDB pagination, 2000-row cap)
- Guardrails: Full sampling confirmation, /mnt path warnings, table name sanitization

### Real-Time Simulation (NB 11-12)

- Live transaction stream generation with configurable patterns
- GraphSAGE embedding updates on growing graph
- WGAN-GP real-time anomaly scoring
- Dash dashboard with Start/Stop/Reset controls (NB 12)
- Live-updating KPIs, score time series, confusion matrix
- Latency analysis and ego-graph investigation tabs

---

## Technical Details

### GraphSAGE (E2E Pipeline)

- 2-layer SAGEConv: 9 input features → 128 → 64 output dimensions
- Neighborhood sampling on transaction graph
- Inductive learning: generalizes to unseen nodes

### WGAN-GP Anomaly Detection (E2E Pipeline)

- Wasserstein distance with gradient penalty (more stable than vanilla GAN)
- Encoder maps nodes to latent space; Generator reconstructs
- Anomaly = high reconstruction error: `||x - G(E(x))||^2`
- Training: alternating critic/generator updates with GP regularization

### Node2Vec (Legacy Pipeline)

- Biased random walks controlled by `p` (return) and `q` (in-out) parameters
- Word2Vec training on walks (nodes as "words")
- Produces 32-dimensional node embeddings

### Autoencoder (Legacy Pipeline)

- TensorFlow/Keras: Input(32) → Dense(16) → Dense(8) → Latent(8) → Dense(16) → Output(32)
- MSE loss, 50 epochs, batch size 32
- High reconstruction error = anomaly

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Wrong conda env | Verify: `conda activate amgan2 && which python` |
| `CuDNN version mismatch` | `pip install --upgrade nvidia-cudnn-cu12>=9.3.0` |
| `No module named ...` | `pip install -r requirements.txt` |
| Widget CDN error | Add `"jupyter.widgetScriptSources": ["jsdelivr.com", "unpkg.com"]` to VS Code settings |
| Out of memory | Use Quick profile or reduce sample_size |
| Redis connection failed | `redis-server` or `redis-cli ping` |
| Celery worker not found | `celery -A app.workers.celery_app worker --loglevel=info` |
| Kernel not found | `python -m ipykernel install --user --name amgan2` |
| Database errors | Delete `app/aml_pipeline.db` and restart API |
| PyG install mismatch | Use `-f https://data.pyg.org/whl/torch-2.6.0+cu124.html` |

---

## References

- [Adversarial Anomaly Detection Paper](https://arxiv.org/pdf/1905.11034.pdf)
- [Node2Vec Paper](https://arxiv.org/abs/1607.00653)
- [GraphSAGE Paper](https://arxiv.org/abs/1706.02216)
- [WGAN-GP Paper](https://arxiv.org/abs/1704.00028)
- [Original Hopsworks AML Demo](https://github.com/logicalclocks/hopsworks-tutorials)
- [AMLSim Transaction Simulator](https://github.com/IBM/AMLSim)

---

AML End-to-End Detection System --- Branch: v3-phase-c
