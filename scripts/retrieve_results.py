#!/usr/bin/env python3
"""Retrieve completed job results and display them.

Checks all pending jobs, parses results, stores to DB, then prints a summary.

Usage:
    python scripts/retrieve_results.py
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

from quantum_noise_pipeline.config import IBMConfig, DatabaseConfig
from quantum_noise_pipeline.database.store import DatabaseStore
from quantum_noise_pipeline.database.models import T1Result, T2Result, ReadoutErrorResult
from quantum_noise_pipeline.utils.ibm_client import IBMClient
from quantum_noise_pipeline.scheduler.runner import retrieve_pending_jobs

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def main() -> None:
    print("\n=== Retrieving Job Results ===")

    config = IBMConfig()
    client = IBMClient.from_config(config)
    db = DatabaseStore(DatabaseConfig())

    # Check and retrieve pending jobs
    pending = db.get_pending_jobs()
    print(f"  Pending jobs: {len(pending)}")
    for p in pending:
        print(f"    {p.job_id} ({p.job_type})")

    if not pending:
        print("  No pending jobs to retrieve.")
    else:
        retrieved = retrieve_pending_jobs(client, db)
        print(f"  Retrieved: {retrieved} job(s)")

    # Display results
    print("\n=== T1 Results ===")
    t1s = db.query_results(T1Result, limit=20)
    if not t1s:
        print("  (none)")
    for r in t1s:
        stderr = f" ± {r.t1_stderr:.1f}" if r.t1_stderr else ""
        print(f"  Qubit {r.qubit}: T1 = {r.t1_us:.1f}{stderr} µs  "
              f"[{r.backend_name}, {r.timestamp.strftime('%Y-%m-%d %H:%M')}]")

    print("\n=== T2 Results ===")
    t2s = db.query_results(T2Result, limit=20)
    if not t2s:
        print("  (none)")
    for r in t2s:
        stderr = f" ± {r.t2_stderr:.1f}" if r.t2_stderr else ""
        print(f"  Qubit {r.qubit}: T2 = {r.t2_us:.1f}{stderr} µs  "
              f"[{r.backend_name}, {r.timestamp.strftime('%Y-%m-%d %H:%M')}]")

    print("\n=== Readout Error Results ===")
    ros = db.query_results(ReadoutErrorResult, limit=20)
    if not ros:
        print("  (none)")
    for r in ros:
        print(f"  Qubit {r.qubit}: 0→1 = {r.error_rate_0to1:.4f}, "
              f"1→0 = {r.error_rate_1to0:.4f}  "
              f"[{r.backend_name}, {r.timestamp.strftime('%Y-%m-%d %H:%M')}]")

    print()


if __name__ == "__main__":
    main()
