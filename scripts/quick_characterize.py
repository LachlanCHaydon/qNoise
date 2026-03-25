#!/usr/bin/env python3
"""Lightweight characterization run — optimized for credit efficiency.

Designed to be run 2-3x per day to build temporal drift data.
Uses fewer delays and shots than the full pipeline to conserve credits.

Estimated QR usage: ~15 seconds per run
Budget for 500s remaining: ~33 runs

Usage:
    python scripts/quick_characterize.py          # default 3 qubits
    python scripts/quick_characterize.py --qubits 0 1 2 5 10  # custom qubits
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Credit-efficient defaults ──
DEFAULT_QUBITS = [0, 1, 2]
NUM_T1_DELAYS = 10        # 10 is enough for a decent exponential fit
NUM_T2_DELAYS = 10
T1_MAX_DELAY_US = 400.0   # wide enough to capture long T1 qubits
T2_MAX_DELAY_US = 300.0
SHOTS = 512               # half the "full" run — still enough for ~2% precision


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick characterization run")
    parser.add_argument("--qubits", type=int, nargs="+", default=DEFAULT_QUBITS,
                        help="Physical qubit indices to characterize")
    parser.add_argument("--shots", type=int, default=SHOTS,
                        help=f"Shots per circuit (default: {SHOTS})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build and transpile circuits but don't submit")
    args = parser.parse_args()

    qubits = args.qubits
    shots = args.shots

    from qiskit import transpile

    from quantum_noise_pipeline.characterization.t1 import (
        build_t1_circuits, generate_delay_values as t1_delays,
    )
    from quantum_noise_pipeline.characterization.t2 import (
        build_t2_circuits, generate_delay_values as t2_delays,
    )
    from quantum_noise_pipeline.characterization.readout_error import build_readout_circuits
    from quantum_noise_pipeline.config import IBMConfig, DatabaseConfig
    from quantum_noise_pipeline.utils.ibm_client import IBMClient
    from quantum_noise_pipeline.database.store import DatabaseStore

    # Build circuits
    delays_t1 = t1_delays(NUM_T1_DELAYS, T1_MAX_DELAY_US)
    delays_t2 = t2_delays(NUM_T2_DELAYS, T2_MAX_DELAY_US)

    t1_circs, _ = build_t1_circuits(qubits, delays_t1)
    t2_circs, _ = build_t2_circuits(qubits, delays_t2)
    ro_circs, _ = build_readout_circuits(qubits)

    n_total = len(t1_circs) + len(t2_circs) + len(ro_circs)

    print(f"\n  Quick Characterize — Credit-Efficient Run")
    print(f"  Qubits:   {qubits}")
    print(f"  Delays:   {NUM_T1_DELAYS} (T1) + {NUM_T2_DELAYS} (T2)")
    print(f"  Shots:    {shots}")
    print(f"  Circuits: {n_total}  ({len(t1_circs)} T1 + {len(t2_circs)} T2 + {len(ro_circs)} readout)")
    print(f"  Est. QR:  ~{n_total * shots / 36 / 256 * 5:.0f} seconds\n")

    # Connect and transpile
    config = IBMConfig()
    client = IBMClient.from_config(config)
    backend = client.backend

    def _transpile_qubit(circuits: list, qubit: int) -> list:
        return list(transpile(circuits, backend=backend,
                              initial_layout=[qubit], optimization_level=1))

    transpiled: list = []
    for q in qubits:
        transpiled += _transpile_qubit([c for c in t1_circs if c.metadata["qubit"] == q], q)
    for q in qubits:
        transpiled += _transpile_qubit([c for c in t2_circs if c.metadata["qubit"] == q], q)
    for q in qubits:
        transpiled += _transpile_qubit([c for c in ro_circs if c.metadata["qubit"] == q], q)

    print(f"  Transpiled {len(transpiled)} circuits for {client.backend_name}")

    if args.dry_run:
        print("  [DRY RUN] — no job submitted.")
        return

    confirm = input("  >>> Submit? (y/n): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("  Cancelled.")
        return

    job = client.run_sampler(transpiled, shots=shots)
    job_id = job.job_id()
    print(f"  Submitted: {job_id}")

    db = DatabaseStore(DatabaseConfig())
    db.create_job_record(
        job_id=job_id,
        backend_name=client.backend_name,
        job_type="characterization_batch",
        metadata_json={
            "qubits": qubits,
            "num_t1_circuits": len(t1_circs),
            "num_t2_circuits": len(t2_circs),
            "num_readout_circuits": len(ro_circs),
            "shots": shots,
        },
    )
    print(f"  Recorded in DB. Retrieve with: python scripts/retrieve_results.py")


if __name__ == "__main__":
    main()
