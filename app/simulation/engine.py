"""
Standalone AML real-time simulation engine.

Runs GraphSAGE + WGAN-GP anomaly scoring on a live transaction stream
in a background thread.  Thread-safe state is polled by the API layer.

Extracted from e2e/11_realtime_simulator.ipynb and
e2e/12_simulation_dashboard.ipynb.
"""

import os
import sys
import gc
import json
import time
import uuid
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque, defaultdict
from copy import deepcopy
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv

# Import gan_anomaly from e2e/
_e2e_dir = str(Path(__file__).resolve().parent.parent.parent / "e2e")
if _e2e_dir not in sys.path:
    sys.path.insert(0, _e2e_dir)
from gan_anomaly import Generator, Encoder, anomaly_score

from ..utils.paths import get_repo_root, get_run_dir

logger = logging.getLogger(__name__)

# ─── Transaction generation constants (same as NB 11) ────────────
AMOUNT_MU = 6.2
AMOUNT_SIGMA = 0.4
AMOUNT_MIN = 40.0
AMOUNT_MAX = 3_000.0
TX_TYPES = [
    "TRANSFER-Mutual", "TRANSFER-FanOut", "TRANSFER-Forward",
    "TRANSFER-Periodical", "TRANSFER-FanIn",
]
TX_PROBS = np.array([0.31, 0.26, 0.22, 0.19, 0.02])
TX_PROBS /= TX_PROBS.sum()

FAN_MIN_LEGS = 4
FAN_MAX_LEGS = 8
PATTERN_AMT_MIN = 500
PATTERN_AMT_MAX = 3_000
STRUCTURING_NUM_TXNS = 8
STRUCTURING_AMT_MIN = 7_000
STRUCTURING_AMT_MAX = 9_500


# ═══════════════════════════════════════════════════════════
#  GraphSAGE (from NB 02/11)
# ═══════════════════════════════════════════════════════════

class GraphSAGE(nn.Module):
    def __init__(self, in_channels=9, hidden_channels=128, out_channels=64, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)
        self.dropout = dropout

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.conv2(x, edge_index)
        return x

    @torch.no_grad()
    def full_forward(self, x, edge_index):
        self.eval()
        return self.forward(x, edge_index)


# ═══════════════════════════════════════════════════════════
#  TransactionStream (from NB 11)
# ═══════════════════════════════════════════════════════════

