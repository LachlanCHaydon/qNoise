#!/usr/bin/env python3
"""Compilation benchmark: Qiskit default vs Superstaq on ibm_fez.

Phase 1 (free): Compile all benchmark circuits through both compilers,
                compare depth/gate metrics locally — no hardware needed.

Phase 2 (credits): Submit compiled circuits to ibm_fez, compare
                   actual measurement fidelity on real hardware.

Usage:
    python scripts/run_compilation_benchmark.py
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


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# ── Phase 1: Static compilation comparison (free) ─────────────────

def run_compilation_comparison() -> list[dict]:
    """Compile all circuits with both compilers, return metrics."""
    import qiskit_superstaq as qss
    from qiskit import transpile

    from quantum_noise_pipeline.compilation.benchmark import (
        get_benchmark_circuits,
        extract_circuit_metrics,
    )
    from quantum_noise_pipeline.config import IBMConfig
    from quantum_noise_pipeline.utils.ibm_client import IBMClient

    section("Phase 1: Compilation Comparison (no credits)")

    # Connect to IBM to get real backend topology
    print("  Connecting to ibm_fez for backend topology...")
    config = IBMConfig()
    client = IBMClient.from_config(config)
    backend = client.backend
    print("  Connected.\n")

    # Connect to Superstaq
    token = os.environ.get("SUPERSTAQ_API_TOKEN", "")
    provider = qss.SuperstaqProvider(api_key=token)

    circuits = get_benchmark_circuits()
    results = []

    header = f"  {'Circuit':<20} {'Compiler':<12} {'Depth Before':>12} {'Depth After':>11} {'2Q Gates':>9} {'Total Gates':>11}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for name, qc in circuits.items():
        original_depth = qc.depth()
        original_metrics = extract_circuit_metrics(qc)

        # ── Qiskit compilation ────────────────────────────────────
        qiskit_compiled = transpile(qc, backend=backend, optimization_level=3)
        qiskit_metrics = extract_circuit_metrics(qiskit_compiled)

        print(f"  {name:<20} {'qiskit':<12} {original_depth:>12} "
              f"{qiskit_metrics.depth:>11} {qiskit_metrics.two_qubit_gate_count:>9} "
              f"{qiskit_metrics.total_gate_count:>11}")

        results.append({
            "circuit_name": name,
            "compiler": "qiskit",
            "original_depth": original_depth,
            "compiled_depth": qiskit_metrics.depth,
            "two_qubit_gates": qiskit_metrics.two_qubit_gate_count,
            "total_gates": qiskit_metrics.total_gate_count,
            "compiled_circuit": qiskit_compiled,
            "original_circuit": qc,
        })

        # ── Superstaq compilation ─────────────────────────────────
        try:
            ss_output = provider.ibmq_compile(qc, target="ibmq_fez_qpu")
            ss_compiled = ss_output.circuit
            ss_metrics = extract_circuit_metrics(ss_compiled)

            print(f"  {'':<20} {'superstaq':<12} {original_depth:>12} "
                  f"{ss_metrics.depth:>11} {ss_metrics.two_qubit_gate_count:>9} "
                  f"{ss_metrics.total_gate_count:>11}")

            results.append({
                "circuit_name": name,
                "compiler": "superstaq",
                "original_depth": original_depth,
                "compiled_depth": ss_metrics.depth,
                "two_qubit_gates": ss_metrics.two_qubit_gate_count,
                "total_gates": ss_metrics.total_gate_count,
                "compiled_circuit": ss_compiled,
                "original_circuit": qc,
            })

        except Exception as e:
            print(f"  {'':<20} {'superstaq':<12} {'FAILED: ' + str(e)[:40]:>45}")

        print()  # blank line between circuits

    return results


# ── Phase 2: Hardware execution (costs credits) ───────────────────

def run_hardware_execution(compilation_results: list[dict]) -> None:
    """Submit compiled circuits to ibm_fez and store benchmark results."""
    from qiskit import QuantumCircuit

    from quantum_noise_pipeline.config import IBMConfig, DatabaseConfig
    from quantum_noise_pipeline.utils.ibm_client import IBMClient
    from quantum_noise_pipeline.database.store import DatabaseStore

    section("Phase 2: Hardware Execution")

    # Group by circuit for submission
    by_circuit: dict[str, dict] = {}
    for r in compilation_results:
        by_circuit.setdefault(r["circuit_name"], {})[r["compiler"]] = r

    # Show what will be submitted
    total_circuits = len(compilation_results)
    shots = 1024
    print(f"  Will submit {total_circuits} circuits × {shots} shots to ibm_fez")
    print(f"  Circuits: {list(by_circuit.keys())}")
    print(f"  Compilers: qiskit + superstaq")
    print()

    confirm = input("  >>> Type 'yes' to submit (this costs credits): ").strip().lower()
    if confirm != "yes":
        print("  Skipped. Run again and type 'yes' to execute on hardware.")
        return

    config = IBMConfig()
    client = IBMClient.from_config(config)

    # Ensure all circuits are hardware-compatible (fix non-integer dt durations
    # from Superstaq output). optimization_level=0 does minimal changes — just
    # fixes constraints without re-optimizing the circuit.
    from qiskit import transpile as _transpile
    all_circuits = []
    for r in compilation_results:
        circ = r["compiled_circuit"]
        if r["compiler"] == "superstaq":
            circ = _transpile(circ, backend=client.backend, optimization_level=0)
        all_circuits.append(circ)

    print("  Submitting...")
    job = client.run_sampler(all_circuits, shots=shots)
    job_id = job.job_id()
    print(f"  Job submitted: {job_id}")

    # Store in DB
    db = DatabaseStore(DatabaseConfig())
    db.create_job_record(
        job_id=job_id,
        backend_name=client.backend_name,
        job_type="compilation_benchmark",
        metadata_json={
            "circuits": [r["circuit_name"] for r in compilation_results],
            "compilers": [r["compiler"] for r in compilation_results],
            "shots": shots,
            "compiled_depths": [r["compiled_depth"] for r in compilation_results],
            "two_qubit_gates": [r["two_qubit_gates"] for r in compilation_results],
            "total_gates": [r["total_gates"] for r in compilation_results],
            "original_depths": [r["original_depth"] for r in compilation_results],
        },
    )

    print(f"  Job recorded in database.")
    print(f"  Monitor at: https://quantum.ibm.com  (job: {job_id})")
    print(f"  Retrieve results with: python scripts/retrieve_benchmark_results.py {job_id}")


# ── Summary ───────────────────────────────────────────────────────

def print_summary(results: list[dict]) -> None:
    section("Compiler Comparison Summary")

    circuits = list(dict.fromkeys(r["circuit_name"] for r in results))

    for name in circuits:
        circuit_results = {r["compiler"]: r for r in results if r["circuit_name"] == name}
        if "qiskit" not in circuit_results or "superstaq" not in circuit_results:
            continue

        q = circuit_results["qiskit"]
        s = circuit_results["superstaq"]

        depth_diff = q["compiled_depth"] - s["compiled_depth"]
        gate_diff = q["two_qubit_gates"] - s["two_qubit_gates"]

        winner_depth = "superstaq" if depth_diff > 0 else ("qiskit" if depth_diff < 0 else "tie")
        winner_gates = "superstaq" if gate_diff > 0 else ("qiskit" if gate_diff < 0 else "tie")

        print(f"  {name}:")
        print(f"    Depth:    Qiskit={q['compiled_depth']}, Superstaq={s['compiled_depth']}"
              f"  → {winner_depth} wins by {abs(depth_diff)}")
        print(f"    2Q gates: Qiskit={q['two_qubit_gates']}, Superstaq={s['two_qubit_gates']}"
              f"  → {winner_gates} wins by {abs(gate_diff)}")
        print()


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nQuantum Noise Pipeline — Compilation Benchmark")
    print("ibm_fez: Qiskit (optimization_level=3) vs Superstaq")

    try:
        results = run_compilation_comparison()
        print_summary(results)
        run_hardware_execution(results)
    except KeyboardInterrupt:
        print("\n  Cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        raise
