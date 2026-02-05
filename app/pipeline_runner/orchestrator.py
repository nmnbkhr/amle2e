"""
Pipeline Orchestrator

Executes AML E2E pipeline notebooks sequentially.
Supports multiple e2e pipeline variants (core, dashboards, realtime)
via the pipeline registry, and multiple dataset profiles via the dataset
registry.

Features:
- Papermill-based execution with fallback to nbclient
- Per-step logging to files
- Progress tracking via callbacks
- Artifact collection after execution
- Configurable timeouts and parameters
- Multi-pipeline support (legacy + e2e)
- SAML-D out-of-core ingestion via DuckDB
"""

import os
import sys
import json
import shutil
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional, Dict, Any, Tuple
from io import StringIO

from ..utils.paths import (
    get_repo_root,
    get_run_dir,
    get_data_dir,
    get_plots_dir,
    get_models_dir,
    get_logs_dir,
    get_report_dir,
)
from ..reports.png_styler import style_pngs
from .pipeline_registry import (
    get_pipeline,
    resolve_steps,
    write_manifest,
    PipelineSpec,
    E2E_CORE,
)
from ..datasets.dataset_registry import (
    get_dataset,
    get_max_rows,
    DatasetSpec,
    SAMPLING_PROFILES,
)

logger = logging.getLogger(__name__)

# Project root directory (resolved via utils)
PROJECT_ROOT = get_repo_root()

# Default notebook timeout in seconds (30 minutes)
DEFAULT_NOTEBOOK_TIMEOUT = 1800

# Run profiles with predefined parameters
RUN_PROFILES = {
    "quick": {
        "sample_size": 5000,
        "epochs": 2,
        "threshold": 0.99,
        "description": "Quick test run with minimal data",
    },
    "standard": {
        "sample_size": 20000,
        "epochs": 5,
        "threshold": 0.99,
        "description": "Standard run with balanced settings",
    },
    "heavy": {
        "sample_size": 100000,
        "epochs": 10,
        "threshold": 0.995,
        "description": "Heavy run - requires 12GB+ VRAM",
    },
}