class TransactionStream:
    """Simulates a live transaction feed with optional laundering patterns."""

    PATTERN_TYPES = ["fan_out", "fan_in", "cycle", "scatter_gather", "structuring"]

    def __init__(self, party_ids, rng, pattern_prob=0.10):
        self.party_ids = list(party_ids)
        self.n_parties = len(self.party_ids)
        self.rng = rng
        self.pattern_prob = pattern_prob
        self.tran_counter = 1_000_000
        self.alert_counter = 500
        self.base_time = datetime.now()
        self.batch_num = 0
        self.total_patterns_injected = 0

    def _pick(self, n, exclude=None):
        pool = self.party_ids if exclude is None else [p for p in self.party_ids if p not in exclude]
        return self.rng.choice(pool, size=min(n, len(pool)), replace=False).tolist()

    def _ts(self):
        offset = timedelta(seconds=self.batch_num * 30 + int(self.rng.integers(0, 30)))
        return (self.base_time + offset).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def _amt(self, low=PATTERN_AMT_MIN, high=PATTERN_AMT_MAX):
        return round(float(self.rng.uniform(low, high)), 2)

    def _next_id(self):
        self.tran_counter += 1
        return self.tran_counter

    def _make_normal_txns(self, n):
        src_idx = self.rng.zipf(a=1.5, size=n) % self.n_parties
        dst_idx = self.rng.zipf(a=1.3, size=n) % self.n_parties
        self_loops = src_idx == dst_idx
        dst_idx[self_loops] = (dst_idx[self_loops] + 1) % self.n_parties
        amounts = self.rng.lognormal(AMOUNT_MU, AMOUNT_SIGMA, size=n)
        amounts = np.clip(amounts, AMOUNT_MIN, AMOUNT_MAX).round(2)
        tx_types = self.rng.choice(TX_TYPES, size=n, p=TX_PROBS)
        txns = []
        for i in range(n):
            txns.append({
                "tran_id": self._next_id(), "tx_type": tx_types[i],
                "base_amt": float(amounts[i]), "tran_timestamp": self._ts(),
                "src": self.party_ids[src_idx[i]], "dst": self.party_ids[dst_idx[i]],
                "_is_pattern": False, "_alert_type": None, "_alert_id": None,
            })
        return txns

    def _inject_fan_out(self):
        n_legs = int(self.rng.integers(FAN_MIN_LEGS, FAN_MAX_LEGS + 1))
        parties = self._pick(1 + n_legs)
        sender, receivers = parties[0], parties[1:]
        aid = self.alert_counter; self.alert_counter += 1
        return [{
            "tran_id": self._next_id(), "tx_type": "TRANSFER-FanOut",
            "base_amt": self._amt(), "tran_timestamp": self._ts(),
            "src": sender, "dst": recv,
            "_is_pattern": True, "_alert_type": "fan_out", "_alert_id": aid,
        } for recv in receivers]

    def _inject_fan_in(self):
        n_legs = int(self.rng.integers(FAN_MIN_LEGS, FAN_MAX_LEGS + 1))
        parties = self._pick(1 + n_legs)
        receiver, senders = parties[0], parties[1:]
        aid = self.alert_counter; self.alert_counter += 1
        return [{
            "tran_id": self._next_id(), "tx_type": "TRANSFER-FanIn",
            "base_amt": self._amt(), "tran_timestamp": self._ts(),
            "src": s, "dst": receiver,
            "_is_pattern": True, "_alert_type": "fan_in", "_alert_id": aid,
        } for s in senders]

    def _inject_cycle(self):
        a, b, c = self._pick(3)
        aid = self.alert_counter; self.alert_counter += 1
        base = self._amt()
        return [{
            "tran_id": self._next_id(), "tx_type": "TRANSFER-Forward",
            "base_amt": round(base * float(self.rng.uniform(0.90, 1.10)), 2),
            "tran_timestamp": self._ts(), "src": s, "dst": d,
            "_is_pattern": True, "_alert_type": "cycle", "_alert_id": aid,
        } for s, d in [(a, b), (b, c), (c, a)]]

    def _inject_scatter_gather(self):
        n_mids = 4
        parties = self._pick(2 + n_mids)
        source, collector = parties[0], parties[1]
        mids = parties[2:]
        aid = self.alert_counter; self.alert_counter += 1
        txns = []
        for mid in mids:
            amt = self._amt()
            txns.append({
                "tran_id": self._next_id(), "tx_type": "TRANSFER-FanOut",
                "base_amt": amt, "tran_timestamp": self._ts(),
                "src": source, "dst": mid,
                "_is_pattern": True, "_alert_type": "scatter_gather", "_alert_id": aid,
            })
            txns.append({
                "tran_id": self._next_id(), "tx_type": "TRANSFER-FanIn",
                "base_amt": round(amt * float(self.rng.uniform(0.90, 0.95)), 2),
                "tran_timestamp": self._ts(), "src": mid, "dst": collector,
                "_is_pattern": True, "_alert_type": "scatter_gather", "_alert_id": aid,
            })
        return txns

    def _inject_structuring(self):
        parties = self._pick(2)
        sender, recv = parties[0], parties[1]
        aid = self.alert_counter; self.alert_counter += 1
        return [{
            "tran_id": self._next_id(), "tx_type": "TRANSFER-Periodical",
            "base_amt": self._amt(STRUCTURING_AMT_MIN, STRUCTURING_AMT_MAX),
            "tran_timestamp": self._ts(), "src": sender, "dst": recv,
            "_is_pattern": True, "_alert_type": "structuring", "_alert_id": aid,
        } for _ in range(STRUCTURING_NUM_TXNS)]

    def next_batch(self, size=50):
        self.batch_num += 1
        txns = self._make_normal_txns(size)
        if self.rng.random() < self.pattern_prob:
            ptype = self.rng.choice(self.PATTERN_TYPES)
            injector = {
                "fan_out": self._inject_fan_out, "fan_in": self._inject_fan_in,
                "cycle": self._inject_cycle, "scatter_gather": self._inject_scatter_gather,
                "structuring": self._inject_structuring,
            }[ptype]
            txns.extend(injector())
            self.total_patterns_injected += 1
        return txns


