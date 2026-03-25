#!/usr/bin/env python3
"""Retrieve and display compilation benchmark results from hardware.

Fetches a completed compilation_benchmark job, extracts counts,
and compares Qiskit vs Superstaq circuit performance.

Usage:
    python scripts/retrieve_benchmark_results.py [JOB_ID]

If no JOB_ID is given, retrieves the most recent compilation_benchmark job.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


def get_ideal_distribution(circuit_name: str) -> dict[str, float]:
    """Return the ideal (noiseless) output distribution for a benchmark circuit.

    Args:
        circuit_name: Name of the benchmark circuit.

    Returns:
        Dict mapping bitstring to ideal probability.
    """
    if circuit_name == "bell_state":
        # Bell state: |00⟩ + |11⟩ / sqrt(2)
        return {"00": 0.5, "11": 0.5}
    elif circuit_name == "ghz_4q":
        # GHZ: |0000⟩ + |1111⟩ / sqrt(2)
        return {"0000": 0.5, "1111": 0.5}
    elif circuit_name == "qft_4q":
        # QFT on |0000⟩ → uniform superposition
        return {format(i, "04b"): 1/16 for i in range(16)}
    elif circuit_name == "qaoa_maxcut_4q":
        # QAOA MaxCut on ring: optimal cuts are alternating patterns
        # 0101, 1010 are optimal 4-cuts on a 4-ring
        # But with p=1 and fixed angles, the distribution is broader
        # We'll just measure heavy output probability
        return {}  # No simple ideal — use heavy output metric
    return {}


def hellinger_fidelity(measured: dict[str, int], ideal: dict[str, float], shots: int) -> float:
    """Compute Hellinger fidelity between measured counts and ideal distribution.

    F_H = (sum_x sqrt(p_x * q_x))^2
    where p_x = measured probability, q_x = ideal probability.

    Args:
        measured: Count dict from hardware.
        ideal: Ideal probability distribution.
        shots: Total number of shots.

    Returns:
        Hellinger fidelity in [0, 1]. 1.0 = perfect match.
    """
    import math
    fidelity_sum = 0.0
    all_keys = set(list(measured.keys()) + list(ideal.keys()))
    for key in all_keys:
        p = measured.get(key, 0) / shots
        q = ideal.get(key, 0.0)
        fidelity_sum += math.sqrt(p * q)
    return fidelity_sum ** 2


def success_probability(measured: dict[str, int], target_states: list[str], shots: int) -> float:
    """Compute probability of measuring one of the target states.

    Args:
        measured: Count dict from hardware.
        target_states: List of "correct" bitstrings.
        shots: Total shots.

    Returns:
        Probability in [0, 1].
    """
    correct = sum(measured.get(s, 0) for s in target_states)
    return correct / shots


def main() -> None:
    from qiskit_ibm_runtime import QiskitRuntimeService

    from quantum_noise_pipeline.config import IBMConfig, DatabaseConfig
    from quantum_noise_pipeline.database.store import DatabaseStore
    from quantum_noise_pipeline.database.models import JobRecord
    from quantum_noise_pipeline.scheduler.runner import _extract_counts_from_sampler_result

    config = IBMConfig()
    service = QiskitRuntimeService(
        channel=config.channel,
        token=config.api_token,
        instance=config.instance or None,
    )

    db = DatabaseStore(DatabaseConfig())

    # Find the job
    job_id = sys.argv[1] if len(sys.argv) > 1 else None

    if not job_id:
        # Find most recent compilation_benchmark job
        from sqlalchemy import select
        with db._session() as session:
            record = session.execute(
                select(JobRecord)
                .where(JobRecord.job_type == "compilation_benchmark")
                .order_by(JobRecord.submitted_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if record:
                job_id = record.job_id
            else:
                print("No compilation_benchmark jobs found in database.")
                sys.exit(1)

    print(f"\n=== Compilation Benchmark Results ===")
    print(f"  Job: {job_id}")

    # Get metadata from DB
    from sqlalchemy import select
    with db._session() as session:
        record = session.execute(
            select(JobRecord).where(JobRecord.job_id == job_id)
        ).scalar_one_or_none()

    if not record:
        print(f"  Job {job_id} not found in database.")
        sys.exit(1)

    meta = record.metadata_json or {}
    circuit_names = meta.get("circuits", [])
    compilers = meta.get("compilers", [])
    shots = meta.get("shots", 1024)
    compiled_depths = meta.get("compiled_depths", [])
    two_qubit_gates = meta.get("two_qubit_gates", [])
    total_gates = meta.get("total_gates", [])
    original_depths = meta.get("original_depths", [])

    print(f"  Circuits: {len(circuit_names)}")
    print(f"  Shots: {shots}")

    # Fetch results from IBM
    print(f"  Fetching results from IBM...")
    job = service.job(job_id)
    raw_status = job.status()
    status_str = raw_status.name if hasattr(raw_status, "name") else str(raw_status)

    if status_str != "DONE":
        print(f"  Job status: {status_str} — not yet complete.")
        sys.exit(0)

    result = job.result()
    all_counts = _extract_counts_from_sampler_result(result)

    # ── Display results ───────────────────────────────────────────

    # Group results by circuit name
    unique_circuits = list(dict.fromkeys(circuit_names))

    print(f"\n{'='*75}")
    header = f"  {'Circuit':<20} {'Compiler':<12} {'Depth':>6} {'2Q':>5} {'Gates':>6} {'Fidelity':>10} {'Success':>9}"
    print(header)
    print("  " + "-" * 71)

    # Store for DB
    benchmark_records = []

    for circ_name in unique_circuits:
        # Find indices for this circuit
        indices = [i for i, c in enumerate(circuit_names) if c == circ_name]

        ideal = get_ideal_distribution(circ_name)

        for idx in indices:
            compiler = compilers[idx]
            counts = all_counts[idx]
            depth = compiled_depths[idx] if idx < len(compiled_depths) else "?"
            twoq = two_qubit_gates[idx] if idx < len(two_qubit_gates) else "?"
            total = total_gates[idx] if idx < len(total_gates) else "?"
            orig_depth = original_depths[idx] if idx < len(original_depths) else "?"

            # Compute metrics
            if ideal:
                fid = hellinger_fidelity(counts, ideal, shots)
                target_states = [k for k, v in ideal.items() if v > 0.01]
                succ = success_probability(counts, target_states, shots)
                fid_str = f"{fid:.4f}"
                succ_str = f"{succ:.4f}"
            else:
                fid = None
                succ = None
                fid_str = "N/A"
                succ_str = "N/A"

            label = circ_name if compiler == compilers[indices[0]] else ""
            print(f"  {label:<20} {compiler:<12} {depth:>6} {twoq:>5} {total:>6} {fid_str:>10} {succ_str:>9}")

            benchmark_records.append({
                "circuit_name": circ_name,
                "compiler": compiler,
                "depth": depth,
                "two_qubit_gates": twoq,
                "total_gates": total,
                "fidelity": fid,
                "success_prob": succ,
                "counts": counts,
                "original_depth": orig_depth,
            })

        print()

    # ── Winner summary ────────────────────────────────────────────

    print(f"{'='*75}")
    print(f"  HEAD-TO-HEAD WINNERS")
    print(f"  " + "-" * 40)

    for circ_name in unique_circuits:
        records = [r for r in benchmark_records if r["circuit_name"] == circ_name]
        if len(records) < 2:
            continue

        q = next((r for r in records if r["compiler"] == "qiskit"), None)
        s = next((r for r in records if r["compiler"] == "superstaq"), None)
        if not q or not s:
            continue

        winners = []

        # Depth comparison
        if q["depth"] != s["depth"]:
            w = "Superstaq" if s["depth"] < q["depth"] else "Qiskit"
            winners.append(f"depth ({w}: {min(q['depth'], s['depth'])} vs {max(q['depth'], s['depth'])})")

        # 2Q gate comparison
        if q["two_qubit_gates"] != s["two_qubit_gates"]:
            w = "Superstaq" if s["two_qubit_gates"] < q["two_qubit_gates"] else "Qiskit"
            winners.append(f"2Q gates ({w}: {min(q['two_qubit_gates'], s['two_qubit_gates'])} vs {max(q['two_qubit_gates'], s['two_qubit_gates'])})")

        # Fidelity comparison
        if q["fidelity"] is not None and s["fidelity"] is not None:
            w = "Superstaq" if s["fidelity"] > q["fidelity"] else "Qiskit"
            winners.append(f"fidelity ({w}: {max(q['fidelity'], s['fidelity']):.4f} vs {min(q['fidelity'], s['fidelity']):.4f})")

        print(f"\n  {circ_name}:")
        for win in winners:
            print(f"    {win}")

    # ── Save top-level counts for inspection ──────────────────────

    print(f"\n{'='*75}")
    print(f"  RAW COUNTS (top 5 outcomes per circuit)")
    print(f"  " + "-" * 50)
    for r in benchmark_records:
        sorted_counts = sorted(r["counts"].items(), key=lambda x: -x[1])[:5]
        counts_str = ", ".join(f"{k}:{v}" for k, v in sorted_counts)
        print(f"  {r['circuit_name']:<20} {r['compiler']:<12} {counts_str}")

    # Store benchmark results in DB
    try:
        for r in benchmark_records:
            db.save_compilation_benchmark(
                backend_name="ibm_fez",
                circuit_name=r["circuit_name"],
                compiler=r["compiler"],
                depth_before=r["original_depth"],
                depth_after=r["depth"],
                cx_count=r["two_qubit_gates"],
                total_gate_count=r["total_gates"],
                shots=shots,
                fidelity=r["fidelity"],
                job_id=job_id,
                raw_data={"counts": r["counts"]},
            )
        print(f"\n  Results saved to database.")
    except Exception as e:
        print(f"\n  Warning: failed to save to DB: {e}")

    print()


if __name__ == "__main__":
    main()
