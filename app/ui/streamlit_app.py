"""
AML Pipeline Runner - Streamlit UI

A single-page application with tabs for:
- Run: Start new pipeline runs with profile selection
- Status: Monitor running/completed jobs with auto-refresh
- Dashboard: View visualizations, metrics, and anomaly data
- Graph & Scoring: Pre-computed graph analysis, financial metrics, and pattern rules (NB06-08)
- Report: Access and download generated reports
- Tables: DuckDB-paginated data table explorer (safe for 9.5M-row files)
- Tier Queue: Risk-ranked entity queue with filtering and export
- Cases: Investigation-ready AML cases with typology detection and network graphs
- AML Scores: 5-signal composite scoring with risk bands
- Simulation: Real-time simulation results from NB11 (latency, alerts, scores)

Run with: streamlit run app/ui/streamlit_app.py
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.utils.paths import (
    get_repo_root,
    get_artifacts_root,
    get_run_dir,
    get_data_dir,
    debug_paths,
)
from app.ui.plotly_theme import apply_modern_terminal_plotly, MODERN_TERMINAL_COLORS, BLOOMBERG_COLORS

# Configuration
API_BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
POLL_INTERVAL = 2  # Auto-refresh interval for running jobs
PROJECT_ROOT = get_repo_root()
ARTIFACTS_ROOT = get_artifacts_root()

# Page configuration
st.set_page_config(
    page_title="AML Pipeline Runner",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Modern Terminal Style Theme
def apply_modern_terminal_css():
    """Inject modern terminal-style CSS into Streamlit."""
    st.markdown(
        """
        <style>
        :root {
          --bg: #0B0F14;
          --panel: #111827;
          --panel2: #0F172A;
          --border: #243042;
          --text: #E5E7EB;
          --muted: #9CA3AF;
          --accent: #FBBF24;
          --cyan: #22D3EE;
          --green: #22C55E;
          --red: #EF4444;
          --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
          --ui: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        }

        /* ===== BASE ===== */
        html, body, [class*="stApp"] {
          background: var(--bg) !important;
          color: var(--text) !important;
          font-family: var(--ui) !important;
        }
        /* Fix top clipping - add proper spacing so tabs aren't cut off */
        .block-container {
          padding-top: 2.5rem !important;
          padding-bottom: 1.2rem;
          max-width: 1320px;
        }
        section.main > div {
          padding-top: 1.5rem !important;
        }
        /* Push content below any Streamlit header */
        [data-testid="stAppViewContainer"] > section > div {
          padding-top: 1rem !important;
        }
        header[data-testid="stHeader"] {
          background: var(--bg) !important;
        }

        /* ===== SCROLLBAR ===== */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

        /* ===== SIDEBAR ===== */
        section[data-testid="stSidebar"] {
          background: linear-gradient(180deg, #0A0F16, #0B0F14) !important;
          border-right: 1px solid var(--border) !important;
        }
        section[data-testid="stSidebar"] * {
          color: var(--text) !important;
        }
        section[data-testid="stSidebar"] .stMarkdown p {
          font-size: 0.9rem;
        }

        /* ===== HEADINGS ===== */
        h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 0.5rem 0; color: var(--text); }
        h2 { font-size: 1.1rem; font-weight: 600; margin: 0.8rem 0 0.4rem 0; color: var(--text); }
        h3 { font-size: 0.95rem; font-weight: 500; margin: 0.6rem 0 0.3rem 0; color: var(--muted); }

        /* ===== TABS (FIXED v6) ===== */
        /* Reset ALL clipping in tabs - use !important everywhere */
        .stTabs,
        .stTabs > div,
        [data-testid="stTabs"],
        [data-testid="stTabs"] > div {
          overflow: visible !important;
          clip-path: none !important;
        }
        /* Tab list container - generous sizing */
        .stTabs [data-baseweb="tab-list"],
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 8px 12px !important;
          gap: 8px !important;
          display: flex !important;
          flex-wrap: nowrap !important;
          min-height: 52px !important;
          height: auto !important;
          align-items: center !important;
          overflow: visible !important;
        }
        /* Individual tab buttons - proper sizing for emojis */
        .stTabs button[role="tab"],
        [data-testid="stTabs"] button[role="tab"],
        [data-baseweb="tab"] {
          all: unset !important;
          display: inline-flex !important;
          align-items: center !important;
          justify-content: center !important;
          background: transparent !important;
          color: var(--muted) !important;
          font-family: var(--mono) !important;
          font-size: 0.85rem !important;
          font-weight: 500 !important;
          border: none !important;
          border-radius: 8px !important;
          padding: 10px 18px !important;
          margin: 0 !important;
          min-height: 36px !important;
          height: auto !important;
          line-height: 1.4 !important;
          white-space: nowrap !important;
          cursor: pointer !important;
          box-sizing: border-box !important;
          overflow: visible !important;
        }
        /* Force text/emoji visibility - use all:unset then restyle */
        .stTabs button[role="tab"] p,
        .stTabs button[role="tab"] span,
        .stTabs button[role="tab"] div,
        [data-testid="stTabs"] button[role="tab"] p,
        [data-testid="stTabs"] button[role="tab"] span,
        [data-testid="stTabs"] button[role="tab"] div,
        [data-baseweb="tab"] p,
        [data-baseweb="tab"] span,
        [data-baseweb="tab"] div {
          all: unset !important;
          color: inherit !important;
          font-family: inherit !important;
          font-size: inherit !important;
          font-weight: inherit !important;
          line-height: inherit !important;
          display: inline !important;
          overflow: visible !important;
        }
        /* Hover state */
        .stTabs button[role="tab"]:hover,
        [data-testid="stTabs"] button[role="tab"]:hover,
        [data-baseweb="tab"]:hover {
          background: rgba(251,191,36,0.12) !important;
          color: var(--text) !important;
        }
        /* Active/selected tab */
        .stTabs button[role="tab"][aria-selected="true"],
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"],
        [data-baseweb="tab"][aria-selected="true"] {
          background: rgba(251,191,36,0.2) !important;
          color: var(--accent) !important;
          font-weight: 600 !important;
        }
        /* Hide default tab decorations (underline, highlight bar) */
        .stTabs [data-baseweb="tab-highlight"],
        .stTabs [data-baseweb="tab-border"],
        [data-testid="stTabs"] [data-baseweb="tab-highlight"],
        [data-testid="stTabs"] [data-baseweb="tab-border"] {
          display: none !important;
          height: 0 !important;
          visibility: hidden !important;
        }
        /* Tab panel content */
        .stTabs [data-baseweb="tab-panel"],
        [data-testid="stTabs"] [data-baseweb="tab-panel"] {
          padding-top: 1rem !important;
          overflow: visible !important;
        }

        /* ===== BUTTONS ===== */
        .stButton > button {
          background: linear-gradient(180deg, var(--panel), var(--panel2)) !important;
          color: var(--text) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 0.5rem 1rem !important;
          font-family: var(--mono) !important;
          font-size: 0.85rem !important;
          font-weight: 500 !important;
          transition: all 150ms ease !important;
        }
        .stButton > button:hover {
          border-color: var(--accent) !important;
          box-shadow: 0 0 0 2px rgba(251,191,36,0.15) !important;
        }
        .stButton > button:active {
          transform: scale(0.98);
        }

        /* ===== INPUTS & TEXT FIELDS ===== */
        div[data-baseweb="input"] {
          background: transparent !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea {
          background: var(--panel2) !important;
          color: var(--text) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
          font-family: var(--mono) !important;
          font-size: 0.85rem !important;
          padding: 0.5rem 0.75rem !important;
        }
        div[data-baseweb="input"] input::placeholder,
        div[data-baseweb="textarea"] textarea::placeholder {
          color: var(--muted) !important;
          opacity: 0.6 !important;
        }
        div[data-baseweb="input"] input:focus,
        div[data-baseweb="textarea"] textarea:focus {
          border-color: var(--accent) !important;
          box-shadow: 0 0 0 2px rgba(251,191,36,0.15) !important;
        }
        /* Input labels */
        .stTextInput label, .stTextArea label, .stNumberInput label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
          font-weight: 500 !important;
        }

        /* ===== SELECT/DROPDOWN ===== */
        div[data-testid="stSelectbox"] label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
          font-weight: 500 !important;
        }
        div[data-baseweb="select"] > div {
          background: var(--panel2) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
        }
        div[data-baseweb="select"] > div:hover {
          border-color: var(--accent) !important;
        }
        div[data-baseweb="select"] [data-baseweb="select"] {
          color: var(--text) !important;
        }
        div[data-baseweb="select"] svg {
          fill: var(--muted) !important;
        }
        /* Dropdown menu */
        div[data-baseweb="popover"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
          box-shadow: 0 8px 24px rgba(0,0,0,0.4) !important;
        }
        div[data-baseweb="popover"] ul {
          background: transparent !important;
        }
        div[data-baseweb="popover"] li {
          background: transparent !important;
          color: var(--text) !important;
          font-size: 0.85rem !important;
        }
        div[data-baseweb="popover"] li:hover {
          background: rgba(251,191,36,0.1) !important;
        }
        div[data-baseweb="popover"] li[aria-selected="true"] {
          background: rgba(251,191,36,0.2) !important;
          color: var(--accent) !important;
        }

        /* ===== MULTISELECT ===== */
        div[data-testid="stMultiSelect"] label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 6px !important;
          color: var(--text) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] span {
          color: var(--text) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] svg {
          fill: var(--muted) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"]:hover svg {
          fill: var(--red) !important;
        }

        /* ===== CHECKBOX ===== */
        div[data-testid="stCheckbox"] {
          padding: 0.25rem 0 !important;
        }
        div[data-testid="stCheckbox"] label {
          color: var(--text) !important;
          font-size: 0.85rem !important;
        }
        div[data-testid="stCheckbox"] label span[data-baseweb="checkbox"] {
          background: var(--panel2) !important;
          border: 2px solid var(--border) !important;
          border-radius: 4px !important;
        }
        div[data-testid="stCheckbox"] label span[data-baseweb="checkbox"]:hover {
          border-color: var(--accent) !important;
        }
        div[data-testid="stCheckbox"] input:checked + span[data-baseweb="checkbox"] {
          background: var(--accent) !important;
          border-color: var(--accent) !important;
        }

        /* ===== RADIO BUTTONS ===== */
        div[data-testid="stRadio"] > label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
          font-weight: 500 !important;
          margin-bottom: 0.5rem !important;
        }
        div[data-testid="stRadio"] label[data-baseweb="radio"] {
          color: var(--text) !important;
          font-size: 0.85rem !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
          background: var(--panel2) !important;
          border: 2px solid var(--border) !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] > label:hover > div:first-child {
          border-color: var(--accent) !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] > label[data-baseweb="radio"] input:checked + div {
          background: var(--accent) !important;
          border-color: var(--accent) !important;
        }

        /* ===== TOGGLE/SWITCH ===== */
        div[data-testid="stToggle"] label {
          color: var(--text) !important;
        }
        div[data-testid="stToggle"] div[data-baseweb="toggle"] {
          background: var(--border) !important;
        }
        div[data-testid="stToggle"] div[data-baseweb="toggle"][aria-checked="true"] {
          background: var(--accent) !important;
        }

        /* ===== SLIDER ===== */
        div[data-testid="stSlider"] label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
        }
        div[data-testid="stSlider"] [data-baseweb="slider"] > div:first-child {
          background: var(--border) !important;
        }
        div[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
          background: var(--accent) !important;
          border: 2px solid var(--accent) !important;
        }
        div[data-testid="stSlider"] [data-baseweb="slider"] > div > div {
          background: var(--accent) !important;
        }

        /* ===== DATAFRAMES ===== */
        div[data-testid="stDataFrame"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 4px !important;
        }
        div[data-testid="stDataFrame"] * {
          color: var(--text) !important;
          font-family: var(--mono) !important;
          font-size: 0.8rem !important;
        }

        /* ===== EXPANDERS ===== */
        div[data-testid="stExpander"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
        }
        div[data-testid="stExpander"] summary {
          color: var(--text) !important;
          font-weight: 500 !important;
        }
        div[data-testid="stExpander"] summary:hover {
          color: var(--accent) !important;
        }

        /* ===== METRICS ===== */
        div[data-testid="stMetric"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 0.75rem !important;
        }
        div[data-testid="stMetric"] label {
          color: var(--muted) !important;
          font-family: var(--mono) !important;
          font-size: 0.72rem !important;
          text-transform: uppercase !important;
          letter-spacing: 0.05em !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
          color: var(--text) !important;
          font-family: var(--mono) !important;
          font-size: 1.3rem !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
          font-family: var(--mono) !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg {
          display: none;
        }

        /* ===== ALERTS/INFO BOXES ===== */
        div[data-testid="stAlert"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          color: var(--text) !important;
        }

        /* ===== PROGRESS BAR ===== */
        div[data-testid="stProgress"] > div > div {
          background: var(--accent) !important;
          border-radius: 4px !important;
        }

        /* ===== SPINNER ===== */
        .stSpinner > div {
          border-top-color: var(--accent) !important;
        }

        /* ===== TOOLTIPS ===== */
        div[data-baseweb="tooltip"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 6px !important;
          color: var(--text) !important;
        }

        /* ===== LINKS ===== */
        a { color: var(--cyan) !important; text-decoration: none; }
        a:hover { text-decoration: underline; color: var(--accent) !important; }

        /* ===== DIVIDER ===== */
        hr { border-color: var(--border) !important; }

        /* ===== CODE ===== */
        code {
          background: var(--panel2) !important;
          color: var(--accent) !important;
          border: 1px solid var(--border) !important;
          border-radius: 4px !important;
          padding: 0.15rem 0.35rem !important;
          font-family: var(--mono) !important;
        }
        pre {
          background: var(--panel2) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
        }

        /* ===== CUSTOM CARD CLASSES ===== */
        .mt-card {
          background: linear-gradient(180deg, var(--panel), var(--panel2));
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 1rem;
          box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
        .mt-title {
          font-family: var(--mono);
          font-size: 0.7rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--muted);
          margin-bottom: 0.4rem;
        }
        .mt-kpi {
          font-family: var(--mono);
          font-size: 1.4rem;
          font-weight: 600;
          color: var(--text);
          line-height: 1.2;
        }
        .mt-sub {
          font-family: var(--mono);
          font-size: 0.75rem;
          color: var(--muted);
          margin-top: 0.3rem;
        }

        /* ===== BADGES ===== */
        .mt-badge {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          padding: 0.2rem 0.6rem;
          border-radius: 999px;
          border: 1px solid var(--border);
          font-family: var(--mono);
          font-size: 0.72rem;
          color: var(--muted);
          background: rgba(17,24,39,0.4);
        }
        .mt-badge.ok { border-color: rgba(34,197,94,0.5); color: var(--green); }
        .mt-badge.warn { border-color: rgba(251,191,36,0.5); color: var(--accent); }
        .mt-badge.err { border-color: rgba(239,68,68,0.5); color: var(--red); }

        /* ===== STATUS CLASSES ===== */
        .status-running { color: var(--cyan) !important; font-weight: 600; }
        .status-completed { color: var(--green) !important; font-weight: 600; }
        .status-failed { color: var(--red) !important; font-weight: 600; }
        .status-pending { color: var(--accent) !important; font-weight: 600; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# Apply themes
apply_modern_terminal_css()
apply_modern_terminal_plotly()


# --- Helper Functions ---

def kpi_card(title: str, value: str, sub: str = ""):
    """Render a styled KPI card with modern terminal theme."""
    st.markdown(
        f"""
        <div class="mt-card">
          <div class="mt-title">{title}</div>
          <div class="mt-kpi">{value}</div>
          <div class="mt-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def api_request(method: str, endpoint: str, timeout: int = 30, **kwargs) -> dict:
    """Make an API request and handle errors."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.HTTPError as e:
        return None
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# Role Map constants & helpers
# ---------------------------------------------------------------------------

ROLE_COLORS = {
    "Ingest": "#3B82F6",
    "Features": "#8B5CF6",
    "Embeddings": "#EC4899",
    "GAN": "#EF4444",
    "Scoring": "#F59E0B",
    "Eval": "#10B981",
    "Dashboards": "#06B6D4",
    "Realtime": "#6366F1",
    "Other": "#6B7280",
}

_DEFAULT_ROLE_ORDER = [
    "Ingest", "Features", "Embeddings", "GAN",
    "Scoring", "Eval", "Dashboards", "Realtime", "Other",
]


@st.cache_data(ttl=30)
def _cached_pipeline_detail(pipeline_name: str, dataset_mode: str):
    """Fetch pipeline detail with role data (cached 30s)."""
    return api_request("GET", f"/pipelines/{pipeline_name}?dataset_mode={dataset_mode}")


@st.cache_data(ttl=30)
def _cached_pipeline_manifest(run_id: str):
    """Fetch pipeline manifest for a completed run (cached 30s). Returns None on 404."""
    return api_request("GET", f"/runs/{run_id}/pipeline-manifest")


def _resolve_role_map_data(
    selected_pipeline: str,
    dataset_mode: str,
    active_run_id: str = None,
):
    """
    Resolve role map data: prefer run manifest if available, else pipeline detail.

    Returns (steps, role_order, role_counts, excluded, source_label) or Nones.
    """
    # Try manifest first if a run is selected
    if active_run_id:
        manifest = _cached_pipeline_manifest(active_run_id)
        if manifest and manifest.get("steps"):
            return (
                manifest["steps"],
                manifest.get("role_order", _DEFAULT_ROLE_ORDER),
                manifest.get("role_counts", {}),
                [],  # manifest has no excluded list (it's the truth)
                f"run manifest ({active_run_id[:8]}…)",
            )

    # Fallback: pipeline detail endpoint
    detail = _cached_pipeline_detail(selected_pipeline, dataset_mode)
    if detail and detail.get("steps"):
        return (
            detail["steps"],
            detail.get("role_order", _DEFAULT_ROLE_ORDER),
            detail.get("role_counts", {}),
            detail.get("excluded_notebooks", []),
            "pipeline resolver",
        )

    return None, None, None, None, None


def render_role_ribbon(role_order, role_counts):
    """Render a horizontal ribbon of colored role pills with counts."""
    parts = []
    for role in role_order:
        count = role_counts.get(role, 0)
        color = ROLE_COLORS.get(role, "#6B7280")
        if count > 0:
            parts.append(
                f'<span style="display:inline-block;padding:4px 12px;margin:2px 4px;'
                f'border-radius:14px;background:{color};color:#fff;font-size:0.8em;'
                f'font-weight:600;">{role} ({count})</span>'
            )
        else:
            parts.append(
                f'<span style="display:inline-block;padding:4px 12px;margin:2px 4px;'
                f'border-radius:14px;background:#1F2937;color:#6B7280;font-size:0.8em;'
                f'border:1px solid #374151;">{role}</span>'
            )
    ribbon_html = ' <span style="color:#4B5563;">&#x2192;</span> '.join(parts)
    st.markdown(
        f'<div style="padding:8px 0;overflow-x:auto;white-space:nowrap;">{ribbon_html}</div>',
        unsafe_allow_html=True,
    )


def render_mermaid_flow(steps):
    """Render a Mermaid LR flowchart with role-colored nodes."""
    lines = ["graph LR"]
    for i, s in enumerate(steps):
        node_id = f"S{s['number']}"
        label = s["name"]
        role = s.get("role", "Other")
        if s.get("optional"):
            lines.append(f"    {node_id}[/{label}/]:::{role}")
        else:
            lines.append(f"    {node_id}[{label}]:::{role}")
        if i > 0:
            prev_id = f"S{steps[i - 1]['number']}"
            lines.append(f"    {prev_id} --> {node_id}")
    for role, color in ROLE_COLORS.items():
        lines.append(f"    classDef {role} fill:{color},stroke:#fff,color:#fff;")
    st.markdown(f"```mermaid\n" + "\n".join(lines) + "\n```")


def render_grouped_steps(steps, role_order):
    """Render steps grouped by role in pipeline order."""
    from collections import OrderedDict

    groups = OrderedDict()
    for role in role_order:
        role_steps = [s for s in steps if s.get("role") == role]
        if role_steps:
            groups[role] = role_steps

    for role, group_steps in groups.items():
        color = ROLE_COLORS.get(role, "#6B7280")
        st.markdown(
            f'<div style="margin:6px 0 2px 0;">'
            f'<span style="color:{color};font-weight:700;">{role}</span>'
            f' <span style="color:#6B7280;font-size:0.85em;">'
            f'({len(group_steps)} step{"s" if len(group_steps) != 1 else ""})</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        for s in group_steps:
            opt = " *(optional)*" if s.get("optional") else ""
            st.markdown(f'&nbsp;&nbsp;&nbsp;&nbsp;`{s["number"]:02d}` {s["notebook"]}{opt}')


def render_excluded_notebooks(excluded):
    """Render the list of notebooks excluded from this pipeline variant."""
    if not excluded:
        return
    st.markdown("---")
    st.markdown(
        '<span style="color:#9CA3AF;font-size:0.85em;">'
        "Available but excluded from this pipeline variant:</span>",
        unsafe_allow_html=True,
    )
    for ex in excluded:
        st.markdown(
            f'&nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#6B7280;">'
            f'`{ex["notebook"]}` — {ex.get("role", "")}</span>',
            unsafe_allow_html=True,
        )


def render_step_details_table(steps):
    """Render an expandable step details table."""
    with st.expander("Step details (table)"):
        rows = [
            {
                "Step": s["number"],
                "Role": s.get("role", ""),
                "Notebook": s["notebook"],
                "Name": s["name"],
                "Optional": "Yes" if s.get("optional") else "",
            }
            for s in steps
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------


def format_datetime(dt_str: str) -> str:
    """Format ISO datetime string for display."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if not seconds:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def get_status_emoji(status: str) -> str:
    """Get emoji for status."""
    emojis = {
        "pending": "⏳",
        "running": "🔄",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "🚫",
        "skipped": "⏭️",
    }
    return emojis.get(status.lower(), "❓")


# --- Run Tab ---

def render_run_tab():
    """Render the Run tab with pipeline, dataset, sampling, and profile selection."""
    st.header("Start New Pipeline Run")

    # Fetch available profiles
    profiles_data = api_request("GET", "/runs/profiles")

    if not profiles_data:
        st.error("Cannot connect to API. Please ensure the server is running.")
        return

    profiles = {p["name"]: p for p in profiles_data.get("profiles", [])}

    # ── Pipeline Selection ──────────────────────────────────────────
    st.subheader("Pipeline")

    pipelines_data = api_request("GET", "/pipelines")
    pipeline_options = {}
    if pipelines_data:
        for p in pipelines_data.get("pipelines", []):
            if p["name"] != "e2e-realtime":  # Simulation now runs from its own tab
                pipeline_options[p["name"]] = p
    else:
        # Fallback if API not yet updated
        pipeline_options = {
            "e2e-core": {"name": "e2e-core", "display_name": "E2E PyTorch Core",
                         "description": "GraphSAGE + WGAN-GP ML pipeline (01-05)"},
            "e2e-dashboards": {"name": "e2e-dashboards", "display_name": "E2E + Dashboards",
                               "description": "Core + visualizations & dashboards (06-10)"},
        }

    # Notebook range labels for each pipeline
    _NB_RANGES = {
        "e2e-core": "01-05",
        "e2e-dashboards": "01-10",
        "e2e-realtime": "11-12",
    }

    pip_cols = st.columns(len(pipeline_options))
    selected_pipeline = st.session_state.get("selected_pipeline", "e2e-core")

    for idx, (pname, pinfo) in enumerate(pipeline_options.items()):
        with pip_cols[idx]:
            is_sel = pname == selected_pipeline
            border = "#22D3EE" if is_sel else "#243042"
            bg = "rgba(34,211,238,0.06)" if is_sel else "transparent"
            nb_range = _NB_RANGES.get(pname, "")
            steps_list = pinfo.get("ordered_steps", [])
            step_count = len(steps_list) if steps_list else ""
            badge = f"<span style='background:#22D3EE;color:#000;padding:2px 8px;border-radius:4px;font-size:0.75em;font-weight:600;'>{nb_range}</span>" if nb_range else ""
            count_label = f"<span style='color:#9CA3AF;font-size:0.75em;'>{step_count} notebooks</span>" if step_count else ""

            st.markdown(f"""
            <div style="border: 2px solid {border}; background: {bg}; padding: 14px; border-radius: 8px; min-height: 130px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <h4 style="margin:0; font-size:0.95em;">{pinfo.get('display_name', pname)}</h4>
                    {badge}
                </div>
                <p style="color: #9CA3AF; font-size: 0.8em; margin: 4px 0 8px 0;">
                    {pinfo.get('description', '')}
                </p>
                {count_label}
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Select", key=f"sel_pipe_{pname}",
                        type="primary" if is_sel else "secondary",
                        use_container_width=True):
                st.session_state["selected_pipeline"] = pname
                st.rerun()

    # Profile selection with descriptions
    st.divider()
    st.subheader("Run Profile")

    profile_cols = st.columns(3)

    selected_profile = st.session_state.get("selected_profile", "standard")

    for idx, (name, config) in enumerate(profiles.items()):
        with profile_cols[idx]:
            is_selected = name == selected_profile
            border_color = "#1f77b4" if is_selected else "#ddd"

            # Profile card
            st.markdown(f"""
            <div style="border: 2px solid {border_color}; padding: 15px; border-radius: 10px; margin: 5px 0;">
                <h4 style="margin: 0;">{name.title()}</h4>
                <p style="color: #666; margin: 5px 0;">{config['description']}</p>
                <ul style="margin: 5px 0; padding-left: 20px;">
                    <li>Samples: {config['sample_size']:,}</li>
                    <li>Epochs: {config['epochs']}</li>
                    <li>Threshold: {config['threshold']}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"Select {name.title()}", key=f"select_{name}",
                        type="primary" if is_selected else "secondary"):
                st.session_state["selected_profile"] = name
                st.rerun()

    # Warning for heavy profile
    if selected_profile == "heavy":
        st.warning("**Heavy profile requires 12GB+ VRAM.** Make sure your system has sufficient resources.")

    # ── Dataset Selection ───────────────────────────────────────────
    st.divider()
    st.subheader("Dataset")

    datasets_data = api_request("GET", "/datasets")
    ds_options = {}
    if datasets_data:
        for d in datasets_data.get("datasets", []):
            ds_options[d["name"]] = d
    else:
        ds_options = {
            "demodata": {"name": "demodata", "display_name": "Demo Data",
                         "description": "local demodata/ (~67K txns)",
                         "approx_rows": 67000, "default_sampling": "Full"},
            "simulate": {"name": "simulate", "display_name": "Generate Synthetic",
                         "description": "Fresh synthetic data via 00_simulate_transactions",
                         "approx_rows": None, "default_sampling": "Full"},
            "saml-d": {"name": "saml-d", "display_name": "SAML-D (9.5M rows)",
                       "description": "/mnt/e/xx/demodata/ (realistic AML dataset)",
                       "approx_rows": 9500000, "default_sampling": "Quick"},
        }

    dataset_mode = st.radio(
        "Select dataset",
        options=list(ds_options.keys()),
        format_func=lambda x: f"{ds_options[x].get('display_name', x)}  —  {ds_options[x].get('description', '')}",
        horizontal=True,
        key="dataset_mode_select",
    )

    # ── Sampling Profile ────────────────────────────────────────────
    ds_info = ds_options.get(dataset_mode, {})
    approx = ds_info.get("approx_rows")
    default_sampling = ds_info.get("default_sampling", "Standard")
    sampling_profiles = ds_info.get("sampling_profiles", ["Quick", "Standard", "Heavy", "Full"])

    sampling_col1, sampling_col2 = st.columns([2, 3])
    with sampling_col1:
        sampling_profile = st.selectbox(
            "Sampling profile",
            options=sampling_profiles if isinstance(sampling_profiles, list) else ["Quick", "Standard", "Heavy", "Full"],
            index=0,
            key="sampling_profile_select",
            help="Quick=200K, Standard=1M, Heavy=3M, Full=all rows",
        )
        # Default the selectbox to the dataset's default if not yet interacted
        if "sampling_profile_init" not in st.session_state:
            st.session_state["sampling_profile_init"] = True

    with sampling_col2:
        if approx and approx > 500_000:
            st.info(f"Large dataset (~{approx:,} rows). Default sampling: {default_sampling}")

    # Full confirm checkbox (guardrail)
    confirm_full = False
    if sampling_profile == "Full" and approx and approx > 500_000:
        st.warning(f"Full sampling on ~{approx:,} rows. This may take a long time and use significant resources.")
        confirm_full = st.checkbox(
            "I confirm I want to run Full sampling on this large dataset",
            value=False,
            key="confirm_full_check",
        )

    # /mnt path warning
    ds_root = ds_info.get("dataset_root", "")
    if isinstance(ds_root, str) and ds_root.startswith("/mnt"):
        st.warning("Data is on /mnt/ (Windows mount). IO will be slow. Parquet caching on Linux recommended.")

    custom_data_path = None
    with st.expander("Custom data path (optional)"):
        custom_data_path = st.text_input(
            "Override dataset root path",
            value="",
            placeholder="/path/to/your/demodata/",
            help="Leave empty to use the default path for the selected dataset",
        )
        if custom_data_path:
            st.info(f"Custom path: `{custom_data_path}`")

    # Additional options
    st.divider()
    st.subheader("Additional Options")

    col1, col2, col3 = st.columns(3)

    with col1:
        skip_hp = st.checkbox("Skip HP tuning", value=True,
                             help="Use cached hyperparameters (faster)")
    with col2:
        gen_viz = st.checkbox("Generate visualizations", value=True)
    with col3:
        gen_report = st.checkbox("Generate report", value=True)

    # Custom overrides (expandable)
    with st.expander("Advanced: Custom Parameters"):
        custom_col1, custom_col2, custom_col3 = st.columns(3)
        with custom_col1:
            custom_sample = st.number_input("Sample size override", min_value=1000, max_value=1000000,
                                           value=None, help="Leave empty to use profile default")
        with custom_col2:
            custom_epochs = st.number_input("Epochs override", min_value=1, max_value=100,
                                           value=None, help="Leave empty to use profile default")
        with custom_col3:
            custom_timeout = st.number_input("Notebook timeout (seconds)", min_value=60, max_value=7200,
                                            value=1800, help="Max time per notebook")

    # Start button
    st.divider()

    # Block start if Full not confirmed
    start_disabled = (sampling_profile == "Full" and approx and approx > 500_000 and not confirm_full)

    if st.button("Start Pipeline Run", type="primary", use_container_width=True, disabled=start_disabled):
        with st.spinner("Starting pipeline run..."):
            params = {
                "pipeline_name": selected_pipeline,
                "profile": selected_profile,
                "dataset_mode": dataset_mode,
                "sampling_profile": sampling_profile,
                "confirm_full": confirm_full,
                "skip_hyperparameter_tuning": skip_hp,
                "generate_visualizations": gen_viz,
                "generate_report": gen_report,
                "notebook_timeout": custom_timeout,
            }

            # Add data path override if specified
            if custom_data_path:
                params["dataset_root"] = custom_data_path

            # Add custom overrides if specified
            if custom_sample:
                params["sample_size"] = custom_sample
            if custom_epochs:
                params["epochs"] = custom_epochs

            result = api_request("POST", "/runs/", json=params)

            if result:
                st.success(f"Pipeline run started! Run ID: `{result['run_id']}`")
                st.session_state["active_run_id"] = result["run_id"]
                st.balloons()
                st.info("Switch to the **Status** tab to monitor progress.")
            else:
                st.error("Failed to start pipeline. Check if the API and Celery worker are running.")

    if start_disabled:
        if selected_pipeline == "e2e-realtime" and not source_run_id:
            st.caption("Select a completed source run above to start the simulation pipeline.")
        else:
            st.caption("Enable the confirmation checkbox above to start with Full sampling.")

    # ── Pipeline Map with Role Categories ─────────────────────────────
    with st.expander("Pipeline Map"):
        active_run_id = st.session_state.get("active_run_id")
        steps, role_order, role_counts, excluded, source_label = _resolve_role_map_data(
            selected_pipeline, dataset_mode, active_run_id,
        )

        if steps:
            st.caption(f"Source: **{source_label}**")

            # Role ribbon
            render_role_ribbon(role_order, role_counts)

            # Mermaid flowchart (colored by role)
            render_mermaid_flow(steps)

            # Grouped steps by role
            st.markdown("**Steps by Role**")
            render_grouped_steps(steps, role_order)

            # Excluded notebooks (if e2e variant)
            render_excluded_notebooks(excluded)

            # Step details table
            render_step_details_table(steps)
        else:
            st.info("Pipeline details not available (API may need updating).")

    # Recent runs
    st.divider()
    st.subheader("Recent Runs")

    runs = api_request("GET", "/runs/?limit=5")
    if runs:
        for run in runs:
            status = run["status"]
            emoji = get_status_emoji(status)
            run_params = run.get("params", {})
            run_pipeline = run_params.get("pipeline_name", "e2e-core")
            run_ds = run_params.get("dataset_mode", run_params.get("data_source", "demodata"))

            col1, col2, col3, col4, col5, col6 = st.columns([3, 1.2, 1, 1.5, 1.5, 1])
            with col1:
                st.markdown(f"`{run['id'][:12]}...`")
            with col2:
                st.markdown(f"`{run_pipeline}`")
            with col3:
                st.markdown(f"`{run_ds}`")
            with col4:
                st.markdown(f"{emoji} **{status.upper()}**")
            with col5:
                st.markdown(f"{run['progress_percent']:.0f}%")
            with col6:
                if st.button("View", key=f"view_{run['id']}"):
                    st.session_state["active_run_id"] = run["id"]
                    st.rerun()
    else:
        st.info("No runs yet. Start your first pipeline run above!")


# --- Status Tab ---

def render_status_tab():
    """Render the Status tab with auto-refresh."""
    st.header("Pipeline Status")

    # Run selector
    runs = api_request("GET", "/runs/?limit=20")
    if not runs:
        st.info("No pipeline runs found. Start a new run from the Run tab.")
        return

    run_options = {f"{r['id'][:8]}... ({r['status']}) - {format_datetime(r['created_at'])}": r["id"] for r in runs}

    # Use active run if set — clear stale IDs that no longer exist
    default_idx = 0
    valid_ids = set(run_options.values())
    if "active_run_id" in st.session_state:
        if st.session_state["active_run_id"] not in valid_ids:
            del st.session_state["active_run_id"]
        else:
            for idx, (label, rid) in enumerate(run_options.items()):
                if rid == st.session_state["active_run_id"]:
                    default_idx = idx
                    break

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), index=default_idx)
    selected_run_id = run_options[selected_label]
    st.session_state["active_run_id"] = selected_run_id

    # Fetch detailed status
    status_data = api_request("GET", f"/status/{selected_run_id}")
    if not status_data:
        st.error("Could not fetch run status")
        return

    status = status_data["status"]

    # Status overview cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        emoji = get_status_emoji(status)
        st.metric("Status", f"{emoji} {status.upper()}")
    with col2:
        st.metric("Progress", f"{status_data['progress_percent']:.1f}%")
    with col3:
        st.metric("Step", f"{status_data['current_step']}/{status_data['total_steps']}")
    with col4:
        st.metric("Current", status_data["current_step_name"][:18] + "..." if len(status_data["current_step_name"]) > 18 else status_data["current_step_name"])

    # Progress bar (clamp to valid range 0.0–1.0)
    st.progress(max(0.0, min(1.0, status_data["progress_percent"] / 100)))

    # Auto-refresh indicator for running jobs
    if status == "running":
        st.info(f"🔄 Run in progress. Auto-refreshing every {POLL_INTERVAL} seconds...")

    # Timing info
    st.divider()
    time_col1, time_col2, time_col3 = st.columns(3)
    with time_col1:
        st.markdown(f"**Created:** {format_datetime(status_data['created_at'])}")
    with time_col2:
        st.markdown(f"**Started:** {format_datetime(status_data['started_at'])}")
    with time_col3:
        st.markdown(f"**Completed:** {format_datetime(status_data['completed_at'])}")

    # Step details table
    st.divider()
    st.subheader("Pipeline Steps")

    if status_data.get("steps"):
        steps_df = pd.DataFrame(status_data["steps"])
        steps_df["Status"] = steps_df["status"].apply(lambda x: f"{get_status_emoji(x)} {x}")
        steps_df = steps_df.rename(columns={"step_number": "Step", "step_name": "Name"})

        st.dataframe(
            steps_df[["Step", "Name", "Status"]],
            width="stretch",
            hide_index=True,
        )

    # Error display
    if status_data.get("error_message"):
        st.error(f"**Error:** {status_data['error_message']}")

    # Action buttons
    st.divider()
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if status in ["pending", "running"]:
            if st.button("🚫 Cancel Run", type="secondary"):
                result = api_request("POST", f"/runs/{selected_run_id}/cancel")
                if result:
                    st.success("Run cancelled")
                    st.rerun()

    with btn_col2:
        if st.button("🔄 Refresh Now"):
            st.rerun()

    with btn_col3:
        if status == "completed":
            if st.button("📊 View Dashboard"):
                st.session_state["dashboard_run_id"] = selected_run_id

    # Auto-refresh for running jobs
    if status == "running":
        time.sleep(POLL_INTERVAL)
        st.rerun()


# --- Dashboard Tab ---

def render_dashboard_tab():
    """Render the Dashboard tab with visualizations and data tables."""
    st.header("Analytics Dashboard")

    # Run selector - show all runs, not just completed
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found.")
        return

    # Filter to show completed runs first
    completed_runs = [r for r in runs if r["status"] == "completed"]
    other_runs = [r for r in runs if r["status"] != "completed"]
    sorted_runs = completed_runs + other_runs

    run_options = {
        f"{r['id'][:8]}... ({r['status']}) - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in sorted_runs
    }

    # Use dashboard_run_id if set
    default_idx = 0
    if "dashboard_run_id" in st.session_state:
        for idx, (label, rid) in enumerate(run_options.items()):
            if rid == st.session_state["dashboard_run_id"]:
                default_idx = idx
                break

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), index=default_idx,
                                  key="dashboard_run_select")
    selected_run_id = run_options[selected_label]

    # Fetch run info, summary and metrics
    run_info = api_request("GET", f"/runs/{selected_run_id}")
    summary = api_request("GET", f"/artifacts/{selected_run_id}/summary")
    metrics = api_request("GET", f"/runs/{selected_run_id}/metrics")

    if not summary:
        st.warning("Could not fetch run summary")
        return

    # KPI Cards at top (status, progress, num_flagged, threshold) - Bloomberg style
    st.subheader("Run Overview")
    kpi_cols = st.columns(4)

    with kpi_cols[0]:
        status = run_info.get("status", "unknown") if run_info else "unknown"
        emoji = get_status_emoji(status)
        status_color = "#22D3EE" if status == "running" else "#00C853" if status == "completed" else "#FF5252" if status == "failed" else "#FFB000"
        run_params = run_info.get("params", {}) if run_info else {}
        ds_label = run_params.get("data_source", "demo-data").upper()
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div style="font-size: 2rem;">{emoji}</div>
            <div class="mt-kpi" style="color: {status_color};">{status.upper()}</div>
            <div class="mt-title">Status</div>
            <div class="mt-sub">Dataset: {ds_label}</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_cols[1]:
        progress = run_info.get("progress_percent", 0) if run_info else 0
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div class="mt-kpi" style="color: #00C853;">{progress:.0f}%</div>
            <div class="mt-title">Progress</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_cols[2]:
        num_flagged = "N/A"
        if metrics and metrics.get("anomalies", {}).get("num_flagged") is not None:
            num_flagged = f"{metrics['anomalies']['num_flagged']:,}"
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div class="mt-kpi" style="color: #FF5252;">{num_flagged}</div>
            <div class="mt-title">Flagged Anomalies</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_cols[3]:
        threshold = "N/A"
        if metrics and metrics.get("anomalies", {}).get("threshold") is not None:
            threshold = f"{metrics['anomalies']['threshold']:.4f}"
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div class="mt-kpi" style="color: #FFB000;">{threshold}</div>
            <div class="mt-title">Threshold</div>
        </div>
        """, unsafe_allow_html=True)

    # Key metrics row
    st.divider()
    st.subheader("Key Metrics")
    metric_cols = st.columns(5)

    results = summary.get("results", {})
    with metric_cols[0]:
        st.metric("Total Nodes", f"{results.get('total_nodes') or 'N/A':,}" if results.get('total_nodes') else "N/A")
    with metric_cols[1]:
        st.metric("Transactions", f"{results.get('total_transactions') or 'N/A':,}" if results.get('total_transactions') else "N/A")
    with metric_cols[2]:
        st.metric("Anomalies", f"{results.get('anomalies_detected') or 'N/A':,}" if results.get('anomalies_detected') else "N/A")
    with metric_cols[3]:
        if metrics and metrics.get("anomalies", {}).get("anomaly_rate"):
            st.metric("Anomaly Rate", f"{metrics['anomalies']['anomaly_rate']}%")
        else:
            st.metric("Anomaly Rate", "N/A")
    with metric_cols[4]:
        artifacts = summary.get("artifacts", {})
        st.metric("Artifacts", artifacts.get("total_files", 0))

    # Detailed metrics from metrics.json
    if metrics and not metrics.get("status") == "metrics_not_available":
        st.divider()
        st.subheader("Detailed Metrics")

        detail_tabs = st.tabs(["Dataset", "Training", "Anomalies", "Embedding"])

        with detail_tabs[0]:
            dataset = metrics.get("dataset", {})
            if dataset:
                ds_col1, ds_col2, ds_col3 = st.columns(3)
                with ds_col1:
                    st.metric("Transactions", f"{dataset.get('num_transactions') or 'N/A':,}" if dataset.get('num_transactions') else "N/A")
                with ds_col2:
                    st.metric("Accounts", f"{dataset.get('num_accounts') or 'N/A':,}" if dataset.get('num_accounts') else "N/A")
                with ds_col3:
                    if dataset.get("data_files"):
                        st.metric("Data Files", len(dataset["data_files"]))

        with detail_tabs[1]:
            training = metrics.get("training", {})
            if training:
                tr_col1, tr_col2, tr_col3, tr_col4 = st.columns(4)
                with tr_col1:
                    st.metric("Epochs", training.get("epochs") or "N/A")
                with tr_col2:
                    if training.get("final_loss"):
                        st.metric("Final Loss", f"{training['final_loss']:.6f}")
                    else:
                        st.metric("Final Loss", "N/A")
                with tr_col3:
                    st.metric("Duration", format_duration(training.get("duration_seconds")))
                with tr_col4:
                    if training.get("threshold"):
                        st.metric("Threshold", f"{training['threshold']:.4f}")
                    else:
                        st.metric("Threshold", "N/A")

                # Show model path and files
                if training.get("model_path"):
                    st.markdown(f"**Model Path:** `{training['model_path']}`")
                if training.get("model_files"):
                    st.markdown(f"**Model Files:** {', '.join(training['model_files'])}")

        with detail_tabs[2]:
            anomalies = metrics.get("anomalies", {})
            if anomalies:
                an_col1, an_col2, an_col3, an_col4 = st.columns(4)
                with an_col1:
                    st.metric("Flagged", f"{anomalies.get('num_flagged') or 'N/A':,}" if anomalies.get('num_flagged') else "N/A")
                with an_col2:
                    if anomalies.get("threshold"):
                        st.metric("Threshold", f"{anomalies['threshold']:.6f}")
                    else:
                        st.metric("Threshold", "N/A")
                with an_col3:
                    st.metric("Anomaly Rate (Table)", f"{anomalies.get('anomaly_rate') or 'N/A'}%")
                with an_col4:
                    if anomalies.get("anomaly_rate_nodes_pct") is not None:
                        st.metric("Rate (All Nodes)", f"{anomalies['anomaly_rate_nodes_pct']:.2f}%")
                    else:
                        st.metric("Rate (All Nodes)", "N/A")

        with detail_tabs[3]:
            embedding = metrics.get("embedding", {})
            if embedding:
                emb_col1, emb_col2, emb_col3 = st.columns(3)
                with emb_col1:
                    st.metric("Dimensions", embedding.get("dim") or "N/A")
                with emb_col2:
                    st.metric("Nodes", f"{embedding.get('num_nodes') or 'N/A':,}" if embedding.get('num_nodes') else "N/A")
                with emb_col3:
                    st.metric("Edges", f"{embedding.get('num_edges') or 'N/A':,}" if embedding.get('num_edges') else "N/A")

    # Debug paths expander (for development/troubleshooting)
    with st.expander("🔧 Debug: Artifact Paths", expanded=False):
        paths_data = api_request("GET", f"/runs/{selected_run_id}/paths")
        if paths_data:
            st.markdown("**Explicit artifact paths from metrics.json:**")

            path_cols = st.columns(2)
            with path_cols[0]:
                st.markdown("**Anomalies Table:**")
                st.code(paths_data.get("anomalies_table_path") or "Not found")

                st.markdown("**Model Path:**")
                st.code(paths_data.get("model_path") or "Not found")

                st.markdown("**Model Files:**")
                model_files = paths_data.get("model_files", [])
                if model_files:
                    for f in model_files:
                        st.text(f"  • {f}")
                else:
                    st.text("  No model files found")

            with path_cols[1]:
                st.markdown("**Report Path:**")
                st.code(paths_data.get("report_path") or "Not found")

                st.markdown("**Bundle Path:**")
                st.code(paths_data.get("bundle_path") or "Not found")

                st.markdown("**Key Plots:**")
                key_plots = paths_data.get("key_plots_paths", [])
                if key_plots:
                    for p in key_plots[:6]:  # Show first 6
                        st.text(f"  • {p}")
                    if len(key_plots) > 6:
                        st.text(f"  ... and {len(key_plots) - 6} more")
                else:
                    st.text("  No key plots found")

            st.markdown("**Base Artifacts Directory:**")
            st.code(paths_data.get("artifacts_base") or "N/A")
        else:
            st.warning("Could not fetch paths data")

    # Visualizations
    st.divider()
    st.subheader("Visualizations")

    # Get the styled plots toggle state
    show_styled = st.session_state.get("show_styled_plots", True)

    # Fetch all plots first to check if styled versions exist
    plots = api_request("GET", f"/artifacts/{selected_run_id}/plots")
    original_plots = plots.get("plots", []) if plots else []

    # Check for styled plots in the artifact index
    artifact_index = api_request("GET", f"/artifacts/{selected_run_id}")
    styled_plots = []
    has_styled = False

    if artifact_index and artifact_index.get("artifacts"):
        styled_plots = [a for a in artifact_index["artifacts"] if "plots/styled" in a.get("path", "")]
        has_styled = len(styled_plots) > 0

    # Determine which plots to show
    if show_styled and has_styled:
        plot_list = styled_plots
        plot_type_label = "Bloomberg-styled"
    else:
        plot_list = original_plots
        plot_type_label = "Original"

    if plot_list:
        # Show info with plot type indicator
        info_msg = f"Found {len(plot_list)} {plot_type_label.lower()} visualization(s)"
        if has_styled:
            info_msg += f" | {'Styled' if show_styled else 'Original'} view"
        st.info(info_msg)

        # Create a grid of plots
        cols_per_row = 2
        for i in range(0, len(plot_list), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                if i + j < len(plot_list):
                    plot = plot_list[i + j]
                    with col:
                        st.markdown(f"**{plot['name']}**")
                        img_url = f"{API_BASE_URL}/artifacts/{selected_run_id}/file/{plot['path']}"
                        try:
                            response = requests.get(img_url, timeout=10)
                            if response.status_code == 200:
                                st.image(response.content, width="stretch")
                        except:
                            st.warning(f"Could not load: {plot['name']}")
    else:
        st.info("No visualizations available for this run.")

    # Anomalies data table
    st.divider()
    st.subheader("Anomaly Data")

    # First try to get alert_nodes_td.csv via the table endpoint (preferred)
    table_data = api_request("GET", f"/artifacts/{selected_run_id}/table/alert_nodes_td.csv?limit=500")

    if table_data and table_data.get("data"):
        st.info(f"📋 **Primary source: alert_nodes_td.csv** | Showing {len(table_data['data'])} of {table_data['total_rows']} rows")

        df = pd.DataFrame(table_data["data"])
        original_df = df.copy()

        # Quick filters in expandable section
        with st.expander("🔍 Quick Filters", expanded=True):
            filter_cols = st.columns(4)

            # is_sar filter (if column exists)
            with filter_cols[0]:
                if "is_sar" in df.columns:
                    sar_options = ["All", "SAR Only (1)", "Non-SAR Only (0)"]
                    sar_filter = st.selectbox("SAR Status", sar_options, key="sar_filter")
                    if sar_filter == "SAR Only (1)":
                        df = df[df["is_sar"] == 1]
                    elif sar_filter == "Non-SAR Only (0)":
                        df = df[df["is_sar"] == 0]

            # Score filter (if column exists)
            with filter_cols[1]:
                score_col = None
                for col in ["score", "anomaly_score", "risk_score"]:
                    if col in df.columns:
                        score_col = col
                        break
                if score_col:
                    min_score = st.slider("Min Score", 0.0, 1.0, 0.0, key="min_score_filter")
                    df = df[df[score_col] >= min_score]

            # ID search (if column exists)
            with filter_cols[2]:
                if "id" in df.columns:
                    id_search = st.text_input("Search ID", key="id_search")
                    if id_search:
                        df = df[df["id"].astype(str).str.contains(id_search, case=False, na=False)]

            # Column selector
            with filter_cols[3]:
                available_cols = df.columns.tolist()
                default_cols = [c for c in ["id", "type", "is_sar", "score", "amount", "degree", "risk"] if c in available_cols]
                if not default_cols:
                    default_cols = available_cols[:5]

        # Show filter stats
        if len(df) != len(original_df):
            st.caption(f"Filtered: {len(df)} rows (from {len(original_df)} total)")

        # Column selector outside expander
        show_cols = st.multiselect("Display Columns", available_cols,
                                  default=default_cols if default_cols else available_cols[:5],
                                  key="show_cols_select")

        # Display table
        if show_cols and len(df) > 0:
            st.dataframe(df[show_cols], width="stretch", hide_index=True)

            # Download buttons
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                csv = df[show_cols].to_csv(index=False)
                st.download_button(
                    label="📥 Download Filtered CSV",
                    data=csv,
                    file_name=f"alert_nodes_{selected_run_id[:8]}.csv",
                    mime="text/csv",
                )
            with btn_col2:
                full_csv = original_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Full Table",
                    data=full_csv,
                    file_name=f"alert_nodes_full_{selected_run_id[:8]}.csv",
                    mime="text/csv",
                )
        elif len(df) == 0:
            st.warning("No records match the current filters.")
    else:
        # Fallback to the anomalies endpoint
        anomalies_data = api_request("GET", f"/artifacts/{selected_run_id}/anomalies?limit=100")

        if anomalies_data and anomalies_data.get("anomalies"):
            st.info(f"Showing top {anomalies_data['returned_count']} anomalies out of {anomalies_data['total_records']} total records")

            # Convert to dataframe
            df = pd.DataFrame(anomalies_data["anomalies"])

            # Add filter controls
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                if anomalies_data.get("score_column") in df.columns:
                    min_score = st.slider("Minimum Score", 0.0, 1.0, 0.0)
                    df = df[df[anomalies_data["score_column"]] >= min_score]
            with filter_col2:
                show_cols = st.multiselect("Show Columns", df.columns.tolist(),
                                          default=df.columns.tolist()[:6])

            # Display table
            if show_cols:
                st.dataframe(df[show_cols], width="stretch", hide_index=True)

                # Download button
                csv = df[show_cols].to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"anomalies_{selected_run_id[:8]}.csv",
                    mime="text/csv",
                )
        else:
            st.info("No anomaly data available for this run.")


# --- Report Tab ---

def render_report_tab():
    """Render the Report tab."""
    st.header("Run Reports")

    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]

    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view reports.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r['completed_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), key="report_run_select")
    selected_run_id = run_options[selected_label]

    # Get report metadata
    report_meta = api_request("GET", f"/artifacts/{selected_run_id}/report?format=json")

    if report_meta and report_meta.get("status") != "report_not_generated":
        st.success("✅ Report available!")

        # Metadata display
        meta_col1, meta_col2 = st.columns(2)
        with meta_col1:
            st.markdown(f"**Run ID:** `{report_meta.get('run_id', 'N/A')}`")
            st.markdown(f"**Generated:** {report_meta.get('generated_at', 'N/A')}")
        with meta_col2:
            st.markdown(f"**Status:** {report_meta.get('status', 'N/A')}")
            metrics = report_meta.get("metrics", {})
            if metrics.get("anomalies_detected"):
                st.markdown(f"**Anomalies:** {metrics['anomalies_detected']:,}")

        # Action buttons
        st.divider()
        report_url = f"{API_BASE_URL}/artifacts/{selected_run_id}/report?format=html"
        bundle_url = f"{API_BASE_URL}/artifacts/{selected_run_id}/bundle"

        btn_col1, btn_col2, btn_col3 = st.columns(3)
        with btn_col1:
            st.link_button("🔗 Open in Browser", report_url, width="stretch")
        with btn_col2:
            try:
                response = requests.get(report_url, timeout=15)
                if response.status_code == 200:
                    st.download_button(
                        label="📥 Download HTML",
                        data=response.content,
                        file_name=f"aml_report_{selected_run_id[:8]}.html",
                        mime="text/html",
                        width="stretch",
                    )
            except:
                st.warning("Could not fetch report")
        with btn_col3:
            try:
                bundle_response = requests.get(bundle_url, timeout=30)
                if bundle_response.status_code == 200:
                    st.download_button(
                        label="📦 Download Run Bundle",
                        data=bundle_response.content,
                        file_name=f"aml_run_{selected_run_id[:8]}_bundle.zip",
                        mime="application/zip",
                        width="stretch",
                        help="ZIP containing metrics, report, alert data, and key plots"
                    )
                else:
                    st.button("📦 Bundle N/A", disabled=True, width="stretch",
                             help="Run bundle not available for this run")
            except Exception as e:
                st.button("📦 Bundle N/A", disabled=True, width="stretch")

        # Inline preview
        st.divider()
        st.subheader("Report Preview")

        try:
            response = requests.get(report_url, timeout=15)
            if response.status_code == 200:
                st.components.v1.html(response.text, height=800, scrolling=True)
        except Exception as e:
            st.warning(f"Could not load report preview: {e}")

    else:
        st.warning("Report not generated for this run.")
        st.markdown("""
        Reports are generated when a pipeline run completes with the "Generate report" option enabled.

        **Report contents:**
        - Run summary and metrics
        - Dataset overview
        - Anomaly detection results
        - Visualizations
        - Detection rules
        """)


# --- Tables (DuckDB Paginated Explorer) Tab ---

def render_tables_tab():
    """Render the Tables explorer tab with server-side DuckDB pagination."""
    st.header("Data Tables")

    runs = api_request("GET", "/runs/?limit=20")
    if not runs:
        st.info("No pipeline runs found. Start a run to explore data tables.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs. Tables are available after a run completes.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at', r.get('created_at', '')))}": r["id"]
        for r in completed_runs
    }
    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), key="tables_run_select")
    selected_run_id = run_options[selected_label]

    # Fetch available tables
    tables_resp = api_request("GET", f"/artifacts/{selected_run_id}/tables")
    if not tables_resp or not tables_resp.get("tables"):
        st.info("No data tables found for this run.")
        return

    tables_list = tables_resp["tables"]
    table_options = {
        f"{t['name']}  ({t['format']}, {t['size_bytes'] / 1024:.0f} KB)": t["stem"]
        for t in tables_list
    }

    selected_table_label = st.selectbox("Select Table", options=list(table_options.keys()), key="tables_table_select")
    table_stem = table_options[selected_table_label]

    # Pagination controls
    st.divider()
    ctrl_cols = st.columns([1, 1, 2])
    with ctrl_cols[0]:
        page_size = st.selectbox("Rows per page", [50, 100, 200, 500, 1000], index=1, key="tables_page_size")
    with ctrl_cols[1]:
        page_num = st.number_input("Page", min_value=1, value=1, step=1, key="tables_page_num")

    offset = (page_num - 1) * page_size

    # Fetch paginated data via DuckDB endpoint
    data = api_request(
        "GET",
        f"/runs/{selected_run_id}/table/{table_stem}?limit={page_size}&offset={offset}",
    )

    if not data:
        st.error(f"Could not load table '{table_stem}'. The API may be unreachable.")
        return

    total = data.get("total", 0)
    columns = data.get("columns", [])
    rows = data.get("rows", [])
    total_pages = max(1, (total + page_size - 1) // page_size)

    # Summary bar
    with ctrl_cols[2]:
        st.markdown(f"**{total:,}** rows total &middot; page {page_num} / {total_pages}")

    if not rows:
        st.info("No data rows returned.")
        return

    df = pd.DataFrame(rows, columns=columns if columns else None)

    # Column info
    with st.expander("Column Info", expanded=False):
        col_info = pd.DataFrame({
            "Column": df.columns,
            "Type": [str(df[c].dtype) for c in df.columns],
            "Non-Null": [df[c].notna().sum() for c in df.columns],
            "Sample": [str(df[c].iloc[0])[:60] if len(df) > 0 else "" for c in df.columns],
        })
        st.dataframe(col_info, use_container_width=True, hide_index=True)

    # Main data table
    st.dataframe(df, use_container_width=True, hide_index=True, height=500)

    # Download current page as CSV
    csv_data = df.to_csv(index=False)
    st.download_button(
        label=f"Download page {page_num} as CSV",
        data=csv_data,
        file_name=f"{table_stem}_page{page_num}.csv",
        mime="text/csv",
    )


# --- Graph & Scoring Tab ---

def render_graph_scoring_tab():
    """Render the Graph & Scoring tab with pre-computed NB06-08 outputs."""
    st.header("Graph & Scoring")

    # Run selector (same pattern as other tabs)
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view graph & scoring data.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox(
        "Select Run", options=list(run_options.keys()), key="graph_scoring_run_select"
    )
    selected_run_id = run_options[selected_label]

    # Resolve artifact path from the run record (handles SAML-D custom paths)
    run_info = api_request("GET", f"/runs/{selected_run_id}")
    if run_info and run_info.get("artifact_path"):
        artifact_path = Path(run_info["artifact_path"])
        if not artifact_path.is_absolute():
            artifact_path = (get_repo_root() / artifact_path).resolve()
        run_dir = artifact_path
    else:
        run_dir = get_run_dir(selected_run_id)
    results_dir = run_dir / "results"

    # Sub-tabs
    tab_graph, tab_financial, tab_patterns = st.tabs([
        "Graph Analysis", "Financial Analysis", "Pattern Analysis",
    ])

    # ══════════════════════════════════════════════════════════════════════
    #  Tab 1: Graph Analysis (NB06 output)
    # ══════════════════════════════════════════════════════════════════════
    with tab_graph:
        scored_path = results_dir / "node_embeddings_scored.parquet"
        if not scored_path.exists():
            st.warning(
                "node_embeddings_scored.parquet not found in `results/`. "
                "Run notebook 06 (visualize_results) to generate this file."
            )
        else:
            try:
                scored_df = pd.read_parquet(scored_path)
            except Exception as e:
                st.error(f"Failed to load node_embeddings_scored.parquet: {e}")
                return

            total_nodes = len(scored_df)
            anomaly_count = int(scored_df["is_anomaly"].sum())
            detection_rate = 100 * anomaly_count / max(total_nodes, 1)

            # Determine threshold from the data (min anomaly_score among anomalies)
            anomaly_scores = scored_df[scored_df["is_anomaly"] == True]["anomaly_score"]
            threshold_val = float(anomaly_scores.min()) if len(anomaly_scores) > 0 else 0.0

            # KPI row
            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Total Nodes", f"{total_nodes:,}")
            kc2.metric("Anomalies Detected", f"{anomaly_count:,}")
            kc3.metric("Threshold", f"{threshold_val:.6f}")
            kc4.metric("Detection Rate", f"{detection_rate:.1f}%")

            st.markdown("---")

            # Anomaly score distribution histogram (SAR vs non-SAR)
            st.subheader("Anomaly Score Distribution")
            if "is_sar" in scored_df.columns:
                scored_df["sar_label"] = scored_df["is_sar"].map({1: "SAR", 0: "Non-SAR"})
                fig_hist = px.histogram(
                    scored_df,
                    x="anomaly_score",
                    color="sar_label",
                    nbins=80,
                    color_discrete_map={
                        "SAR": MODERN_TERMINAL_COLORS["red"],
                        "Non-SAR": MODERN_TERMINAL_COLORS["green"],
                    },
                    labels={"anomaly_score": "Anomaly Score", "sar_label": "SAR Status"},
                    barmode="overlay",
                )
                fig_hist.update_traces(opacity=0.7)
            else:
                fig_hist = px.histogram(
                    scored_df,
                    x="anomaly_score",
                    nbins=80,
                    color_discrete_sequence=[MODERN_TERMINAL_COLORS["cyan"]],
                    labels={"anomaly_score": "Anomaly Score"},
                )

            fig_hist.add_vline(
                x=threshold_val, line_dash="dash",
                line_color=MODERN_TERMINAL_COLORS["red"],
                annotation_text=f"Threshold {threshold_val:.4f}",
            )
            fig_hist.update_layout(
                yaxis_type="log",
                yaxis_title="Count (log)",
                height=400,
                margin=dict(t=40, b=40),
                legend=dict(orientation="h", y=1.08),
            )
            apply_modern_terminal_plotly()
            st.plotly_chart(fig_hist, use_container_width=True)

            # Top 20 anomalous nodes table
            st.subheader("Top 20 Anomalous Nodes")
            display_cols = ["id", "anomaly_score", "is_anomaly"]
            if "is_sar" in scored_df.columns:
                display_cols.append("is_sar")
            if "risk_score" in scored_df.columns:
                display_cols.append("risk_score")

            top20 = scored_df.nlargest(20, "anomaly_score")[display_cols].copy()
            top20["anomaly_score"] = top20["anomaly_score"].round(4)
            if "risk_score" in top20.columns:
                top20["risk_score"] = top20["risk_score"].round(4)
            st.dataframe(top20, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    #  Tab 2: Financial Analysis (NB07 output)
    # ══════════════════════════════════════════════════════════════════════
    with tab_financial:
        metrics_path = results_dir / "financial_metrics.json"
        money_flow_path = results_dir / "node_money_flow.parquet"

        if not metrics_path.exists():
            st.warning(
                "financial_metrics.json not found in `results/`. "
                "Run notebook 07 (analytical_dashboard) to generate this file."
            )
        else:
            try:
                with open(metrics_path) as f:
                    fin_metrics = json.load(f)
            except Exception as e:
                st.error(f"Failed to load financial_metrics.json: {e}")
                return

            # Financial KPIs
            recovered = float(fin_metrics.get("recovered_amount", 0))
            op_cost = float(fin_metrics.get("total_operational_cost", 0))
            net_savings = float(fin_metrics.get("net_savings", 0))
            tp = int(fin_metrics.get("true_positives", 0))
            fp = int(fin_metrics.get("false_positives", 0))
            fn = int(fin_metrics.get("false_negatives", 0))
            tn = int(fin_metrics.get("true_negatives", 0))

            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Recovered Amount", f"${recovered:,.0f}")
            kc2.metric("Operational Cost", f"${op_cost:,.0f}")
            kc3.metric("Net Savings", f"${net_savings:,.0f}")
            kc4.metric("TP / FP / FN / TN", f"{tp} / {fp} / {fn} / {tn}")

            st.markdown("---")

            # Confusion matrix
            col_cm, col_wf = st.columns(2)

            with col_cm:
                st.subheader("Detection Matrix")
                cm = np.array([[tn, fp], [fn, tp]])
                fig_cm = px.imshow(
                    cm, text_auto=True,
                    x=["Predicted Normal", "Predicted Anomaly"],
                    y=["Actual Normal", "Actual AML"],
                    color_continuous_scale="RdYlGn_r",
                    labels=dict(color="Count"),
                )
                fig_cm.update_layout(height=350, margin=dict(t=40, b=30))
                apply_modern_terminal_plotly()
                st.plotly_chart(fig_cm, use_container_width=True)

            with col_wf:
                st.subheader("Loss vs Savings Waterfall")
                suspicious_val = float(fin_metrics.get("suspicious_txn_value", 0))
                loss_detected = float(fin_metrics.get("potential_loss_detected", 0))
                inv_cost = float(fin_metrics.get("investigation_cost", 0))
                fp_cost = float(fin_metrics.get("false_positive_cost", 0))

                fig_wf = go.Figure(go.Waterfall(
                    x=["Suspicious<br>Value", "Loss<br>Avoided", "Recovered",
                       "Investigation<br>Cost", "FP Cost", "Net Savings"],
                    y=[suspicious_val, -loss_detected, recovered,
                       -inv_cost, -fp_cost, net_savings],
                    measure=["absolute", "relative", "relative",
                             "relative", "relative", "total"],
                    connector_line_color="rgba(200,200,200,0.3)",
                    increasing_marker_color=MODERN_TERMINAL_COLORS["green"],
                    decreasing_marker_color=MODERN_TERMINAL_COLORS["red"],
                    totals_marker_color=BLOOMBERG_COLORS["accent"],
                    texttemplate="$%{y:,.0f}",
                    textposition="outside",
                ))
                fig_wf.update_layout(
                    yaxis_title="Amount ($)",
                    height=350,
                    margin=dict(t=40, b=30),
                )
                apply_modern_terminal_plotly()
                st.plotly_chart(fig_wf, use_container_width=True)

            # Money flow comparison: anomalous vs normal
            if money_flow_path.exists():
                try:
                    money_df = pd.read_parquet(money_flow_path)
                except Exception as e:
                    st.warning(f"Could not load node_money_flow.parquet: {e}")
                    money_df = None

                if money_df is not None and "is_anomaly" in money_df.columns:
                    st.markdown("---")
                    col_flow, col_risk_vol = st.columns(2)

                    with col_flow:
                        st.subheader("Money Flow: Anomalous vs Normal")
                        anom = money_df[money_df["is_anomaly"] == True]
                        norm = money_df[money_df["is_anomaly"] == False]

                        flow_metrics = ["total_volume", "outgoing_amt", "incoming_amt"]
                        flow_labels = ["Total Volume", "Outgoing", "Incoming"]
                        anom_means = [anom[m].mean() for m in flow_metrics]
                        norm_means = [norm[m].mean() for m in flow_metrics]

                        fig_flow = go.Figure()
                        fig_flow.add_trace(go.Bar(
                            x=flow_labels, y=anom_means, name="Anomalous",
                            marker_color=MODERN_TERMINAL_COLORS["red"],
                        ))
                        fig_flow.add_trace(go.Bar(
                            x=flow_labels, y=norm_means, name="Normal",
                            marker_color=MODERN_TERMINAL_COLORS["green"],
                        ))
                        fig_flow.update_layout(
                            barmode="group",
                            yaxis_title="Avg Amount ($)",
                            height=380,
                            margin=dict(t=40, b=30),
                            legend=dict(orientation="h", y=1.08),
                        )
                        apply_modern_terminal_plotly()
                        st.plotly_chart(fig_flow, use_container_width=True)

                    with col_risk_vol:
                        st.subheader("Transaction Volume by Risk Category")
                        if "risk_score" in money_df.columns:
                            risk_labels = ["Low", "Medium", "High", "Critical"]
                            risk_colors = [
                                MODERN_TERMINAL_COLORS["green"],
                                BLOOMBERG_COLORS["accent"],
                                MODERN_TERMINAL_COLORS["amber"],
                                MODERN_TERMINAL_COLORS["red"],
                            ]
                            money_df["risk_category"] = pd.cut(
                                money_df["risk_score"],
                                bins=[0, 0.25, 0.5, 0.75, 1.0],
                                labels=risk_labels,
                                include_lowest=True,
                            )
                            risk_vol = money_df.groupby("risk_category", observed=False)["total_volume"].sum()
                            risk_vol = risk_vol.reindex(risk_labels).fillna(0)

                            fig_risk = go.Figure(go.Bar(
                                x=risk_labels,
                                y=risk_vol.values,
                                marker_color=risk_colors,
                                text=[f"${v:,.0f}" for v in risk_vol.values],
                                textposition="outside",
                            ))
                            fig_risk.update_layout(
                                yaxis_title="Total Volume ($)",
                                height=380,
                                margin=dict(t=40, b=30),
                            )
                            apply_modern_terminal_plotly()
                            st.plotly_chart(fig_risk, use_container_width=True)
                        else:
                            st.info("risk_score column not found in money flow data.")
            else:
                st.info(
                    "node_money_flow.parquet not found. "
                    "Money flow charts require notebook 07 output."
                )

    # ══════════════════════════════════════════════════════════════════════
    #  Tab 3: Pattern Analysis (NB08 output)
    # ══════════════════════════════════════════════════════════════════════
    with tab_patterns:
        rules_path = results_dir / "aml_rules.json"
        if not rules_path.exists():
            st.warning(
                "aml_rules.json not found in `results/`. "
                "Run notebook 08 (pattern_analysis) to generate this file."
            )
        else:
            try:
                with open(rules_path) as f:
                    rules_data = json.load(f)
            except Exception as e:
                st.error(f"Failed to load aml_rules.json: {e}")
                return

            # Header KPIs from rules metadata
            total_analyzed = rules_data.get("total_nodes_analyzed", 0)
            anomalies_found = rules_data.get("anomalies_detected", 0)
            rule_threshold = rules_data.get("anomaly_threshold", 0)
            rules_list = rules_data.get("rules", [])

            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("Nodes Analyzed", f"{total_analyzed:,}")
            kc2.metric("Anomalies Detected", f"{anomalies_found:,}")
            kc3.metric("Rules Extracted", f"{len(rules_list):,}")

            st.markdown("---")

            if not rules_list:
                st.info("No rules were extracted in the pattern analysis.")
            else:
                # Build rules DataFrame
                rules_rows = []
                for r in rules_list:
                    rate = r.get("suspicious_rate", 0)
                    # Handle NaN rates (e.g. velocity rule with nan)
                    try:
                        rate = float(rate)
                        if np.isnan(rate):
                            rate = 0.0
                    except (TypeError, ValueError):
                        rate = 0.0

                    rules_rows.append({
                        "Category": r.get("category", "N/A"),
                        "Rule": r.get("rule", "N/A"),
                        "Pattern": r.get("pattern", r.get("description", "N/A")),
                        "Suspicious Rate": rate,
                    })

                rules_df = pd.DataFrame(rules_rows).sort_values(
                    "Suspicious Rate", ascending=False
                ).reset_index(drop=True)

                # Rules table
                st.subheader("Extracted Detection Rules")
                display_df = rules_df.copy()
                display_df["Suspicious Rate"] = display_df["Suspicious Rate"].apply(
                    lambda x: f"{100 * x:.1f}%"
                )
                st.dataframe(display_df, use_container_width=True, hide_index=True)

                st.markdown("---")

                # Rules bar chart ranked by effectiveness
                st.subheader("Rules Ranked by Effectiveness")
                chart_df = rules_df.head(15).copy()
                chart_df["label"] = (
                    chart_df["Category"].str[:3] + ": " + chart_df["Rule"].str[:40]
                )
                chart_df["rate_pct"] = chart_df["Suspicious Rate"] * 100

                category_colors = {
                    "AMOUNT": MODERN_TERMINAL_COLORS["green"],
                    "NETWORK": MODERN_TERMINAL_COLORS["cyan"],
                    "FREQUENCY": BLOOMBERG_COLORS["accent"],
                }

                fig_rules = go.Figure()
                for cat in chart_df["Category"].unique():
                    cat_data = chart_df[chart_df["Category"] == cat]
                    fig_rules.add_trace(go.Bar(
                        y=cat_data["label"],
                        x=cat_data["rate_pct"],
                        orientation="h",
                        name=cat,
                        marker_color=category_colors.get(cat, MODERN_TERMINAL_COLORS["muted"]),
                        hovertemplate=(
                            "<b>%{y}</b><br>"
                            "Suspicious Rate: %{x:.1f}%<extra></extra>"
                        ),
                    ))

                fig_rules.update_layout(
                    xaxis_title="Suspicious Rate (%)",
                    yaxis=dict(autorange="reversed"),
                    height=max(350, len(chart_df) * 30 + 80),
                    margin=dict(t=40, b=30, l=220),
                    legend=dict(orientation="h", y=1.08),
                    barmode="group",
                )
                apply_modern_terminal_plotly()
                st.plotly_chart(fig_rules, use_container_width=True)


# --- Sidebar ---

def render_sidebar():
    """Render the sidebar."""
    with st.sidebar:
        st.title("🔍 AML Pipeline")
        st.markdown("---")

        # System Status
        st.subheader("System Status")
        # Use lightweight /ping (no Celery/DB check) to avoid 5s+ blocking
        ping = api_request("GET", "/ping", timeout=3)

        if ping:
            st.success("API Online")
        else:
            st.error("API Offline")
            if st.button("Retry Connection"):
                st.rerun()
            st.markdown("Start the API server:")
            st.code("uvicorn app.api.main:app --reload", language="bash")

        st.markdown("---")

        # Quick Links
        st.subheader("Quick Links")
        st.markdown(f"[📚 API Docs]({API_BASE_URL}/docs)")
        st.markdown(f"[❤️ Health Check]({API_BASE_URL}/status/health)")

        st.markdown("---")

        # Plot Style Toggle
        st.subheader("Display Options")
        st.toggle(
            "Show Styled Plots",
            value=True,
            key="show_styled_plots",
            help="Toggle between Bloomberg-terminal styled plots and original plots"
        )

        st.markdown("---")

        # Help
        with st.expander("❓ Help"):
            st.markdown("""
            **Prerequisites:**
            1. Redis server running
            2. API server running
            3. Celery worker running

            **Commands:**
            ```bash
            # Terminal 1 - Redis
            redis-server

            # Terminal 2 - API
            uvicorn app.api.main:app --reload

            # Terminal 3 - Celery
            celery -A app.workers.celery_app worker -l info

            # Terminal 4 - Streamlit
            streamlit run app/ui/streamlit_app.py
            ```
            """)

        with st.expander("📖 About"):
            st.markdown("""
            **AML Pipeline Runner** v2.1

            A web UI for running and monitoring
            the AML end-to-end detection pipeline.

            Features:
            - Multi-pipeline support (e2e-core, e2e-dashboards)
            - Dataset profiles with sampling (Quick/Standard/Heavy/Full)
            - Standalone simulation with Start/Stop/Reset
            - Real-time progress monitoring
            - Interactive dashboards and reports
            """)


# --- Tier Queue Tab ---

def render_tier_queue_tab():
    """Render the Tier Queue tab with risk-ranked entities."""
    st.header("Tier Queue — Risk-Ranked Entities")

    # Run selector (same pattern as Analytics tab)
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found. Start a run first.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view the risk queue.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox(
        "Select Run", options=list(run_options.keys()), key="tier_queue_run_select"
    )
    selected_run_id = run_options[selected_label]

    # Load summary
    summary = api_request("GET", f"/runs/{selected_run_id}/risk-summary")
    if not summary or summary.get("detail"):
        st.warning(
            "Risk queue not available for this run. "
            "Re-run the pipeline or ensure `data/alert_nodes_td.csv` exists."
        )
        return

    # --- Label sparse warning ---
    sar_stats = summary.get("sar_label_stats", {})
    if sar_stats.get("label_sparse", False):
        sar_ct = sar_stats.get("sar_count", 0)
        sar_rt = sar_stats.get("sar_rate_pct", 0)
        st.warning(
            f"**Labels are sparse:** Only {sar_ct} SAR-labelled entities "
            f"({sar_rt:.3f}% of total). Risk ranking relies primarily on "
            f"network connectivity (degree). Consider enriching labels or "
            f"using a larger sample size for more robust scoring."
        )

    # --- Filter controls ---
    st.markdown("---")
    col_tier, col_pct, col_type, col_sar, col_search = st.columns([1.2, 1.2, 1.2, 1, 1.4])

    tier_counts = summary.get("tier_counts", {})

    with col_tier:
        tier_labels = [
            f"T1 ({tier_counts.get('T1', 0)})",
            f"T2 ({tier_counts.get('T2', 0)})",
            f"T3 ({tier_counts.get('T3', 0)})",
            f"T4 ({tier_counts.get('T4', 0)})",
        ]
        tier_values = ["T1", "T2", "T3", "T4"]
        selected_tier_labels = st.multiselect(
            "Tier Filter",
            options=tier_labels,
            default=[tier_labels[0], tier_labels[1]],
            key="tq_tier",
        )
        # Map labels back to values
        selected_tiers = [
            tier_values[tier_labels.index(lbl)]
            for lbl in selected_tier_labels
            if lbl in tier_labels
        ]

    with col_pct:
        max_percentile = st.slider(
            "Investigate Top X%", min_value=0.5, max_value=100.0,
            value=5.0, step=0.5, key="tq_pct",
        )

    with col_type:
        # Gather entity types from summary
        all_types = set()
        for tier_types in summary.get("top_types_per_tier", {}).values():
            all_types.update(tier_types.keys())
        all_types = sorted(all_types)
        selected_types = st.multiselect(
            "Entity Types", options=all_types, default=[], key="tq_etype",
        )

    with col_sar:
        sar_option = st.radio(
            "SAR Filter", ["All", "SAR Only", "Non-SAR"], key="tq_sar",
        )

    with col_search:
        search_text = st.text_input(
            "Search Entity ID", value="", key="tq_search",
        )

    # --- Reasons filter ---
    reason_options = ["SAR_LABEL", "HIGH_CONNECTIVITY"]
    selected_reasons = st.multiselect(
        "Filter by Reasons", options=reason_options, default=[], key="tq_reasons",
    )

    # --- Build query params ---
    params = {"limit": 500, "offset": 0, "max_percentile": max_percentile}
    if selected_tiers:
        params["tier"] = selected_tiers
    if selected_types:
        params["entity_type"] = selected_types
    if sar_option == "SAR Only":
        params["is_sar"] = 1
    elif sar_option == "Non-SAR":
        params["is_sar"] = 0
    if search_text.strip():
        params["search"] = search_text.strip()

    # Fetch filtered queue
    queue_data = api_request("GET", f"/runs/{selected_run_id}/risk-queue", params=params)
    if not queue_data or queue_data.get("detail"):
        st.warning("Could not load risk queue data.")
        return

    rows = queue_data.get("rows", [])

    # Client-side reasons filter
    if selected_reasons and rows:
        rows = [
            r for r in rows
            if any(reason in (r.get("reasons") or "") for reason in selected_reasons)
        ]

    total_filtered = len(rows)

    # --- KPI cards ---
    st.markdown("---")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    with kpi1:
        st.metric("Total Entities", f"{summary.get('total_entities', 0):,}")
    with kpi2:
        st.metric("Filtered Results", f"{total_filtered:,}")
    with kpi3:
        sar_count = summary.get("sar_count", 0)
        st.metric("SAR-Labelled", f"{sar_count:,}")
    with kpi4:
        # Top entity type in filtered results
        if rows:
            type_counts = {}
            for row in rows:
                t = row.get("entity_type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            top_type = max(type_counts, key=type_counts.get)
            st.metric("Top Type (filtered)", str(top_type))
        else:
            st.metric("Top Type (filtered)", "N/A")

    # --- Tier breakdown bar ---
    tier_cols = st.columns(4)
    tier_colors = {"T1": "#EF4444", "T2": "#F59E0B", "T3": "#3B82F6", "T4": "#6B7280"}
    for i, tier_name in enumerate(["T1", "T2", "T3", "T4"]):
        with tier_cols[i]:
            count = tier_counts.get(tier_name, 0)
            pct = (count / max(summary.get("total_entities", 1), 1)) * 100
            color = tier_colors[tier_name]
            st.markdown(
                f"<div style='text-align:center;padding:0.5rem;border-radius:6px;"
                f"border:1px solid {color};'>"
                f"<span style='color:{color};font-weight:700;font-size:1.1rem;'>{tier_name}</span><br>"
                f"<span style='color:#E5E7EB;font-size:1.3rem;font-weight:600;'>{count:,}</span><br>"
                f"<span style='color:#9CA3AF;font-size:0.85rem;'>{pct:.1f}%</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("")

    # --- Data table ---
    if rows:
        df = pd.DataFrame(rows)

        # Column ordering
        display_cols = [
            c for c in ["rank", "tier", "entity_id", "entity_type", "is_sar",
                         "risk_score", "degree", "percentile", "reasons"]
            if c in df.columns
        ]
        df = df[display_cols]

        # Format risk_score and percentile
        if "risk_score" in df.columns:
            df["risk_score"] = df["risk_score"].round(4)
        if "percentile" in df.columns:
            df["percentile"] = df["percentile"].round(2)

        st.dataframe(
            df,
            width="stretch",
            height=500,
            column_config={
                "rank": st.column_config.NumberColumn("Rank", format="%d"),
                "tier": st.column_config.TextColumn("Tier"),
                "entity_id": st.column_config.TextColumn("Entity ID"),
                "entity_type": st.column_config.TextColumn("Type"),
                "is_sar": st.column_config.NumberColumn("SAR", format="%d"),
                "risk_score": st.column_config.NumberColumn("Risk Score", format="%.4f"),
                "degree": st.column_config.NumberColumn("Degree", format="%d"),
                "percentile": st.column_config.NumberColumn("Pctile %", format="%.2f"),
                "reasons": st.column_config.TextColumn("Reasons"),
            },
        )

        # Download button
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="Download Filtered Queue (CSV)",
            data=csv_data,
            file_name=f"risk_queue_{selected_run_id[:8]}_filtered.csv",
            mime="text/csv",
            key="tq_download",
        )
    else:
        st.info("No entities match the current filters.")

    # --- Operating Point Panel ---
    st.markdown("---")
    st.subheader("Operating Point")

    # Load existing operating point if saved
    saved_op = api_request("GET", f"/runs/{selected_run_id}/operating-point")

    op_col1, op_col2 = st.columns([2, 1])
    with op_col1:
        if saved_op and not saved_op.get("detail"):
            saved_payload = saved_op.get("payload", {})
            saved_at = saved_op.get("saved_at", "")
            st.markdown(
                f"**Saved:** {saved_at[:19]}Z &nbsp;|&nbsp; "
                f"Top {saved_payload.get('top_percent', '?')}% &nbsp;|&nbsp; "
                f"Tiers: {', '.join(saved_payload.get('tiers', []))} &nbsp;|&nbsp; "
                f"SAR: {saved_payload.get('sar_filter', 'All')}"
            )
        else:
            st.caption("No operating point saved for this run yet.")

    with op_col2:
        if st.button("Save Operating Point", key="tq_save_op"):
            op_body = {
                "top_percent": max_percentile,
                "tiers": selected_tiers if selected_tiers else ["T1", "T2", "T3", "T4"],
                "entity_types": selected_types,
                "sar_filter": sar_option,
                "search": search_text.strip(),
            }
            result = api_request("POST", f"/runs/{selected_run_id}/operating-point", json=op_body)
            if result and not result.get("detail"):
                st.success("Operating point saved.")
            else:
                detail = result.get("detail", "Unknown error") if result else "API unavailable"
                st.error(f"Failed to save: {detail}")

    # Score distribution chart
    if rows and len(rows) > 5:
        st.markdown("---")
        st.subheader("Risk Score Distribution")
        df_chart = pd.DataFrame(rows)
        if "risk_score" in df_chart.columns and "tier" in df_chart.columns:
            fig = px.histogram(
                df_chart,
                x="risk_score",
                color="tier",
                nbins=40,
                color_discrete_map=tier_colors,
                labels={"risk_score": "Risk Score", "tier": "Tier"},
            )
            apply_modern_terminal_plotly()
            fig.update_layout(
                height=340,
                margin=dict(l=40, r=20, t=30, b=40),
                barmode="overlay",
                legend=dict(orientation="h", y=1.08),
            )
            fig.update_traces(opacity=0.75)
            st.plotly_chart(fig, width="stretch")


# --- Cases Tab ---

def render_cases_tab():
    """Render the Cases tab for investigation-ready AML cases."""
    st.header("Investigation Cases")

    # Run selector
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found. Start a run first.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view cases.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox(
        "Select Run", options=list(run_options.keys()), key="cases_run_select"
    )
    selected_run_id = run_options[selected_label]

    # Load cases summary
    summary = api_request("GET", f"/runs/{selected_run_id}/cases/summary")
    if not summary or summary.get("detail"):
        st.warning("Cases not available for this run. Re-run the pipeline to generate cases.")
        return

    total_cases = summary.get("total_cases", 0)
    if total_cases == 0:
        st.info("No cases generated — no seed entities matched the operating point criteria.")
        return

    # --- KPI cards ---
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Total Cases", f"{total_cases:,}")
    with kpi2:
        st.metric("Seed Entities", f"{summary.get('seed_count', 0):,}")
    with kpi3:
        st.metric("Entities in Cases", f"{summary.get('total_entities_in_cases', 0):,}")
    with kpi4:
        st.metric("SARs in Cases", f"{summary.get('total_sar_in_cases', 0):,}")

    # Typology counts bar
    typology_counts = summary.get("typology_counts", {})
    if typology_counts:
        typ_cols = st.columns(len(typology_counts))
        typ_colors = {
            "FAN_OUT": "#F59E0B", "FAN_IN": "#3B82F6", "CIRCULAR_FLOW": "#EF4444",
            "HUB_DOMINANCE": "#8B5CF6", "SAR_PROXIMITY": "#22C55E",
        }
        for i, (typ_name, typ_count) in enumerate(sorted(typology_counts.items())):
            with typ_cols[i]:
                color = typ_colors.get(typ_name, "#9CA3AF")
                st.markdown(
                    f"<div style='text-align:center;padding:0.4rem;border-radius:6px;"
                    f"border:1px solid {color};'>"
                    f"<span style='color:{color};font-weight:600;font-size:0.85rem;'>"
                    f"{typ_name}</span><br>"
                    f"<span style='color:#E5E7EB;font-size:1.2rem;font-weight:700;'>"
                    f"{typ_count}</span></div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # --- Filters ---
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        tier_filter = st.multiselect(
            "Tier Filter", ["T1", "T2", "T3", "T4"], default=[], key="cases_tier",
        )
    with filter_col2:
        typology_options = sorted(typology_counts.keys()) if typology_counts else []
        typology_filter = st.multiselect(
            "Typology Filter", typology_options, default=[], key="cases_typology",
        )
    with filter_col3:
        min_entities = st.number_input(
            "Min Entities", min_value=1, value=1, step=1, key="cases_min_ent",
        )

    # Build query params
    params = {"limit": 200, "offset": 0}
    if tier_filter:
        params["tier"] = tier_filter
    if typology_filter:
        params["typology"] = typology_filter
    if min_entities > 1:
        params["min_entities"] = min_entities

    # Fetch case list
    cases_data = api_request("GET", f"/runs/{selected_run_id}/cases", params=params)
    if not cases_data or cases_data.get("detail"):
        st.warning("Could not load cases.")
        return

    cases_list = cases_data.get("cases", [])

    if not cases_list:
        st.info("No cases match the current filters.")
        return

    # --- Case list table ---
    cases_df = pd.DataFrame(cases_list)
    display_cols = [
        c for c in ["case_id", "tier", "risk_score", "entity_count", "edge_count",
                     "sar_count", "typologies", "seed_count"]
        if c in cases_df.columns
    ]
    cases_df_display = cases_df[display_cols].copy()
    if "case_id" in cases_df_display.columns:
        cases_df_display["case_id"] = cases_df_display["case_id"].str[:12] + "..."
    if "risk_score" in cases_df_display.columns:
        cases_df_display["risk_score"] = cases_df_display["risk_score"].round(4)

    st.dataframe(
        cases_df_display,
        width="stretch",
        height=min(400, 35 * len(cases_df_display) + 60),
        column_config={
            "case_id": st.column_config.TextColumn("Case ID"),
            "tier": st.column_config.TextColumn("Tier"),
            "risk_score": st.column_config.NumberColumn("Risk Score", format="%.4f"),
            "entity_count": st.column_config.NumberColumn("Entities", format="%d"),
            "edge_count": st.column_config.NumberColumn("Edges", format="%d"),
            "sar_count": st.column_config.NumberColumn("SARs", format="%d"),
            "typologies": st.column_config.TextColumn("Typologies"),
            "seed_count": st.column_config.NumberColumn("Seeds", format="%d"),
        },
    )

    # --- Case detail view ---
    st.markdown("---")
    st.subheader("Case Detail")

    case_ids_full = cases_df["case_id"].tolist() if "case_id" in cases_df.columns else []
    if not case_ids_full:
        return

    case_select_options = {
        f"{cid[:12]}... (Tier {cases_df.iloc[i].get('tier', '?')}, "
        f"{cases_df.iloc[i].get('entity_count', 0)} entities)": cid
        for i, cid in enumerate(case_ids_full)
    }

    selected_case_label = st.selectbox(
        "Select Case to Inspect", options=list(case_select_options.keys()),
        key="cases_detail_select",
    )
    selected_case_id = case_select_options[selected_case_label]

    case_detail = api_request("GET", f"/runs/{selected_run_id}/cases/{selected_case_id}")
    if not case_detail or case_detail.get("detail"):
        st.warning("Could not load case detail.")
        return

    # Stats row
    stat1, stat2, stat3, stat4 = st.columns(4)
    with stat1:
        st.metric("Entities", case_detail.get("entity_count", 0))
    with stat2:
        st.metric("Edges", case_detail.get("edge_count", 0))
    with stat3:
        st.metric("SARs", case_detail.get("sar_count", 0))
    with stat4:
        st.metric("Risk Score", f"{case_detail.get('risk_score', 0):.4f}")

    # Typology badges
    case_typologies = case_detail.get("typologies", [])
    if case_typologies:
        badge_html = " ".join(
            f"<span style='display:inline-block;padding:0.25rem 0.6rem;"
            f"border-radius:12px;background:{typ_colors.get(t, '#374151')}22;"
            f"color:{typ_colors.get(t, '#9CA3AF')};font-weight:600;"
            f"font-size:0.85rem;margin-right:0.4rem;border:1px solid "
            f"{typ_colors.get(t, '#374151')};'>{t}</span>"
            for t in case_typologies
        )
        st.markdown(f"**Typologies:** {badge_html}", unsafe_allow_html=True)

    # Reasons
    case_reasons = case_detail.get("reasons", [])
    if case_reasons:
        st.markdown(f"**Reasons:** {', '.join(case_reasons)}")

    # Entity table
    entities = case_detail.get("entities", [])
    if entities:
        st.markdown("**Entities:**")
        ent_df = pd.DataFrame(entities)
        ent_display = [
            c for c in ["entity_id", "entity_type", "is_seed", "is_sar",
                         "risk_score", "tier", "degree"]
            if c in ent_df.columns
        ]
        ent_df = ent_df[ent_display]
        if "risk_score" in ent_df.columns:
            ent_df["risk_score"] = ent_df["risk_score"].round(4)
        st.dataframe(ent_df, width="stretch", height=250)

    # Interactive network graph (Plotly)
    edges = case_detail.get("edges", [])
    if entities and len(entities) > 1:
        st.markdown("**Network Graph:**")
        _render_case_network(entities, edges, case_typologies)

    # Download case JSON
    case_json_str = json.dumps(case_detail, indent=2)
    st.download_button(
        label="Download Case JSON",
        data=case_json_str,
        file_name=f"case_{selected_case_id[:12]}.json",
        mime="application/json",
        key="cases_download",
    )


def _render_case_network(entities: list, edges: list, typologies: list):
    """Render an interactive Plotly network graph for a case."""
    import math

    node_ids = [e["entity_id"] for e in entities]
    node_map = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)

    # Circular layout
    positions = {}
    for i, nid in enumerate(node_ids):
        angle = 2 * math.pi * i / n
        positions[nid] = (math.cos(angle), math.sin(angle))

    # Edge traces
    edge_x, edge_y = [], []
    for e in edges:
        src, dst = e.get("src"), e.get("dst")
        if src in positions and dst in positions:
            x0, y0 = positions[src]
            x1, y1 = positions[dst]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=0.8, color="#4B5563"),
        hoverinfo="none",
    )

    # Node traces
    node_x = [positions[nid][0] for nid in node_ids]
    node_y = [positions[nid][1] for nid in node_ids]
    node_colors = []
    node_sizes = []
    node_texts = []

    for e in entities:
        if e.get("is_seed"):
            node_colors.append("#EF4444" if e.get("is_sar") else "#FBBF24")
            node_sizes.append(14)
        elif e.get("is_sar"):
            node_colors.append("#22C55E")
            node_sizes.append(11)
        else:
            node_colors.append("#6B7280")
            node_sizes.append(8)
        node_texts.append(
            f"ID: {e['entity_id'][:12]}<br>"
            f"Type: {e.get('entity_type', '?')}<br>"
            f"Tier: {e.get('tier', '?')}<br>"
            f"Score: {e.get('risk_score', 0):.4f}<br>"
            f"Degree: {e.get('degree', 0)}<br>"
            f"SAR: {'Yes' if e.get('is_sar') else 'No'}<br>"
            f"Seed: {'Yes' if e.get('is_seed') else 'No'}"
        )

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers",
        marker=dict(size=node_sizes, color=node_colors, line=dict(width=1, color="#1F2937")),
        text=node_texts,
        hoverinfo="text",
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    apply_modern_terminal_plotly()
    fig.update_layout(
        showlegend=False,
        height=450,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    )

    # Legend annotation
    legend_text = (
        "<span style='color:#FBBF24'>● Seed</span> &nbsp; "
        "<span style='color:#EF4444'>● Seed+SAR</span> &nbsp; "
        "<span style='color:#22C55E'>● SAR</span> &nbsp; "
        "<span style='color:#6B7280'>● Other</span>"
    )
    st.markdown(legend_text, unsafe_allow_html=True)
    st.plotly_chart(fig, width="stretch")


# --- AML Scores Tab ---

def render_aml_scores_tab():
    """Render the AML Scores tab with composite risk scores per party."""
    st.header("AML Risk Scores — Composite Party Scoring")

    # Run selector
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found. Start a run first.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view AML scores.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox(
        "Select Run", options=list(run_options.keys()), key="aml_scores_run_select"
    )
    selected_run_id = run_options[selected_label]

    # Load summary (or offer to compute)
    summary = api_request("GET", f"/runs/{selected_run_id}/aml-summary")
    if not summary or summary.get("detail"):
        st.info("AML scores have not been computed for this run yet.")
        if st.button("Compute AML Scores", key="aml_compute_init"):
            with st.spinner("Computing AML scores..."):
                result = api_request("POST", f"/runs/{selected_run_id}/aml-scores/compute")
            if result and not result.get("detail"):
                st.success(
                    f"AML scores computed for {result.get('total_scored', '?')} parties. "
                    "Refresh the page to view results."
                )
                st.rerun()
            else:
                detail = result.get("detail", "Unknown error") if result else "API unavailable"
                st.error(f"Scoring failed: {detail}")
        return

    band_dist = summary.get("band_distribution", {})
    band_colors = {
        "Critical": "#EF4444", "High": "#F59E0B",
        "Medium": "#3B82F6", "Low": "#6B7280",
    }

    # Degraded mode notice
    signals_available = summary.get("signals_available", [])
    all_signals = {"sar", "laundering", "network", "geo", "volume"}
    missing_signals = all_signals - set(signals_available)
    if missing_signals:
        missing_labels = ", ".join(sorted(missing_signals))
        st.warning(
            f"**Degraded scoring mode:** {len(signals_available)}/5 signals active "
            f"({', '.join(signals_available)}). "
            f"Missing signals ({missing_labels}) require enrichment data "
            f"(`extra_info.csv`). Band distribution may show empty bands."
        )

    # --- Filter controls ---
    st.markdown("---")
    col_band, col_score, col_sar, col_laun, col_search = st.columns([1.5, 1.5, 1, 1, 1.5])

    with col_band:
        band_labels = [
            f"Critical ({band_dist.get('Critical', 0)})",
            f"High ({band_dist.get('High', 0)})",
            f"Medium ({band_dist.get('Medium', 0)})",
            f"Low ({band_dist.get('Low', 0)})",
        ]
        band_values = ["Critical", "High", "Medium", "Low"]
        selected_band_labels = st.multiselect(
            "Risk Band", options=band_labels,
            default=[band_labels[0], band_labels[1]],
            key="aml_band",
        )
        selected_bands = [
            band_values[band_labels.index(lbl)]
            for lbl in selected_band_labels if lbl in band_labels
        ]

    with col_score:
        score_range = st.slider(
            "Score Range", min_value=0.0, max_value=100.0,
            value=(0.0, 100.0), step=1.0, key="aml_score_range",
        )

    with col_sar:
        sar_option = st.radio(
            "SAR Filter", ["All", "SAR Only", "Non-SAR"], key="aml_sar",
        )

    with col_laun:
        laun_option = st.radio(
            "Laundering", ["All", "Has Laundering"], key="aml_laun",
        )

    with col_search:
        search_text = st.text_input(
            "Search Entity ID", value="", key="aml_search",
        )

    # Sort controls
    sort_col1, sort_col2 = st.columns([1, 1])
    with sort_col1:
        sort_by = st.selectbox(
            "Sort By",
            options=["aml_score", "sar_signal", "laundering_signal",
                     "network_signal", "geo_signal", "volume_signal",
                     "txn_count", "total_amt"],
            index=0, key="aml_sort_by",
        )
    with sort_col2:
        sort_order = st.selectbox(
            "Order", options=["desc", "asc"], index=0, key="aml_sort_order",
        )

    # Build query params
    params = {
        "limit": 500, "offset": 0,
        "sort_by": sort_by, "sort_order": sort_order,
    }
    if selected_bands:
        params["band"] = selected_bands
    if score_range[0] > 0:
        params["min_score"] = score_range[0]
    if score_range[1] < 100:
        params["max_score"] = score_range[1]
    if sar_option == "SAR Only":
        params["is_sar"] = 1
    elif sar_option == "Non-SAR":
        params["is_sar"] = 0
    if laun_option == "Has Laundering":
        params["has_laundering"] = 1
    if search_text.strip():
        params["search"] = search_text.strip()

    # Fetch filtered scores
    score_data = api_request("GET", f"/runs/{selected_run_id}/aml-scores", params=params)
    if not score_data or score_data.get("detail"):
        st.warning("Could not load AML score data.")
        return

    rows = score_data.get("rows", [])
    total_filtered = len(rows)

    # --- KPI cards + recompute ---
    st.markdown("---")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi_btn = st.columns([1, 1, 1, 1, 1, 0.8])

    with kpi1:
        st.metric("Total Scored", f"{summary.get('total_scored', 0):,}")
    with kpi2:
        st.metric("Filtered", f"{total_filtered:,}")
    with kpi3:
        st.metric("Mean Score", f"{summary.get('mean_score', 0):.1f}")
    with kpi4:
        critical_ct = band_dist.get("Critical", 0)
        high_ct = band_dist.get("High", 0)
        st.metric("Critical + High", f"{critical_ct + high_ct:,}")
    with kpi5:
        st.metric("Median Score", f"{summary.get('median_score', 0):.1f}")
    with kpi_btn:
        st.caption("")  # spacer for alignment
        if st.button("Recompute", key="aml_recompute"):
            with st.spinner("Recomputing AML scores..."):
                result = api_request("POST", f"/runs/{selected_run_id}/aml-scores/compute")
            if result and not result.get("detail"):
                st.success("Scores recomputed.")
                st.rerun()
            else:
                detail = result.get("detail", "Unknown error") if result else "API unavailable"
                st.error(f"Failed: {detail}")

    # --- Band breakdown ---
    band_cols = st.columns(4)
    for i, band_name in enumerate(["Critical", "High", "Medium", "Low"]):
        with band_cols[i]:
            count = band_dist.get(band_name, 0)
            total_scored = max(summary.get("total_scored", 1), 1)
            pct = (count / total_scored) * 100
            color = band_colors[band_name]
            st.markdown(
                f"<div style='text-align:center;padding:0.5rem;border-radius:6px;"
                f"border:1px solid {color};'>"
                f"<span style='color:{color};font-weight:700;font-size:1.1rem;'>{band_name}</span><br>"
                f"<span style='color:#E5E7EB;font-size:1.3rem;font-weight:600;'>{count:,}</span><br>"
                f"<span style='color:#9CA3AF;font-size:0.85rem;'>{pct:.1f}%</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("")

    # --- Data table ---
    if rows:
        df = pd.DataFrame(rows)

        display_cols = [
            c for c in [
                "entity_id", "risk_band", "aml_score", "is_sar",
                "sar_signal", "laundering_signal", "network_signal",
                "geo_signal", "volume_signal",
                "degree", "txn_count", "total_amt",
                "laundering_txn_count", "cross_border_count",
                "reasons",
            ]
            if c in df.columns
        ]
        df_display = df[display_cols].copy()

        # Round numeric columns
        for col in ["aml_score", "sar_signal", "laundering_signal",
                     "network_signal", "geo_signal", "volume_signal", "total_amt"]:
            if col in df_display.columns:
                df_display[col] = df_display[col].round(3)

        st.dataframe(
            df_display,
            width="stretch",
            height=500,
            column_config={
                "entity_id": st.column_config.TextColumn("Entity ID"),
                "risk_band": st.column_config.TextColumn("Band"),
                "aml_score": st.column_config.NumberColumn("AML Score", format="%.1f"),
                "is_sar": st.column_config.NumberColumn("SAR", format="%d"),
                "sar_signal": st.column_config.NumberColumn("SAR Sig", format="%.3f"),
                "laundering_signal": st.column_config.NumberColumn("Laun Sig", format="%.3f"),
                "network_signal": st.column_config.NumberColumn("Net Sig", format="%.3f"),
                "geo_signal": st.column_config.NumberColumn("Geo Sig", format="%.3f"),
                "volume_signal": st.column_config.NumberColumn("Vol Sig", format="%.3f"),
                "degree": st.column_config.NumberColumn("Degree", format="%d"),
                "txn_count": st.column_config.NumberColumn("Txn Count", format="%d"),
                "total_amt": st.column_config.NumberColumn("Total Amt", format="%.2f"),
                "laundering_txn_count": st.column_config.NumberColumn("Laun Txns", format="%d"),
                "cross_border_count": st.column_config.NumberColumn("Cross-Border", format="%d"),
                "reasons": st.column_config.TextColumn("Reasons"),
            },
        )

        # Download
        csv_data = df_display.to_csv(index=False)
        st.download_button(
            label="Download Filtered AML Scores (CSV)",
            data=csv_data,
            file_name=f"aml_scores_{selected_run_id[:8]}_filtered.csv",
            mime="text/csv",
            key="aml_download",
        )
        # --- Per-entity signal contribution ---
        st.markdown("---")
        st.subheader("Signal Contribution — Entity Detail")
        signal_cols_detail = ["sar_signal", "laundering_signal", "network_signal",
                              "geo_signal", "volume_signal"]
        signal_labels = {"sar_signal": "SAR", "laundering_signal": "Laundering",
                         "network_signal": "Network", "geo_signal": "Geo",
                         "volume_signal": "Volume"}
        signal_colors_map = {"SAR": "#EF4444", "Laundering": "#F59E0B",
                             "Network": "#8B5CF6", "Geo": "#3B82F6", "Volume": "#22C55E"}

        entity_options = df_display["entity_id"].head(50).tolist()
        if entity_options:
            selected_entity = st.selectbox(
                "Select entity to inspect",
                options=entity_options,
                key="aml_entity_detail",
            )
            entity_row = df[df["entity_id"] == selected_entity].iloc[0]

            detail_vals = []
            detail_labels = []
            detail_colors = []
            for sc in signal_cols_detail:
                if sc in entity_row.index:
                    val = float(entity_row[sc])
                    label = signal_labels[sc]
                    detail_vals.append(val)
                    detail_labels.append(label)
                    detail_colors.append(signal_colors_map.get(label, "#6B7280"))

            if detail_vals:
                fig_bar = go.Figure(go.Bar(
                    x=detail_labels,
                    y=detail_vals,
                    marker_color=detail_colors,
                    text=[f"{v:.3f}" for v in detail_vals],
                    textposition="outside",
                ))
                apply_modern_terminal_plotly()
                fig_bar.update_layout(
                    height=300,
                    margin=dict(l=40, r=20, t=30, b=40),
                    yaxis=dict(range=[0, 1.15], title="Signal Strength"),
                    xaxis=dict(title=""),
                )
                col_chart, col_info = st.columns([2, 1])
                with col_chart:
                    st.plotly_chart(fig_bar, width="stretch")
                with col_info:
                    st.markdown(f"**Entity:** `{selected_entity}`")
                    st.markdown(f"**AML Score:** {entity_row.get('aml_score', 0):.1f}")
                    st.markdown(f"**Band:** {entity_row.get('risk_band', 'N/A')}")
                    st.markdown(f"**SAR:** {'Yes' if entity_row.get('is_sar', 0) else 'No'}")
                    st.markdown(f"**Degree:** {int(entity_row.get('degree', 0))}")
                    reasons = entity_row.get("reasons", "")
                    if reasons:
                        st.markdown("**Reasons:**")
                        for r in str(reasons).split(", "):
                            st.markdown(f"- `{r}`")
    else:
        st.info("No entities match the current filters.")

    # --- Score distribution histogram ---
    if rows and len(rows) > 5:
        st.markdown("---")
        st.subheader("AML Score Distribution")
        df_chart = pd.DataFrame(rows)
        if "aml_score" in df_chart.columns and "risk_band" in df_chart.columns:
            fig = px.histogram(
                df_chart,
                x="aml_score",
                color="risk_band",
                nbins=50,
                color_discrete_map=band_colors,
                labels={"aml_score": "AML Score", "risk_band": "Risk Band"},
            )
            apply_modern_terminal_plotly()
            fig.update_layout(
                height=340,
                margin=dict(l=40, r=20, t=30, b=40),
                barmode="overlay",
                legend=dict(orientation="h", y=1.08),
            )
            fig.update_traces(opacity=0.75)
            st.plotly_chart(fig, width="stretch")

    # --- Signal radar chart for top entities ---
    if rows and len(rows) > 0:
        st.markdown("---")
        st.subheader("Signal Breakdown — Top Entities")

        signal_cols = ["sar_signal", "laundering_signal", "network_signal",
                       "geo_signal", "volume_signal"]
        df_radar = pd.DataFrame(rows[:10])  # top 10 by current sort

        if all(c in df_radar.columns for c in signal_cols):
            fig_radar = go.Figure()
            categories = ["SAR", "Laundering", "Network", "Geo", "Volume"]

            for _, row in df_radar.head(5).iterrows():
                values = [row[c] for c in signal_cols]
                values.append(values[0])  # close the radar
                eid = str(row.get("entity_id", "?"))[:12]
                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=categories + [categories[0]],
                    name=eid,
                    fill="toself",
                    opacity=0.5,
                ))

            apply_modern_terminal_plotly()
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 1]),
                    bgcolor="rgba(0,0,0,0)",
                ),
                height=420,
                margin=dict(l=60, r=60, t=40, b=40),
                legend=dict(orientation="h", y=-0.15),
            )
            st.plotly_chart(fig_radar, width="stretch")