# ═══════════════════════════════════════════════════════════
#  LiveGraph (from NB 11)
# ═══════════════════════════════════════════════════════════

class LiveGraph:
    """Maintains graph state with O(k) incremental updates per batch."""

    def __init__(self, data_dir: str):
        nf = pd.read_parquet(os.path.join(data_dir, "node_features.parquet"))
        edges_df = pd.read_parquet(os.path.join(data_dir, "edges.parquet"))

        self.node_ids = list(nf["id"].values)
        self.node_to_idx = {nid: i for i, nid in enumerate(self.node_ids)}
        self.n_nodes = len(self.node_ids)

        self.node_type = {}
        self.out_degree = defaultdict(int)
        self.in_degree = defaultdict(int)
        self.total_sent = defaultdict(float)
        self.total_received = defaultdict(float)
        self.counterparties_sent = defaultdict(set)
        self.counterparties_received = defaultdict(set)

        for _, row in nf.iterrows():
            nid = row["id"]
            self.node_type[nid] = int(row["type"])
            self.out_degree[nid] = int(row["out_degree"])
            self.in_degree[nid] = int(row["in_degree"])
            self.total_sent[nid] = float(row["total_amount_sent"])
            self.total_received[nid] = float(row["total_amount_received"])
            self.counterparties_sent[nid] = set(range(int(row["unique_counterparties_sent"])))
            self.counterparties_received[nid] = set(range(int(row["unique_counterparties_received"])))

        self.edges = set()
        for _, row in edges_df.iterrows():
            src_idx = self.node_to_idx.get(row["source"])
            dst_idx = self.node_to_idx.get(row["target"])
            if src_idx is not None and dst_idx is not None:
                self.edges.add((src_idx, dst_idx))

        self.is_sar = {row["id"]: int(row.get("is_sar", 0)) for _, row in nf.iterrows()}
        self.total_txns_processed = 0
        self.pattern_nodes = set()

    def update(self, txn_batch):
        affected = set()
        for txn in txn_batch:
            src, dst, amt = txn["src"], txn["dst"], txn["base_amt"]
            for nid in (src, dst):
                if nid not in self.node_to_idx:
                    idx = self.n_nodes
                    self.node_to_idx[nid] = idx
                    self.node_ids.append(nid)
                    self.n_nodes += 1
                    self.node_type[nid] = 0
            src_idx = self.node_to_idx[src]
            dst_idx = self.node_to_idx[dst]
            self.out_degree[src] += 1
            self.in_degree[dst] += 1
            self.total_sent[src] += amt
            self.total_received[dst] += amt
            self.counterparties_sent[src].add(dst_idx)
            self.counterparties_received[dst].add(src_idx)
            self.edges.add((src_idx, dst_idx))
            affected.add(src_idx)
            affected.add(dst_idx)
            if txn.get("_is_pattern"):
                self.pattern_nodes.add(src)
                self.pattern_nodes.add(dst)
                self.is_sar[src] = 1
                self.is_sar[dst] = 1
        self.total_txns_processed += len(txn_batch)
        return affected

    def get_feature_matrix(self):
        features = np.zeros((self.n_nodes, 9), dtype=np.float32)
        for i, nid in enumerate(self.node_ids):
            od = self.out_degree[nid]
            ind = self.in_degree[nid]
            ts = self.total_sent[nid]
            tr = self.total_received[nid]
            features[i, 0] = self.node_type.get(nid, 0)
            features[i, 1] = ind
            features[i, 2] = od
            features[i, 3] = ts
            features[i, 4] = tr
            features[i, 5] = (ts / od) if od > 0 else 0.0
            features[i, 6] = (tr / ind) if ind > 0 else 0.0
            features[i, 7] = len(self.counterparties_sent[nid])
            features[i, 8] = len(self.counterparties_received[nid])
        return torch.tensor(features, dtype=torch.float32)

    def get_edge_index(self):
        if not self.edges:
            return torch.zeros((2, 0), dtype=torch.long)
        src_list, dst_list = zip(*self.edges)
        return torch.tensor([list(src_list), list(dst_list)], dtype=torch.long)

    def get_sar_labels(self):
        return np.array([self.is_sar.get(nid, 0) for nid in self.node_ids])