class NotebookExecutor:
    """
    Handles execution of individual notebooks using papermill with nbclient fallback.
    """

    def __init__(self, project_root: Path, output_dir: Path, log_dir: Path):
        self.project_root = project_root
        self.output_dir = output_dir
        self.log_dir = log_dir

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        notebook_path: Path,
        parameters: Dict[str, Any],
        timeout: int = DEFAULT_NOTEBOOK_TIMEOUT,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Execute a notebook using papermill, with nbclient fallback.

        Args:
            notebook_path: Path to the notebook
            parameters: Parameters to inject
            timeout: Execution timeout in seconds

        Returns:
            Tuple of (success, output_path, error_message)
        """
        notebook_name = notebook_path.name
        output_path = self.output_dir / notebook_name
        log_path = self.log_dir / f"{notebook_path.stem}.log"

        # Capture logs
        log_content = StringIO()

        try:
            # Try papermill first
            success, error = self._execute_with_papermill(
                notebook_path, output_path, parameters, timeout, log_content
            )

            if not success and "parameters" in str(error).lower():
                # Fallback to nbclient if papermill fails due to parameter issues
                logger.info(f"Papermill failed, falling back to nbclient for {notebook_name}")
                log_content.write(f"\n--- Falling back to nbclient ---\n")
                success, error = self._execute_with_nbclient(
                    notebook_path, output_path, timeout, log_content
                )

        except Exception as e:
            success = False
            error = str(e)
            log_content.write(f"\nExecution error: {error}\n")
            log_content.write(traceback.format_exc())

        # Write log file
        with open(log_path, "w") as f:
            f.write(log_content.getvalue())

        return success, str(output_path) if output_path.exists() else None, error if not success else None

    def _execute_with_papermill(
        self,
        notebook_path: Path,
        output_path: Path,
        parameters: Dict[str, Any],
        timeout: int,
        log_stream: StringIO,
    ) -> Tuple[bool, Optional[str]]:
        """Execute notebook using papermill."""
        try:
            import papermill as pm

            log_stream.write(f"Executing {notebook_path.name} with papermill\n")
            log_stream.write(f"Parameters: {json.dumps(parameters, indent=2)}\n")
            log_stream.write(f"Timeout: {timeout}s\n")
            log_stream.write("-" * 50 + "\n")

            # Execute with papermill
            pm.execute_notebook(
                str(notebook_path),
                str(output_path),
                parameters=parameters,
                cwd=str(self.project_root),
                kernel_name="python3",
                progress_bar=False,
                log_output=True,
                stdout_file=log_stream,
                stderr_file=log_stream,
                execution_timeout=timeout,
            )

            log_stream.write("-" * 50 + "\n")
            log_stream.write("Execution completed successfully\n")
            return True, None

        except pm.PapermillExecutionError as e:
            error_msg = f"Papermill execution error: {e}"
            log_stream.write(f"\n{error_msg}\n")
            return False, error_msg

        except Exception as e:
            error_msg = f"Papermill error: {e}"
            log_stream.write(f"\n{error_msg}\n")
            log_stream.write(traceback.format_exc())
            return False, error_msg

    def _execute_with_nbclient(
        self,
        notebook_path: Path,
        output_path: Path,
        timeout: int,
        log_stream: StringIO,
    ) -> Tuple[bool, Optional[str]]:
        """Execute notebook using nbclient (fallback)."""
        try:
            import nbformat
            from nbclient import NotebookClient
            from nbclient.exceptions import CellExecutionError

            log_stream.write(f"Executing {notebook_path.name} with nbclient\n")
            log_stream.write(f"Timeout: {timeout}s\n")
            log_stream.write("-" * 50 + "\n")

            # Read notebook
            with open(notebook_path) as f:
                nb = nbformat.read(f, as_version=4)

            # Create client and execute
            client = NotebookClient(
                nb,
                timeout=timeout,
                kernel_name="python3",
                resources={"metadata": {"path": str(self.project_root)}},
            )

            # Execute
            client.execute()

            # Save executed notebook
            with open(output_path, "w") as f:
                nbformat.write(nb, f)

            log_stream.write("-" * 50 + "\n")
            log_stream.write("Execution completed successfully\n")
            return True, None

        except CellExecutionError as e:
            error_msg = f"Cell execution error: {e}"
            log_stream.write(f"\n{error_msg}\n")

            # Still save the partially executed notebook
            try:
                with open(output_path, "w") as f:
                    nbformat.write(nb, f)
            except:
                pass

            return False, error_msg

        except Exception as e:
            error_msg = f"nbclient error: {e}"
            log_stream.write(f"\n{error_msg}\n")
            log_stream.write(traceback.format_exc())
            return False, error_msg


class PipelineOrchestrator:
    """
    Orchestrates execution of the AML pipeline notebooks.

    This class wraps the existing pipeline without modifying it.
    It provides progress tracking, logging, and artifact collection.
    """

    def __init__(
        self,
        run_id: str,
        params: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, str, float], None]] = None,
        step_callback: Optional[Callable[[int, str, str, Optional[str]], None]] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            run_id: Unique identifier for this run
            params: Optional parameters to customize the run.
                    Recognised keys include *pipeline_name* (str, default "e2e-core"),
                    *dataset_mode* (str, default "demodata"), and
                    *sampling_profile* (str, default from dataset spec).
            progress_callback: Callback function(step, name, percent) for progress updates
            step_callback: Callback function(step, name, status, error) for step status updates
        """
        self.run_id = run_id
        self.params = params or {}
        self.progress_callback = progress_callback
        self.step_callback = step_callback

        # Extract run parameters first (needed to resolve artifact paths)
        self.project_root = get_repo_root()
        self._extract_params()

        # Resolve pipeline spec from registry
        pipeline_name = self.params.get("pipeline_name", "e2e-core")
        try:
            self.pipeline_spec: PipelineSpec = get_pipeline(pipeline_name)
        except KeyError:
            logger.warning(f"Unknown pipeline '{pipeline_name}', falling back to e2e-core")
            self.pipeline_spec = E2E_CORE

        # Resolve dataset spec from registry
        try:
            self.dataset_spec: DatasetSpec = get_dataset(self.dataset_mode)
        except KeyError:
            logger.warning(f"Unknown dataset '{self.dataset_mode}', using demodata defaults")
            self.dataset_spec = get_dataset("demodata")

        # Setup paths — always under artifacts/runs/<run_id>
        self.artifacts_dir = get_run_dir(run_id)

        self.data_dir = self.artifacts_dir / "data"
        self.prepared_data_dir = self.artifacts_dir / "prepared_data"
        self.models_dir = self.artifacts_dir / "models"
        self.plots_dir = self.artifacts_dir / "plots"
        self.report_dir = self.artifacts_dir / "report"
        self.logs_dir = self.artifacts_dir / "logs"
        self.notebooks_dir = self.artifacts_dir / "notebooks_executed"
        self.metrics_dir = self.artifacts_dir / "metrics"
        self.queues_dir = self.artifacts_dir / "queues"
        self.cases_dir = self.artifacts_dir / "cases"
        self.results_dir = self.artifacts_dir / "results"
        self.pipeline_dir = self.artifacts_dir / "pipeline"

        # Create artifact directories
        self._setup_artifact_dirs()

        # Resolve notebook steps via pipeline registry (conditional 00 based on dataset_mode)
        self.pipeline_steps = resolve_steps(
            self.pipeline_spec,
            dataset_mode=self.dataset_mode,
            project_root=self.project_root,
        )
        if not self.pipeline_steps:
            raise RuntimeError(
                f"Pipeline '{self.pipeline_spec.name}' resolved 0 steps — "
                f"check that e2e/ notebooks exist."
            )
        self.total_steps = len(self.pipeline_steps)

        # Resolve working directory for notebook execution
        if self.pipeline_spec.cwd_relative:
            self.notebook_cwd = self.project_root / self.pipeline_spec.cwd_relative
        else:
            self.notebook_cwd = self.project_root

        # Initialize notebook executor
        self.executor = NotebookExecutor(
            self.notebook_cwd,
            self.notebooks_dir,
            self.logs_dir,
        )

        # Write pipeline manifest
        env_vars = self._build_env_vars()
        write_manifest(
            self.artifacts_dir,
            self.pipeline_spec,
            self.pipeline_steps,
            self.params,
            env_vars,
        )

        # Results accumulator
        self.results = {
            "run_id": run_id,
            "pipeline_name": self.pipeline_spec.name,
            "dataset_mode": self.dataset_mode,
            "sampling_profile": self.sampling_profile,
            "max_rows": self.max_rows,
            "total_nodes": None,
            "total_transactions": None,
            "anomalies_detected": None,
            "steps_completed": 0,
            "steps_failed": 0,
            "step_results": {},
        }

        logger.info(f"Orchestrator initialized for run {run_id}")
        logger.info(f"Pipeline: {self.pipeline_spec.display_name} ({self.pipeline_spec.name})")
        logger.info(f"Dataset: {self.dataset_spec.display_name} (mode={self.dataset_mode})")
        logger.info(f"Sampling: {self.sampling_profile} (max_rows={self.max_rows})")
        logger.info(f"Project root: {self.project_root}")
        logger.info(f"Notebook CWD: {self.notebook_cwd}")
        logger.info(f"Artifacts dir: {self.artifacts_dir}")
        logger.info(f"Resolved {self.total_steps} pipeline steps")

    def _extract_params(self):
        """Extract and validate run parameters."""
        # Strip None values so profile defaults can apply
        self.params = {k: v for k, v in self.params.items() if v is not None}

        # Apply profile if specified
        profile = self.params.get("profile", "standard")
        if profile in RUN_PROFILES:
            profile_params = RUN_PROFILES[profile].copy()
            profile_params.pop("description", None)
            # Profile provides defaults, explicit params override
            for key, value in profile_params.items():
                if key not in self.params:
                    self.params[key] = value

        # Extract individual parameters with defaults
        self.sample_size = self.params.get("sample_size", 20000)
        self.epochs = self.params.get("epochs", 5)
        self.threshold = self.params.get("threshold", 0.99)
        self.notebook_timeout = self.params.get("notebook_timeout", DEFAULT_NOTEBOOK_TIMEOUT)
        self.skip_hp_tuning = self.params.get("skip_hyperparameter_tuning", True)
        self.generate_viz = self.params.get("generate_visualizations", True)
        self.generate_report = self.params.get("generate_report", True)

        # Dataset mode + sampling profile
        self.dataset_mode = self.params.get("dataset_mode", "demodata")
        self.sampling_profile = self.params.get("sampling_profile")
        self.dataset_root_override = self.params.get("dataset_root")

        # Resolve max_rows from sampling profile or explicit override
        max_rows_override = self.params.get("max_rows")
        if self.sampling_profile:
            self.max_rows = get_max_rows(self.sampling_profile, max_rows_override)
        elif max_rows_override:
            self.max_rows = max_rows_override
        else:
            # Use dataset spec's default sampling profile
            try:
                ds = get_dataset(self.dataset_mode)
                self.max_rows = get_max_rows(ds.default_sampling)
                self.sampling_profile = ds.default_sampling
            except KeyError:
                self.max_rows = None
                self.sampling_profile = "Full"

        # Resolve data_path from dataset_root override or registry
        self.data_path = self.dataset_root_override
        if not self.data_path:
            try:
                ds = get_dataset(self.dataset_mode)
                root_str = ds.dataset_root or "demodata"
                data_root = Path(root_str)
                if not data_root.is_absolute():
                    data_root = self.project_root / data_root
                self.data_path = str(data_root)
            except KeyError:
                if self.dataset_mode == "saml-d":
                    self.data_path = "/mnt/e/xx/demodata"
                else:
                    self.data_path = str(self.project_root / "demodata")

        logger.info(f"Run parameters: sample_size={self.sample_size}, epochs={self.epochs}, "
                    f"threshold={self.threshold}, timeout={self.notebook_timeout}s, "
                    f"dataset_mode={self.dataset_mode}, sampling={self.sampling_profile}, "
                    f"max_rows={self.max_rows}, data_path={self.data_path}")

    def _setup_artifact_dirs(self):
        """Create the artifact directory structure for this run."""
        dirs = [
            self.data_dir,
            self.prepared_data_dir,
            self.models_dir,
            self.plots_dir,
            self.report_dir,
            self.logs_dir,
            self.notebooks_dir,
            self.metrics_dir,
            self.queues_dir,
            self.cases_dir,
            self.results_dir,
            self.pipeline_dir,
        ]
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created artifact directories at {self.artifacts_dir}")

    def _update_progress(self, step: int, name: str, percent: float):
        """Update progress via callback if available."""
        percent = max(0.0, min(100.0, percent))
        if self.progress_callback:
            try:
                self.progress_callback(step, name, percent)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def _update_step_status(self, step: int, name: str, status: str, error: Optional[str] = None):
        """Update step status via callback if available."""
        if self.step_callback:
            try:
                self.step_callback(step, name, status, error)
            except Exception as e:
                logger.warning(f"Step callback failed: {e}")

    def _get_notebook_parameters(self) -> Dict[str, Any]:
        """
        Get parameters to inject into notebooks via papermill.

        Returns parameters that notebooks can optionally use.
        """
        return {
            "run_id": self.run_id,
            "artifacts_dir": str(self.artifacts_dir),
            "sample_size": self.sample_size,
            "epochs": self.epochs,
            "threshold": self.threshold,
            "data_path": self.data_path,
        }

    def _build_env_vars(self) -> Dict[str, str]:
        """
        Build the environment variables dict for e2e pipelines.

        These are set before each notebook execution (for non-papermill
        pipelines) and also recorded in the pipeline manifest.
        """
        env = {
            "AML_RUN_ID": self.run_id,
            "AML_RUN_DIR": str(self.artifacts_dir),
            "AML_PREPARED_DATA_DIR": str(self.prepared_data_dir),
            "AML_DATASET_MODE": self.dataset_mode,
            "AML_DATA_PATH": self.data_path,
            "AML_ARTIFACTS_DIR": str(self.artifacts_dir),
            "AML_SAMPLE_SIZE": str(self.sample_size),
            "AML_EPOCHS": str(self.epochs),
            "AML_THRESHOLD": str(self.threshold),
        }
        if self.max_rows is not None:
            env["AML_MAX_ROWS"] = str(self.max_rows)
        if self.sampling_profile:
            env["AML_SAMPLING_PROFILE"] = self.sampling_profile
        seed = self.params.get("seed")
        if seed is not None:
            env["AML_SEED"] = str(seed)
        return env

    def _execute_notebook(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single notebook step.

        Resolves the notebook path from the pipeline spec's notebook directory
        and injects parameters via papermill (legacy) or environment variables
        (e2e pipelines without papermill cells).

        Args:
            step: Step dictionary with notebook info

        Returns:
            dict with execution result
        """
        notebook_name = step["notebook"]
        step_num = step["number"]
        step_name = step["name"]

        # Resolve path: use the step's full path if available, else look in notebooks_dir
        if step.get("path") and Path(step["path"]).exists():
            notebook_path = Path(step["path"])
        else:
            nb_dir = self.project_root / self.pipeline_spec.notebooks_dir
            notebook_path = nb_dir / notebook_name
            if not notebook_path.exists():
                notebook_path = self.project_root / notebook_name

        if not notebook_path.exists():
            logger.warning(f"Notebook not found: {notebook_path}")
            return {
                "status": "skipped",
                "reason": "notebook_not_found",
                "notebook": notebook_name,
            }

        logger.info(f"Executing notebook: {notebook_name}")
        start_time = datetime.utcnow()

        # Get parameters for this notebook
        parameters = self._get_notebook_parameters()

        # For pipelines that don't support papermill, inject via env vars
        env_backup = {}
        if not self.pipeline_spec.supports_papermill:
            env_backup = self._set_env_parameters(parameters)
            parameters = {}  # don't pass to papermill

        try:
            # Execute notebook
            success, output_path, error = self.executor.execute(
                notebook_path,
                parameters,
                timeout=self.notebook_timeout,
            )
        finally:
            # Restore environment
            self._restore_env(env_backup)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        result = {
            "status": "completed" if success else "failed",
            "notebook": notebook_name,
            "output_path": output_path,
            "execution_time": duration,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
        }

        if error:
            result["error"] = error

        # Read log file for additional context
        log_path = self.logs_dir / f"{notebook_path.stem}.log"
        if log_path.exists():
            result["log_path"] = str(log_path)

        return result

    def _set_env_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        Set notebook parameters as environment variables.

        For e2e pipelines: sets AML_* env vars (run dir, data paths, etc.)
        For legacy pipelines: sets AML_PIPELINE_* env vars (papermill-style).

        Returns a dict of previous values for restoration.
        """
        backup: Dict[str, Optional[str]] = {}

        # Always set the AML_* env vars (e2e notebooks read these)
        for env_key, value in self._build_env_vars().items():
            backup[env_key] = os.environ.get(env_key)
            os.environ[env_key] = str(value)

        # Also set AML_PIPELINE_* for legacy compatibility
        for key, value in parameters.items():
            env_key = f"AML_PIPELINE_{key.upper()}"
            backup[env_key] = os.environ.get(env_key)
            os.environ[env_key] = str(value)

        return backup

    @staticmethod
    def _restore_env(backup: Dict[str, Optional[str]]) -> None:
        """Restore environment variables from backup."""
        for key, old_value in backup.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    def _collect_outputs(self):
        """
        Organize outputs within the artifact directory.

        Notebooks write outputs to artifacts_dir/{data,models,results,queues,cases}/
        via AML_RUN_DIR env var. This method:
        1. Moves PNGs from data/ to plots/
        2. Moves PNGs from results/ to plots/
        3. Falls back to sweeping e2e/results/ for any notebooks that wrote locally
        """
        logger.info("Collecting pipeline outputs...")

        collected_files = {"plots": [], "data": [], "models": [], "results": [], "queues": [], "cases": []}

        # Move PNGs from data_dir to plots_dir (notebooks write them to OUTPUT_PATH = data/)
        for img_file in self.data_dir.glob("*.png"):
            dest = self.plots_dir / img_file.name
            shutil.move(str(img_file), str(dest))
            collected_files["plots"].append(img_file.name)
            logger.debug(f"Moved plot to plots/: {img_file.name}")

        for img_file in self.data_dir.glob("*.jpg"):
            dest = self.plots_dir / img_file.name
            shutil.move(str(img_file), str(dest))
            collected_files["plots"].append(img_file.name)

        # Move PNGs from results/ to plots/
        results_dir = self.artifacts_dir / "results"
        if results_dir.exists():
            for img_file in results_dir.glob("*.png"):
                dest = self.plots_dir / img_file.name
                shutil.move(str(img_file), str(dest))
                collected_files["plots"].append(img_file.name)
                logger.debug(f"Moved plot from results/ to plots/: {img_file.name}")

        # Fallback: sweep e2e/results/ for notebooks that wrote locally
        local_results = self.notebook_cwd / "results"
        if local_results.exists() and local_results != results_dir:
            results_dir.mkdir(parents=True, exist_ok=True)
            cases_dir = self.artifacts_dir / "cases"
            cases_dir.mkdir(parents=True, exist_ok=True)

            # Copy results/ top-level files
            for f in local_results.iterdir():
                if f.is_file():
                    dest = results_dir / f.name if f.suffix != ".png" else self.plots_dir / f.name
                    if not dest.exists():
                        shutil.copy2(str(f), str(dest))
                        cat = "plots" if f.suffix == ".png" else "results"
                        collected_files[cat].append(f.name)
                        logger.debug(f"Copied from local results/: {f.name} -> {cat}/")

            # Copy results/queues/ -> queues/
            local_queues = local_results / "queues"
            if local_queues.exists():
                for f in local_queues.iterdir():
                    if f.is_file():
                        dest = self.queues_dir / f.name
                        if not dest.exists():
                            shutil.copy2(str(f), str(dest))
                            collected_files["queues"].append(f.name)
                            logger.debug(f"Copied from local results/queues/: {f.name}")

            # Copy results/cases/ -> cases/
            local_cases = local_results / "cases"
            if local_cases.exists():
                for f in local_cases.iterdir():
                    if f.is_file():
                        dest = cases_dir / f.name
                        if not dest.exists():
                            shutil.copy2(str(f), str(dest))
                            collected_files["cases"].append(f.name)
                            logger.debug(f"Copied from local results/cases/: {f.name}")

        # Count data files already in artifacts
        for data_file in self.data_dir.glob("*.parquet"):
            collected_files["data"].append(data_file.name)
        for data_file in self.data_dir.glob("*.csv"):
            collected_files["data"].append(data_file.name)
        for json_file in self.data_dir.glob("*.json"):
            collected_files["data"].append(json_file.name)

        # Count model artifacts already in artifacts
        for model_dir in self.models_dir.glob("gan_anomaly_*"):
            if model_dir.is_dir():
                collected_files["models"].append(model_dir.name)

        logger.info(f"Output collection complete: {len(collected_files['plots'])} plots, "
                    f"{len(collected_files['data'])} data files, {len(collected_files['models'])} models, "
                    f"{len(collected_files['results'])} results, "
                    f"{len(collected_files['queues'])} queue files, {len(collected_files['cases'])} case files")

        return collected_files

    def _parse_results(self) -> Dict[str, Any]:
        """
        Parse results from pipeline outputs to extract summary metrics.

        Only reads from the run's artifact directory — no local fallbacks.
        """
        results = {
            "total_nodes": None,
            "total_transactions": None,
            "anomalies_detected": None,
        }

        try:
            # Read node embeddings from artifact dir
            embeddings_file = self.data_dir / "node_embeddings_fg.parquet"

            if embeddings_file.exists():
                import pandas as pd
                df = pd.read_parquet(embeddings_file)
                results["total_nodes"] = len(df)

                # Count anomalies
                if "is_sar" in df.columns:
                    results["anomalies_detected"] = int(df["is_sar"].sum())
                elif "anomaly_score" in df.columns:
                    # Use threshold from model in artifact dir only
                    thresholds = list(self.models_dir.glob("*/threshold.npy"))

                    if thresholds:
                        import numpy as np
                        threshold = np.load(thresholds[0])
                        results["anomalies_detected"] = int((df["anomaly_score"] > threshold).sum())

            # Get transaction count from edges file in artifact dir
            edges_file = self.data_dir / "edges_td.csv"

            if edges_file.exists():
                import pandas as pd
                edges_df = pd.read_csv(edges_file)
                results["total_transactions"] = len(edges_df)

        except Exception as e:
            logger.warning(f"Failed to parse some results: {e}")

        return results

    def _build_metrics(self) -> Dict[str, Any]:
        """
        Build the metrics.json file with dashboard data contract.
        """
        from .metrics_builder import MetricsBuilder

        builder = MetricsBuilder(self.artifacts_dir, self.project_root)
        metrics = builder.build(self.results)

        # Save metrics
        metrics_path = self.metrics_dir / "metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)

        logger.info(f"Metrics saved to {metrics_path}")
        return metrics

    def _build_artifact_index(self):
        """
        Build the artifact index for dynamic UI.
        """
        from .artifacts_index import ArtifactIndexer

        indexer = ArtifactIndexer(self.artifacts_dir)
        index = indexer.build_index()

        logger.info(f"Artifact index built: {index['summary']}")
        return index

    def _style_plots(self) -> int:
        """
        Apply Bloomberg-terminal styling to generated plots.

        Creates styled versions in plots/styled/ directory.

        Returns:
            Number of styled plots created
        """
        try:
            styled_files = style_pngs(self.run_id, theme="bloomberg")
            logger.info(f"Created {len(styled_files)} styled plots")
            return len(styled_files)
        except Exception as e:
            logger.warning(f"Failed to style plots: {e}")
            return 0

    def run(self) -> Dict[str, Any]:
        """
        Execute the full pipeline.

        Returns:
            dict with run results including metrics and artifact paths
        """
        logger.info(f"Starting pipeline execution for run {self.run_id}")
        start_time = datetime.utcnow()
        self.results["started_at"] = start_time.isoformat()

        completed_steps = 0
        failed_steps = 0

        try:
            # ── Pre-pipeline: dataset ingestion (SAML-D DuckDB) ──
            if self.dataset_spec.requires_ingest:
                self._update_progress(0, "Ingesting dataset via DuckDB", 1)
                try:
                    from ..datasets.saml_d_ingest import prepare_dataset

                    ingest_result = prepare_dataset(
                        data_root=Path(self.data_path),
                        prepared_dir=self.prepared_data_dir,
                        max_rows=self.max_rows,
                        cache_root=Path(self.dataset_spec.cache_root) if self.dataset_spec.cache_root else None,
                    )
                    self.results["ingest"] = ingest_result
                    logger.info(f"Dataset ingestion complete: {ingest_result}")
                except Exception as e:
                    logger.error(f"Dataset ingestion failed: {e}")
                    raise RuntimeError(f"Dataset ingestion failed: {e}") from e

            for step in self.pipeline_steps:
                step_num = step["number"]
                step_name = step["name"]
                notebook = step["notebook"]
                is_optional = step.get("optional", False)

                # Skip HP tuning steps if configured
                if is_optional and self.skip_hp_tuning and ("maggy" in notebook.lower() or "hp" in step_name.lower()):
                    logger.info(f"Skipping optional step {step_num}: {step_name}")
                    self._update_progress(step_num, f"{step_name} (skipped)", (step_num / self.total_steps) * 90)
                    self._update_step_status(step_num, step_name, "skipped")
                    self.results["step_results"][step_num] = {"status": "skipped", "reason": "optional_disabled"}
                    completed_steps += 1
                    continue

                # Skip visualization/dashboard steps (06+) if not requested
                if step_num >= 6 and not self.generate_viz:
                    logger.info(f"Skipping visualization step {step_num}: {step_name}")
                    self._update_progress(step_num, f"{step_name} (skipped)", (step_num / self.total_steps) * 90)
                    self._update_step_status(step_num, step_name, "skipped")
                    self.results["step_results"][step_num] = {"status": "skipped", "reason": "visualization_disabled"}
                    completed_steps += 1
                    continue

                # Update progress to "running"
                self._update_progress(step_num, f"Running: {step_name}", ((step_num - 0.5) / self.total_steps) * 90)
                self._update_step_status(step_num, step_name, "running")

                # Execute the step
                step_result = self._execute_notebook(step)
                self.results["step_results"][step_num] = step_result

                if step_result.get("status") == "failed":
                    failed_steps += 1
                    self._update_step_status(step_num, step_name, "failed", step_result.get("error"))

                    # For non-optional steps, this is a fatal error
                    if not is_optional:
                        error_msg = f"Step {step_num} ({step_name}) failed: {step_result.get('error')}"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    else:
                        logger.warning(f"Optional step {step_num} failed, continuing...")
                else:
                    completed_steps += 1
                    self._update_step_status(step_num, step_name, "completed")

                # Update progress to "completed" – cap at 90% so the
                # remaining 10% is reserved for post-processing; tasks.py
                # sets 100% atomically together with status=COMPLETED.
                progress_pct = (step_num / self.total_steps) * 90
                self._update_progress(step_num, step_name, progress_pct)

                logger.info(f"Completed step {step_num}/{self.total_steps}: {step_name}")

            # -- Post-processing phase (90 → 99%) --
            self._update_progress(self.total_steps, "Finalizing: collecting outputs", 91)

            # Collect outputs from the pipeline
            self._collect_outputs()

            # Apply Bloomberg-terminal styling to plots
            try:
                styled_count = self._style_plots()
                self.results["styled_plots_count"] = styled_count
            except Exception as e:
                logger.warning(f"Failed to style plots: {e}")
                self.results["styled_plots_count"] = 0

            self._update_progress(self.total_steps, "Finalizing: parsing results", 93)

            # Parse results
            parsed_results = self._parse_results()
            self.results.update(parsed_results)
            self.results["steps_completed"] = completed_steps
            self.results["steps_failed"] = failed_steps

            self._update_progress(self.total_steps, "Finalizing: building metrics", 95)

            # Build metrics for dashboard
            try:
                self._build_metrics()
            except Exception as e:
                logger.warning(f"Failed to build metrics: {e}")

            # Build artifact index (includes styled plots category)
            try:
                self._build_artifact_index()
            except Exception as e:
                logger.warning(f"Failed to build artifact index: {e}")

            self._update_progress(self.total_steps, "Finalizing: building risk queue", 97)

            # Build risk queue (skip if NB10 already produced it)
            queue_exists = (self.queues_dir / "risk_queue.parquet").exists()
            if queue_exists:
                logger.info("Risk queue already exists (from NB10), skipping build_risk_queue()")
            else:
                try:
                    from .risk_ranking import build_risk_queue
                    queue_summary = build_risk_queue(self.artifacts_dir)
                    self.results["risk_queue"] = queue_summary
                    logger.info(f"Risk queue built: {queue_summary.get('total_entities', 0)} entities")
                except Exception as e:
                    logger.warning(f"Failed to build risk queue: {e}")

            # Build investigation cases (skip if NB10 already produced them)
            cases_dir = self.artifacts_dir / "cases"
            cases_exist = (cases_dir / "case_index.parquet").exists()
            if cases_exist:
                logger.info("Cases already exist (from NB10), skipping build_cases()")
            else:
                try:
                    from .case_builder import build_cases
                    case_summary = build_cases(self.artifacts_dir)
                    self.results["cases"] = case_summary
                    logger.info(f"Cases built: {case_summary.get('total_cases', 0)} cases")
                except Exception as e:
                    logger.warning(f"Failed to build cases: {e}")

            # Rebuild artifact index to pick up all files (queues/, cases/)
            try:
                self._build_artifact_index()
            except Exception:
                pass

            self._update_progress(self.total_steps, "Finalizing: generating report", 99)

            # Generate report if requested
            if self.generate_report:
                self._generate_report()

            end_time = datetime.utcnow()
            self.results["completed_at"] = end_time.isoformat()
            self.results["execution_time_seconds"] = (end_time - start_time).total_seconds()

            logger.info(f"Pipeline execution completed for run {self.run_id}")
            return self.results

        except Exception as e:
            logger.error(f"Pipeline execution failed for run {self.run_id}: {e}")
            self.results["error"] = str(e)
            self.results["error_traceback"] = traceback.format_exc()
            self.results["steps_completed"] = completed_steps
            self.results["steps_failed"] = failed_steps

            # Still try to collect partial outputs and build index
            try:
                self._collect_outputs()
                self._build_artifact_index()
            except:
                pass

            raise

    def _generate_report(self):
        """
        Generate the HTML report for this run.
        """
        from ..reports.generator import ReportGenerator

        try:
            generator = ReportGenerator(
                run_id=self.run_id,
                results=self.results,
                artifacts_dir=self.artifacts_dir,
            )
            generator.generate()
            logger.info(f"Report generated for run {self.run_id}")
        except Exception as e:
            logger.error(f"Failed to generate report for run {self.run_id}: {e}")

    def cleanup(self):
        """
        Cleanup resources: kill orphan notebook kernels and free GPU memory.

        Called from the Celery task's ``finally`` block so it runs on
        success, failure, cancellation, and timeout.
        """
        # 1. Kill any notebook kernel subprocesses spawned by this worker
        self._kill_child_processes()

        # 2. Free GPU memory
        self._cleanup_gpu()

    # ------------------------------------------------------------------
    # Internal helpers for cleanup
    # ------------------------------------------------------------------

    def _kill_child_processes(self):
        """Kill all child processes of the current worker (orphan kernels)."""
        import signal

        try:
            import psutil
        except ImportError:
            # psutil not available — fall back to os-level cleanup
            logger.warning("psutil not installed; skipping child-process cleanup")
            return

        try:
            current = psutil.Process()
            children = current.children(recursive=True)
            if not children:
                return

            logger.info(f"Killing {len(children)} orphan child process(es)")
            for child in children:
                try:
                    child.send_signal(signal.SIGTERM)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Give them 3 s to exit, then SIGKILL survivors
            _, alive = psutil.wait_procs(children, timeout=3)
            for child in alive:
                try:
                    child.kill()
                    logger.info(f"Force-killed child PID {child.pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        except Exception as e:
            logger.warning(f"Child-process cleanup error: {e}")

    @staticmethod
    def _cleanup_gpu():
        """Release GPU memory held by the current process."""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("GPU cache cleared (torch.cuda.empty_cache)")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"GPU cleanup error: {e}")

        try:
            import gc
            gc.collect()
        except Exception:
            pass
