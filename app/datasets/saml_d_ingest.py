"""
SAML-D Ingestion via DuckDB

Handles out-of-core reading of the 9.5M-row SAML-D CSV files,
with optional row-limit sampling and Linux-side parquet caching.

Output goes to ``prepared_data/`` inside the run's artifact directory
so that notebooks can read from a single known location.

Usage (called by orchestrator before notebook execution):

    from app.datasets.saml_d_ingest import prepare_dataset

    result = prepare_dataset(
        data_root=Path("/mnt/e/xx/demodata"),
        prepared_dir=Path("artifacts/runs/<run_id>/prepared_data"),
        max_rows=200_000,
        cache_root=Path("/tmp/aml-saml-d-cache"),
    )
"""

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# DuckDB memory guardrail
_DUCKDB_MEMORY_LIMIT = "2GB"
_DUCKDB_THREADS = 4


def prepare_dataset(
    data_root: Path,
    prepared_dir: Path,
    max_rows: Optional[int] = None,
    cache_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Read CSVs via DuckDB, optionally sample, and write parquet files
    to *prepared_dir* for downstream notebooks.

    If *cache_root* is provided, parquet files are cached keyed by a
    fingerprint of (file sizes + mtimes + max_rows).  Subsequent runs
    with identical config skip DuckDB and copy from cache.

    Returns dict with: party_rows, txn_rows, alert_rows, cached, elapsed_s
    """
    import duckdb
    from .dataset_registry import compute_cache_key

    data_root = Path(data_root)
    prepared_dir = Path(prepared_dir)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "source": str(data_root),
        "party_rows": 0,
        "txn_rows": 0,
        "alert_rows": 0,
        "max_rows": max_rows,
        "cached": False,
        "elapsed_s": 0.0,
    }

    t0 = time.time()

    # ── Cache check ──────────────────────────────────────────────────
    cache_key = compute_cache_key(data_root, max_rows)
    cache_path = Path(cache_root) / cache_key if cache_root else None

    if cache_path and cache_path.exists():
        cached_files = list(cache_path.glob("*.parquet"))
        if len(cached_files) >= 2:  # party + transactions minimum
            logger.info(f"Cache hit: {cache_path} ({len(cached_files)} files)")
            for f in cached_files:
                shutil.copy2(str(f), str(prepared_dir / f.name))
            result["cached"] = True
            result.update(_count_parquet_rows(prepared_dir))
            result["elapsed_s"] = round(time.time() - t0, 2)
            _write_meta(prepared_dir, result)
            return result

    # ── DuckDB out-of-core ingestion ─────────────────────────────────
    logger.info(f"DuckDB ingestion from {data_root} (max_rows={max_rows})")

    con = duckdb.connect(database=":memory:")
    con.execute(f"SET memory_limit = '{_DUCKDB_MEMORY_LIMIT}'")
    con.execute(f"SET threads TO {_DUCKDB_THREADS}")

    try:
        # ── party.csv (always fully loaded) ──
        party_csv = data_root / "party.csv"
        party_out = prepared_dir / "party.parquet"
        if party_csv.exists():
            con.execute(f"""
                COPY (SELECT * FROM read_csv_auto('{party_csv}'))
                TO '{party_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """)
            result["party_rows"] = _count(con, party_out)
            logger.info(f"  party.parquet: {result['party_rows']:,} rows")

        # ── transactions.csv (optionally row-limited) ──
        txn_csv = data_root / "transactions.csv"
        txn_out = prepared_dir / "transactions.parquet"
        if txn_csv.exists():
            if max_rows and max_rows > 0:
                con.execute(f"""
                    COPY (
                        SELECT * FROM read_csv_auto('{txn_csv}')
                        USING SAMPLE {max_rows} ROWS
                    )
                    TO '{txn_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """)
            else:
                con.execute(f"""
                    COPY (SELECT * FROM read_csv_auto('{txn_csv}'))
                    TO '{txn_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """)
            result["txn_rows"] = _count(con, txn_out)
            logger.info(f"  transactions.parquet: {result['txn_rows']:,} rows")

        # ── alert_transactions.csv (small) ──
        alert_csv = data_root / "alert_transactions.csv"
        alert_out = prepared_dir / "alert_transactions.parquet"
        if alert_csv.exists():
            con.execute(f"""
                COPY (SELECT * FROM read_csv_auto('{alert_csv}'))
                TO '{alert_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """)
            result["alert_rows"] = _count(con, alert_out)
            logger.info(f"  alert_transactions.parquet: {result['alert_rows']:,} rows")
    finally:
        con.close()

    # ── Populate cache ───────────────────────────────────────────────
    if cache_path:
        cache_path.mkdir(parents=True, exist_ok=True)
        for pq in prepared_dir.glob("*.parquet"):
            shutil.copy2(str(pq), str(cache_path / pq.name))
        logger.info(f"Cached parquet files to {cache_path}")

    result["elapsed_s"] = round(time.time() - t0, 2)
    _write_meta(prepared_dir, result)
    logger.info(f"SAML-D ingestion complete in {result['elapsed_s']}s")
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count(con, parquet_path: Path) -> int:
    return con.execute(
        f"SELECT count(*) FROM read_parquet('{parquet_path}')"
    ).fetchone()[0]


def _count_parquet_rows(prepared_dir: Path) -> Dict[str, int]:
    """Count rows from cached parquet files without heavy memory use."""
    import duckdb

    counts: Dict[str, int] = {}
    con = duckdb.connect(database=":memory:")
    try:
        for key, fname in [
            ("party_rows", "party.parquet"),
            ("txn_rows", "transactions.parquet"),
            ("alert_rows", "alert_transactions.parquet"),
        ]:
            fp = prepared_dir / fname
            counts[key] = _count(con, fp) if fp.exists() else 0
    finally:
        con.close()
    return counts


def _write_meta(prepared_dir: Path, result: Dict[str, Any]) -> None:
    """Write prepared_dataset_meta.json alongside the parquet files."""
    meta = {
        "source": result.get("source", ""),
        "party_rows": result.get("party_rows", 0),
        "txn_rows": result.get("txn_rows", 0),
        "alert_rows": result.get("alert_rows", 0),
        "max_rows": result.get("max_rows"),
        "cached": result.get("cached", False),
        "ingest_elapsed_s": result.get("elapsed_s", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = prepared_dir / "prepared_dataset_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Prepared dataset meta written to {meta_path}")


# ---------------------------------------------------------------------------
# Server-side pagination (used by /table API endpoint)
# ---------------------------------------------------------------------------

def query_large_table(
    parquet_path: Path,
    offset: int = 0,
    limit: int = 200,
    columns: Optional[str] = None,
    where: Optional[str] = None,
    order_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    DuckDB-based pagination for large parquet tables.

    Safe for 9.5M-row files — never loads full table into memory.

    Args:
        parquet_path: Path to the parquet file
        offset: Skip first N rows
        limit: Max rows to return (capped at 2000)
        columns: Comma-separated column names (None = all)
        where: SQL WHERE clause (no WHERE keyword)
        order_by: SQL ORDER BY clause (no ORDER BY keyword)

    Returns:
        {"total": int, "rows": list[dict], "limit": int, "offset": int}
    """
    import duckdb

    limit = min(limit, 2000)  # hard cap

    con = duckdb.connect(database=":memory:")
    con.execute("SET memory_limit = '512MB'")

    try:
        base = f"read_parquet('{parquet_path}')"
        col_clause = columns if columns else "*"
        where_clause = f"WHERE {where}" if where else ""
        order_clause = f"ORDER BY {order_by}" if order_by else ""

        total = con.execute(
            f"SELECT count(*) FROM {base} {where_clause}"
        ).fetchone()[0]

        rows_df = con.execute(f"""
            SELECT {col_clause} FROM {base}
            {where_clause}
            {order_clause}
            LIMIT {limit} OFFSET {offset}
        """).fetchdf()

        return {
            "total": total,
            "rows": rows_df.to_dict(orient="records"),
            "limit": limit,
            "offset": offset,
        }
    finally:
        con.close()