# ═══════════════════════════════════════════════════════════
#  RealtimeScorer (from NB 12)
# ═══════════════════════════════════════════════════════════

class RealtimeScorer:
    """Scores nodes using pre-trained GraphSAGE + WGAN-GP."""

    def __init__(self, device, models_dir: str, threshold_pct=99, rescore_interval=3):
        self.device = device
        self.rescore_interval = rescore_interval

        with open(os.path.join(models_dir, "training_meta.json")) as f:
            self.meta = json.load(f)

        self.sage = GraphSAGE(9, 128, 64, dropout=0.3).to(device)
        self.sage.load_state_dict(torch.load(
            os.path.join(models_dir, "graphsage.pt"), map_location=device, weights_only=True))
        self.sage.eval()

        m = self.meta
        self.encoder = Encoder(m["input_dim"], m["latent_dim"], m["e_hidden"],
                               m["n_layers"], m["activation"]).to(device)
        self.generator = Generator(m["latent_dim"], m["input_dim"], m["g_hidden"],
                                   m["n_layers"], m["activation"]).to(device)
        self.encoder.load_state_dict(torch.load(
            os.path.join(models_dir, "encoder.pt"), map_location=device, weights_only=True))
        self.generator.load_state_dict(torch.load(
            os.path.join(models_dir, "generator.pt"), map_location=device, weights_only=True))
        self.encoder.eval()
        self.generator.eval()

        norm = torch.load(os.path.join(models_dir, "feature_norm.pt"),
                          map_location=device, weights_only=True)
        self.x_mean = norm["mean"].to(device)
        self.x_std = norm["std"].to(device)

        X_train = np.load(os.path.join(models_dir, "X_train.npy"))
        train_tensor = torch.tensor(X_train, dtype=torch.float32).to(device)
        train_scores = anomaly_score(train_tensor, self.encoder, self.generator).cpu().numpy()
        self.threshold = float(np.percentile(train_scores, threshold_pct))
        del train_tensor, train_scores
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.all_scores = None
        self.all_embeddings = None
        self.alerts = deque(maxlen=200)
        self.score_history = deque(maxlen=200)
        self.latency_history = []
        self.total_alerts = 0
        self.total_scored = 0

    def score(self, graph, affected_indices, batch_num, txn_batch):
        t0 = time.perf_counter()
        should_rescore = (batch_num % self.rescore_interval == 0) or (self.all_scores is None)

        if should_rescore:
            x = graph.get_feature_matrix().to(self.device)
            edge_index = graph.get_edge_index().to(self.device)
            x_norm = (x - self.x_mean) / self.x_std
            embeddings = self.sage.full_forward(x_norm, edge_index)
            self.all_embeddings = embeddings.cpu()
            scores = anomaly_score(embeddings, self.encoder, self.generator)
            self.all_scores = scores.cpu().numpy()
            del x, edge_index, x_norm, embeddings, scores
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        latency_ms = (time.perf_counter() - t0) * 1000
        self.latency_history.append(latency_ms)

        affected_list = sorted(affected_indices)
        batch_alerts = []

        if self.all_scores is not None:
            for idx in affected_list:
                if idx < len(self.all_scores):
                    score_val = float(self.all_scores[idx])
                    node_id = graph.node_ids[idx]
                    if score_val > self.threshold:
                        alert = {
                            "batch": batch_num, "node_id": node_id,
                            "score": score_val,
                            "is_sar": graph.is_sar.get(node_id, 0),
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                        self.alerts.append(alert)
                        batch_alerts.append(alert)
                        self.total_alerts += 1

            self.total_scored += len(affected_list)
            affected_scores = [self.all_scores[i] for i in affected_list if i < len(self.all_scores)]
            if affected_scores:
                self.score_history.append((
                    batch_num, float(np.mean(affected_scores)),
                    float(np.max(affected_scores)), len(batch_alerts),
                ))

        return {
            "batch_num": batch_num, "affected_count": len(affected_list),
            "alerts": batch_alerts, "latency_ms": latency_ms, "rescored": should_rescore,
        }


# ═══════════════════════════════════════════════════════════
#  SimulationState — thread-safe (from NB 12)
# ═══════════════════════════════════════════════════════════

class SimulationState:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = self._initial_state()

    @staticmethod
    def _initial_state():
        return {
            "status": "idle",
            "batch_num": 0,
            "total_batches": 0,
            "total_txns": 0,
            "total_alerts": 0,
            "total_patterns": 0,
            "pattern_nodes": 0,
            "score_history": [],
            "recent_alerts": [],
            "all_scores": None,
            "sar_labels": None,
            "threshold": 0.0,
            "latency_history": [],
            "confusion": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
            "elapsed": 0.0,
            "last_batch_info": "",
            "error": None,
        }

    def get(self) -> dict:
        with self._lock:
            snap = {}
            for k, v in self._state.items():
                if isinstance(v, np.ndarray):
                    snap[k] = v.tolist()
                elif isinstance(v, (list, dict)):
                    snap[k] = deepcopy(v)
                else:
                    snap[k] = v
            return snap

    def update(self, **kwargs):
        with self._lock:
            self._state.update(kwargs)

    def reset(self):
        with self._lock:
            self._state = self._initial_state()


# ═══════════════════════════════════════════════════════════
#  SimulationConfig
# ═══════════════════════════════════════════════════════════

@dataclass
class SimulationConfig:
    source_run_id: str
    num_batches: int = 80
    batch_size: int = 50
    batch_interval: float = 0.5
    pattern_prob: float = 0.10
    rescore_interval: int = 3
    threshold_percentile: int = 99
    seed: int = 42


# ═══════════════════════════════════════════════════════════
#  GPU Cleanup
# ═══════════════════════════════════════════════════════════

def _cleanup_gpu(scorer=None):
    if scorer is not None:
        try:
            del scorer.sage, scorer.encoder, scorer.generator
            del scorer
        except Exception:
            pass
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()


# ═══════════════════════════════════════════════════════════
#  Save Results
# ═══════════════════════════════════════════════════════════

def _save_results(sim_id: str, state_snapshot: dict, config: SimulationConfig):
    sim_dir = get_repo_root() / "artifacts" / "simulations" / sim_id
    sim_dir.mkdir(parents=True, exist_ok=True)

    confusion = state_snapshot.get("confusion", {})
    tp = confusion.get("tp", 0)
    fp = confusion.get("fp", 0)
    fn = confusion.get("fn", 0)
    tn = confusion.get("tn", 0)

    summary = {
        "sim_id": sim_id,
        "source_run_id": config.source_run_id,
        "duration_seconds": round(state_snapshot.get("elapsed", 0), 1),
        "batches_completed": state_snapshot.get("batch_num", 0),
        "total_batches_configured": config.num_batches,
        "total_transactions": state_snapshot.get("total_txns", 0),
        "patterns_injected": state_snapshot.get("total_patterns", 0),
        "pattern_nodes": state_snapshot.get("pattern_nodes", 0),
        "threshold": state_snapshot.get("threshold", 0),
        "detection": {
            "total_alerts": state_snapshot.get("total_alerts", 0),
            "true_positives": tp, "false_positives": fp,
            "false_negatives": fn, "true_negatives": tn,
            "precision": round(tp / max(tp + fp, 1), 4),
            "recall": round(tp / max(tp + fn, 1), 4),
            "f1": round(2 * tp / max(2 * tp + fp + fn, 1), 4),
        },
        "latency": {
            "mean_all_ms": round(float(np.mean(state_snapshot["latency_history"])), 0) if state_snapshot["latency_history"] else None,
            "p95_ms": round(float(np.percentile(state_snapshot["latency_history"], 95)), 0) if state_snapshot["latency_history"] else None,
        },
        "config": asdict(config),
    }

    with open(sim_dir / "simulation_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    alerts = state_snapshot.get("recent_alerts", [])
    if alerts:
        pd.DataFrame(alerts).to_parquet(sim_dir / "alert_log.parquet", index=False)

    score_hist = state_snapshot.get("score_history", [])
    if score_hist:
        pd.DataFrame(score_hist, columns=["batch", "mean_score", "max_score", "n_alerts"]).to_parquet(
            sim_dir / "score_timeseries.parquet", index=False)

    lats = state_snapshot.get("latency_history", [])
    if lats:
        ri = config.rescore_interval
        pd.DataFrame({
            "batch": list(range(1, len(lats) + 1)),
            "latency_ms": lats,
            "is_rescore": [(i % ri == 0 or i == 1) for i in range(1, len(lats) + 1)],
        }).to_parquet(sim_dir / "latency.parquet", index=False)

    logger.info(f"Simulation results saved to {sim_dir}")


# ═══════════════════════════════════════════════════════════
#  Simulation Loop (background thread)
# ═══════════════════════════════════════════════════════════

def _simulation_loop(
    config: SimulationConfig,
    state: SimulationState,
    stop_event: threading.Event,
    sim_id: str,
):
    scorer = None
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    try:
        source_dir = get_run_dir(config.source_run_id)
        data_dir = str(source_dir / "data")
        models_dir = str(source_dir / "models")

        nf = pd.read_parquet(os.path.join(data_dir, "node_features.parquet"))
        party_ids = nf["id"].tolist()

        rng = np.random.default_rng(config.seed)
        stream = TransactionStream(party_ids, rng, pattern_prob=config.pattern_prob)
        graph = LiveGraph(data_dir)
        scorer = RealtimeScorer(device, models_dir,
                                threshold_pct=config.threshold_percentile,
                                rescore_interval=config.rescore_interval)

        state.update(status="running", threshold=scorer.threshold,
                     total_batches=config.num_batches)

        sim_start = time.perf_counter()

        for batch_num in range(1, config.num_batches + 1):
            if stop_event.is_set():
                state.update(status="stopped", elapsed=time.perf_counter() - sim_start)
                break

            txn_batch = stream.next_batch(config.batch_size)
            affected = graph.update(txn_batch)
            result = scorer.score(graph, affected, batch_num, txn_batch)

            # Confusion matrix
            confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
            if scorer.all_scores is not None:
                sar_labels = graph.get_sar_labels()
                n = min(len(scorer.all_scores), len(sar_labels))
                predicted = (scorer.all_scores[:n] > scorer.threshold).astype(int)
                actual = sar_labels[:n]
                confusion["tp"] = int(((predicted == 1) & (actual == 1)).sum())
                confusion["fp"] = int(((predicted == 1) & (actual == 0)).sum())
                confusion["fn"] = int(((predicted == 0) & (actual == 1)).sum())
                confusion["tn"] = int(((predicted == 0) & (actual == 0)).sum())

            n_pattern = sum(1 for t in txn_batch if t.get("_is_pattern"))

            state.update(
                batch_num=batch_num,
                total_txns=graph.total_txns_processed,
                total_alerts=scorer.total_alerts,
                total_patterns=stream.total_patterns_injected,
                pattern_nodes=len(graph.pattern_nodes),
                score_history=list(scorer.score_history),
                recent_alerts=[dict(a) for a in list(scorer.alerts)[-20:]],
                all_scores=scorer.all_scores.copy() if scorer.all_scores is not None else None,
                sar_labels=graph.get_sar_labels(),
                latency_history=list(scorer.latency_history),
                confusion=confusion,
                elapsed=time.perf_counter() - sim_start,
                last_batch_info=(
                    f"Batch {batch_num}/{config.num_batches}: {len(txn_batch)} txns "
                    f"({n_pattern} pattern) | "
                    f"{result['affected_count']} affected | "
                    f"{len(result['alerts'])} new alerts | "
                    f"{result['latency_ms']:.0f}ms"
                    f"{' [RESCORE]' if result['rescored'] else ''}"
                ),
            )

            if batch_num < config.num_batches:
                if stop_event.wait(timeout=config.batch_interval):
                    state.update(status="stopped", elapsed=time.perf_counter() - sim_start)
                    break
        else:
            state.update(status="finished", elapsed=time.perf_counter() - sim_start)

        _save_results(sim_id, state.get(), config)

    except Exception as e:
        import traceback
        traceback.print_exc()
        state.update(status="error", error=str(e))
    finally:
        _cleanup_gpu(scorer)


# ═══════════════════════════════════════════════════════════
#  SimulationManager — singleton, one-at-a-time
# ═══════════════════════════════════════════════════════════

class SimulationManager:
    def __init__(self):
        self._mgr_lock = threading.Lock()
        self._state = SimulationState()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._config: Optional[SimulationConfig] = None
        self._sim_id: Optional[str] = None

    def start(self, config: SimulationConfig) -> dict:
        with self._mgr_lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("A simulation is already running. Stop it first.")

            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=3.0)
            _cleanup_gpu()

            source_dir = get_run_dir(config.source_run_id)
            for f in ["graphsage.pt", "encoder.pt", "generator.pt",
                       "training_meta.json", "feature_norm.pt", "X_train.npy"]:
                if not (source_dir / "models" / f).exists():
                    raise FileNotFoundError(f"Source run missing model: {f}")
            if not (source_dir / "data" / "node_features.parquet").exists():
                raise FileNotFoundError("Source run missing data/node_features.parquet")

            self._sim_id = str(uuid.uuid4())
            self._config = config
            self._stop_event = threading.Event()
            self._state.reset()
            self._state.update(status="starting", total_batches=config.num_batches)

            self._thread = threading.Thread(
                target=_simulation_loop,
                args=(config, self._state, self._stop_event, self._sim_id),
                daemon=True,
            )
            self._thread.start()
            return {"sim_id": self._sim_id, "status": "starting"}

    def stop(self) -> dict:
        with self._mgr_lock:
            if not self._thread or not self._thread.is_alive():
                return {"status": "not_running"}
            self._stop_event.set()
            self._state.update(status="stopping")
            return {"status": "stopping", "sim_id": self._sim_id}

    def reset(self) -> dict:
        with self._mgr_lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
            _cleanup_gpu()
            self._state.reset()
            self._sim_id = None
            self._config = None
            return {"status": "idle"}

    def status(self) -> dict:
        snapshot = self._state.get()
        snapshot["sim_id"] = self._sim_id
        if self._config:
            snapshot["config"] = asdict(self._config)
        return snapshot


# Module-level singleton
simulation_manager = SimulationManager()
