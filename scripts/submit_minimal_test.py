#!/usr/bin/env python3
"""Submit a minimal characterization batch to IBM hardware.

This WILL spend credits. Uses conservative parameters:
  - 3 qubits (0, 1, 2)
  - 5 delay points per qubit for T1 and T2
  - 256 shots per circuit
  - Total: 36 circuits

Usage:
    python scripts/submit_minimal_test.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from qiskit import transpile

from quantum_noise_pipeline.config import IBMConfig, DatabaseConfig
from quantum_noise_pipeline.database.store import DatabaseStore
from quantum_noise_pipeline.utils.ibm_client import IBMClient
from quantum_noise_pipeline.characterization.t1 import (
    build_t1_circuits, generate_delay_values as t1_delays,
)
from quantum_noise_pipeline.characterization.t2 import (
    build_t2_circuits, generate_delay_values as t2_delays,
)
from quantum_noise_pipeline.characterization.readout_error import build_readout_circuits

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ── Minimal test parameters ──────────────────────────────────────
QUBITS = [0, 1, 2]
T1_NUM_DELAYS = 5
T1_MAX_DELAY_US = 300.0
T2_NUM_DELAYS = 5
T2_MAX_DELAY_US = 200.0
SHOTS = 256


def main() -> None:
    print("\n=== Minimal Hardware Test ===")
    print(f"  Qubits: {QUBITS}")
    print(f"  T1: {T1_NUM_DELAYS} delays up to {T1_MAX_DELAY_US} µs")
    print(f"  T2: {T2_NUM_DELAYS} delays up to {T2_MAX_DELAY_US} µs")
    print(f"  Shots: {SHOTS}")

    # Build circuits
    delays_t1 = t1_delays(T1_NUM_DELAYS, T1_MAX_DELAY_US)
    delays_t2 = t2_delays(T2_NUM_DELAYS, T2_MAX_DELAY_US)

    t1_circs, _ = build_t1_circuits(QUBITS, delays_t1)
    t2_circs, _ = build_t2_circuits(QUBITS, delays_t2)
    ro_circs, _ = build_readout_circuits(QUBITS)

    n_t1 = len(t1_circs)
    n_t2 = len(t2_circs)
    n_ro = len(ro_circs)
    total = n_t1 + n_t2 + n_ro

    print(f"  Circuits: {n_t1} T1 + {n_t2} T2 + {n_ro} readout = {total} total")

    # Connect to IBM
    config = IBMConfig()
    client = IBMClient.from_config(config)

    if not client.is_operational():
        print(f"  ERROR: {config.default_backend} is not operational right now.")
        sys.exit(1)

    backend = client.backend
    print(f"  Backend: {client.backend_name} (operational)")

    # Transpile with correct physical qubit mapping
    print("  Transpiling...")
    transpiled: list = []
    for q in QUBITS:
        transpiled += list(transpile(
            [c for c in t1_circs if c.metadata["qubit"] == q],
            backend=backend, initial_layout=[q], optimization_level=1))
    for q in QUBITS:
        transpiled += list(transpile(
            [c for c in t2_circs if c.metadata["qubit"] == q],
            backend=backend, initial_layout=[q], optimization_level=1))
    for q in QUBITS:
        transpiled += list(transpile(
            [c for c in ro_circs if c.metadata["qubit"] == q],
            backend=backend, initial_layout=[q], optimization_level=1))

    print(f"  Transpiled {len(transpiled)} circuits")

    # Final confirmation
    print(f"\n  >>> READY TO SUBMIT {total} circuits × {SHOTS} shots to {client.backend_name}")
    confirm = input("  >>> Type 'yes' to submit (this costs credits): ").strip().lower()
    if confirm != "yes":
        print("  Aborted.")
        sys.exit(0)

    # Submit
    print("  Submitting...")
    job = client.run_sampler(transpiled, shots=SHOTS)
    job_id = job.job_id()
    print(f"  Job submitted: {job_id}")

    # Record in database
    db = DatabaseStore(DatabaseConfig())
    db.create_job_record(
        job_id=job_id,
        backend_name=client.backend_name,
        job_type="characterization_batch",
        metadata_json={
            "qubits": QUBITS,
            "num_t1_circuits": n_t1,
            "num_t2_circuits": n_t2,
            "num_readout_circuits": n_ro,
            "shots": SHOTS,
            "test": "minimal_first_run",
        },
    )
    print(f"  Job recorded in database.")
    print(f"\n  Monitor at: https://quantum.ibm.com  (look for job {job_id})")
    print(f"  To retrieve results later, run:  python -c \"")
    print(f"    from quantum_noise_pipeline.scheduler.runner import main; main()\"")


if __name__ == "__main__":
    main()