# --- Simulation Tab ---


def render_simulation_tab():
    """Render the Simulation tab — live Start/Stop/Reset controls with real-time charts."""
    apply_modern_terminal_plotly()

    # ── Fetch current simulation status ────────────────────────
    sim_status = api_request("GET", "/simulation/status") or {}
    status = sim_status.get("status", "idle")

    # ── Source Run Selection ───────────────────────────────────
    st.subheader("Source Run")
    st.caption("Select a completed pipeline run whose trained models power the simulation.")

    source_runs_data = api_request("GET", "/runs/completed-sources?limit=15")
    source_runs = source_runs_data.get("runs", []) if source_runs_data else []

    source_run_id = None
    if source_runs:
        source_options = {
            r["id"]: f"{r['id'][:8]}  |  {r.get('pipeline_name', '?')}  |  {r.get('dataset_mode', '?')}  |  {format_datetime(r.get('completed_at', ''))}"
            for r in source_runs
        }
        source_run_id = st.selectbox(
            "Completed run with trained models",
            options=list(source_options.keys()),
            format_func=lambda x: source_options[x],
            key="sim_source_run_select",
        )
    else:
        st.warning("No completed runs with trained models found. Run **e2e-core** or **e2e-dashboards** first.")

    # ── Configuration Panel ────────────────────────────────────
    with st.expander("Simulation Configuration", expanded=status == "idle"):
        cfg1, cfg2, cfg3 = st.columns(3)
        with cfg1:
            num_batches = st.number_input("Batches", min_value=1, max_value=500, value=80, key="sim_batches")
            batch_size = st.number_input("Batch Size", min_value=10, max_value=500, value=50, key="sim_batch_size")
        with cfg2:
            pattern_prob = st.slider("Pattern Probability", min_value=0.0, max_value=1.0, value=0.10, step=0.01, key="sim_pattern_prob")
            batch_interval = st.slider("Batch Interval (s)", min_value=0.1, max_value=10.0, value=0.5, step=0.1, key="sim_interval")
        with cfg3:
            rescore_interval = st.number_input("Rescore Interval", min_value=1, max_value=50, value=3, key="sim_rescore")
            threshold_pct = st.number_input("Threshold Percentile", min_value=80, max_value=100, value=99, key="sim_thresh")

    # ── Control Buttons ────────────────────────────────────────
    st.divider()
    btn1, btn2, btn3, btn_spacer = st.columns([2, 2, 2, 6])

    with btn1:
        start_disabled = status not in ("idle", "finished", "stopped", "error") or not source_run_id
        if st.button("START", type="primary", use_container_width=True, disabled=start_disabled):
            result = api_request("POST", "/simulation/start", json={
                "source_run_id": source_run_id,
                "num_batches": num_batches,
                "batch_size": batch_size,
                "batch_interval": batch_interval,
                "pattern_prob": pattern_prob,
                "rescore_interval": rescore_interval,
                "threshold_percentile": threshold_pct,
                "seed": 42,
            })
            if result:
                st.success(f"Simulation started: {result.get('sim_id', '')[:8]}")
            else:
                st.error("Failed to start simulation. Check API logs.")
            st.rerun()

    with btn2:
        stop_disabled = status not in ("running", "starting")
        if st.button("STOP", use_container_width=True, disabled=stop_disabled):
            api_request("POST", "/simulation/stop")
            st.rerun()

    with btn3:
        if st.button("RESET", use_container_width=True):
            api_request("POST", "/simulation/reset")
            st.rerun()

    # ── Status Badge ───────────────────────────────────────────
    status_colors = {
        "idle": "#9CA3AF", "starting": "#FBBF24", "running": "#22C55E",
        "stopping": "#FBBF24", "stopped": "#22D3EE", "finished": "#22D3EE", "error": "#EF4444",
    }
    badge_color = status_colors.get(status, "#9CA3AF")
    st.markdown(
        f'<div style="display:inline-block;padding:4px 14px;border-radius:12px;'
        f'background:{badge_color}22;border:1px solid {badge_color};color:{badge_color};'
        f'font-weight:600;font-size:0.9em;margin-bottom:8px;">{status.upper()}</div>',
        unsafe_allow_html=True,
    )

    # Show error if any
    if sim_status.get("error"):
        st.error(f"Simulation error: {sim_status['error']}")

    # ── KPI Metrics ────────────────────────────────────────────
    if status not in ("idle",):
        batch_num = sim_status.get("batch_num", 0)
        total_batches = sim_status.get("total_batches", 0)
        total_txns = sim_status.get("total_txns", 0)
        total_alerts = sim_status.get("total_alerts", 0)
        total_patterns = sim_status.get("total_patterns", 0)
        elapsed = sim_status.get("elapsed", 0)
        threshold = sim_status.get("threshold", 0)
        confusion = sim_status.get("confusion", {})

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Batches", f"{batch_num}/{total_batches}")
        k2.metric("Transactions", f"{total_txns:,}")
        k3.metric("Alerts", f"{total_alerts:,}")
        k4.metric("Patterns", f"{total_patterns}")
        k5.metric("Duration", f"{elapsed:.1f}s")

        # ── Status line ────────────────────────────────────────
        last_info = sim_status.get("last_batch_info", "")
        if last_info:
            st.caption(last_info)

        st.divider()

        # ── Score Time Series + Alert Feed ─────────────────────
        score_history = sim_status.get("score_history", [])
        recent_alerts = sim_status.get("recent_alerts", [])

        col_ts, col_alert = st.columns([7, 5])

        with col_ts:
            if score_history:
                # score_history is list of tuples: (batch, mean, max, n_alerts)
                sh_df = pd.DataFrame(score_history, columns=["batch", "mean", "max", "n_alerts"])
                fig_ts = go.Figure()
                fig_ts.add_trace(go.Scatter(
                    x=sh_df["batch"], y=sh_df["mean"],
                    mode="lines", name="Mean Score",
                    fill="tozeroy", fillcolor="rgba(52,152,219,0.15)",
                    line=dict(width=2),
                ))
                fig_ts.add_trace(go.Scatter(
                    x=sh_df["batch"], y=sh_df["max"],
                    mode="lines", name="Max Score",
                    line=dict(width=1, dash="dot"),
                ))
                if threshold > 0:
                    fig_ts.add_hline(
                        y=threshold, line_dash="dash",
                        annotation_text=f"Threshold={threshold:.2f}",
                    )
                # Alert markers
                alert_rows = sh_df[sh_df["n_alerts"] > 0]
                if len(alert_rows) > 0:
                    fig_ts.add_trace(go.Scatter(
                        x=alert_rows["batch"], y=alert_rows["max"],
                        mode="markers", name="Alert Batch",
                        marker=dict(size=8, symbol="triangle-down", color="#E74C3C"),
                    ))
                fig_ts.update_layout(
                    title="Score Time Series (Live)",
                    xaxis_title="Batch", yaxis_title="Anomaly Score",
                    height=350,
                    margin=dict(t=40, b=30, l=50, r=10),
                    legend=dict(orientation="h", y=-0.18),
                )
                st.plotly_chart(fig_ts, use_container_width=True)
            else:
                st.caption("Waiting for score data...")

        with col_alert:
            st.markdown("**Recent Alerts**")
            if recent_alerts:
                alert_df = pd.DataFrame(recent_alerts)
                st.dataframe(alert_df.tail(20), use_container_width=True, hide_index=True)
            else:
                st.caption("No alerts yet.")

        # ── Confusion Matrix + Score Histogram ─────────────────
        col_cm, col_hist = st.columns([5, 7])

        with col_cm:
            tp = confusion.get("tp", 0)
            fp = confusion.get("fp", 0)
            fn = confusion.get("fn", 0)
            tn = confusion.get("tn", 0)

            if tp + fp + fn + tn > 0:
                cm_array = np.array([[tn, fp], [fn, tp]])
                fig_cm = go.Figure(data=go.Heatmap(
                    z=cm_array,
                    x=["Pred: Normal", "Pred: Anomaly"],
                    y=["Actual: Normal", "Actual: SAR"],
                    text=[[f"{cm_array[i][j]:,}" for j in range(2)] for i in range(2)],
                    texttemplate="%{text}",
                    textfont={"size": 16},
                    colorscale="YlOrRd",
                    showscale=False,
                ))
                fig_cm.update_layout(
                    title="Confusion Matrix",
                    height=350,
                    margin=dict(t=40, b=30, l=100, r=10),
                )
                st.plotly_chart(fig_cm, use_container_width=True)

                # Detection KPIs
                precision = tp / max(tp + fp, 1)
                recall = tp / max(tp + fn, 1)
                f1 = 2 * precision * recall / max(precision + recall, 1e-9)
                dk1, dk2, dk3 = st.columns(3)
                dk1.metric("Precision", f"{precision:.4f}")
                dk2.metric("Recall", f"{recall:.4f}")
                dk3.metric("F1 Score", f"{f1:.4f}")
            else:
                st.caption("No detection data yet.")

        with col_hist:
            all_scores = sim_status.get("all_scores", [])
            sar_labels = sim_status.get("sar_labels", [])
            if all_scores:
                scores_arr = np.array(all_scores)
                labels_arr = np.array(sar_labels) if sar_labels else np.zeros(len(all_scores))
                fig_hist = go.Figure()
                normal_mask = labels_arr == 0
                sar_mask = labels_arr == 1
                if normal_mask.any():
                    fig_hist.add_trace(go.Histogram(
                        x=scores_arr[normal_mask], name="Normal",
                        nbinsx=50, opacity=0.6, marker_color="#3498DB",
                    ))
                if sar_mask.any():
                    fig_hist.add_trace(go.Histogram(
                        x=scores_arr[sar_mask], name="SAR",
                        nbinsx=50, opacity=0.7, marker_color="#E74C3C",
                    ))
                if threshold > 0:
                    fig_hist.add_vline(
                        x=threshold, line_dash="dash", line_color="#FBBF24",
                        annotation_text=f"Threshold={threshold:.2f}",
                    )
                fig_hist.update_layout(
                    title="Score Distribution (Normal vs SAR)",
                    xaxis_title="Anomaly Score", yaxis_title="Count",
                    barmode="overlay", height=350,
                    margin=dict(t=40, b=30),
                    legend=dict(orientation="h", y=-0.18),
                )
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.caption("Waiting for score distribution data...")

        # ── Latency Analysis ───────────────────────────────────
        latency_history = sim_status.get("latency_history", [])
        if len(latency_history) > 1:
            st.divider()
            # latency_history is a list of floats (latency values in ms)
            lat_arr = np.array(latency_history)
            batch_nums = list(range(1, len(lat_arr) + 1))
            col_bar, col_lhist = st.columns(2)

            with col_bar:
                fig_bar = go.Figure(go.Bar(
                    x=batch_nums, y=lat_arr,
                    marker_color="#3498DB", opacity=0.7,
                ))
                mean_lat = float(lat_arr.mean())
                fig_bar.add_hline(
                    y=mean_lat, line_dash="dash",
                    annotation_text=f"Mean: {mean_lat:.0f}ms",
                )
                fig_bar.update_layout(
                    title="Scoring Latency per Batch",
                    xaxis_title="Batch", yaxis_title="Latency (ms)",
                    height=380, margin=dict(t=40, b=30),
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            with col_lhist:
                p95 = float(np.percentile(lat_arr, 95))
                fig_lhist = go.Figure(go.Histogram(
                    x=lat_arr, nbinsx=30, opacity=0.7,
                ))
                fig_lhist.add_vline(x=p95, line_dash="dash", line_color="#E74C3C",
                                    annotation_text=f"P95: {p95:.0f}ms")
                fig_lhist.add_vline(x=mean_lat, line_dash="dash", line_color="#2ECC71",
                                    annotation_text=f"Mean: {mean_lat:.0f}ms")
                fig_lhist.update_layout(
                    title="Latency Distribution",
                    xaxis_title="Latency (ms)", yaxis_title="Count",
                    height=380, margin=dict(t=40, b=30),
                )
                st.plotly_chart(fig_lhist, use_container_width=True)

            # Latency KPIs
            lk1, lk2, lk3, lk4 = st.columns(4)
            lk1.metric("Mean Latency", f"{mean_lat:.0f}ms")
            lk2.metric("P95 Latency", f"{p95:.0f}ms")
            throughput = total_txns / max(elapsed, 0.01)
            lk3.metric("Throughput", f"{throughput:.0f} txns/s")
            pattern_nodes = sim_status.get("pattern_nodes", 0)
            lk4.metric("Pattern Nodes", f"{pattern_nodes}")

    # ── Post-Simulation Analysis (shown when stopped/finished) ──────
    if status in ("stopped", "finished"):
        st.divider()
        st.subheader("Post-Simulation Analysis")

        # Summary metrics
        cm = confusion
        tp, fp, fn, tn = cm.get("tp", 0), cm.get("fp", 0), cm.get("fn", 0), cm.get("tn", 0)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)

        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.metric("Duration", f"{elapsed:.1f}s")
        throughput = total_txns / max(elapsed, 0.01)
        s2.metric("Throughput", f"{throughput:.0f} txns/s")
        s3.metric("Precision", f"{precision:.4f}")
        s4.metric("Recall", f"{recall:.4f}")
        s5.metric("F1 Score", f"{f1:.4f}")
        if latency_history:
            p95_lat = float(np.percentile(latency_history, 95))
            s6.metric("P95 Latency", f"{p95_lat:.0f}ms")
        else:
            s6.metric("P95 Latency", "--")

        # Saved results location
        sim_id = sim_status.get("sim_id", "")
        if sim_id:
            st.caption(f"Results saved to: `artifacts/simulations/{sim_id}/`")

        # Investigation section (top alert)
        st.divider()
        st.subheader("Investigation")

        recent_alerts = sim_status.get("recent_alerts", [])
        if recent_alerts:
            # Find top alert by score
            top_alert = max(recent_alerts, key=lambda a: a.get("score", 0))
            inv1, inv2 = st.columns([3, 9])

            with inv1:
                st.markdown("**Top Alert Node**")
                st.metric("Node ID", top_alert.get("node_id", "N/A")[:12])
                st.metric("Score", f"{top_alert.get('score', 0):.4f}")
                st.metric("SAR", "Yes" if top_alert.get("is_sar") else "No")
                st.metric("Batch", str(top_alert.get("batch", "--")))

            with inv2:
                st.markdown("**Alert Details**")
                # Show all alerts in a table
                alert_df = pd.DataFrame(recent_alerts)
                if len(alert_df) > 0:
                    alert_df = alert_df.sort_values("score", ascending=False)
                    display_cols = ["batch", "node_id", "score", "is_sar", "timestamp"]
                    display_cols = [c for c in display_cols if c in alert_df.columns]
                    st.dataframe(alert_df[display_cols].head(20), use_container_width=True, hide_index=True)
        else:
            st.info("No alerts generated during simulation.")

    # ── Auto-refresh for active simulation ─────────────────────
    if status in ("running", "starting", "stopping"):
        st.info(f"Simulation {status}. Auto-refreshing every {POLL_INTERVAL} seconds...")
        time.sleep(POLL_INTERVAL)
        st.rerun()


# --- Main ---

def main():
    """Main application entry point."""
    render_sidebar()

    # Tab navigation
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
        "🚀 Run", "📊 Status", "📈 Dashboard", "🔬 Graph & Scoring",
        "📄 Report", "🗃 Tables", "⚡ Tier Queue",
        "🧩 Cases", "🎯 AML Scores", "🎮 Simulation",
    ])

    with tab1:
        render_run_tab()

    with tab2:
        render_status_tab()

    with tab3:
        render_dashboard_tab()

    with tab4:
        render_graph_scoring_tab()

    with tab5:
        render_report_tab()

    with tab6:
        render_tables_tab()

    with tab7:
        render_tier_queue_tab()

    with tab8:
        render_cases_tab()

    with tab9:
        render_aml_scores_tab()

    with tab10:
        render_simulation_tab()


if __name__ == "__main__":
    main()
