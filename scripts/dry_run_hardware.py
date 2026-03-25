#!/usr/bin/env python3
"""Full pipeline dry-run — no credits spent, no jobs submitted.

Validates every stage of the pipeline against real infrastructure:
  1. IBM connection + backend fetch
  2. Circuit building (T1, T2, readout)
  3. Transpilation with correct physical qubit layout
  4. Superstaq dry-run compilation
  5. Database initialization and round-trip writes

Run this and confirm every section prints OK before submitting hardware jobs.

Usage:
    python scripts/dry_run_hardware.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


QUBITS = [0, 1, 2]       # small subset
T1_DELAYS = 5             # fewer delays for speed
T2_DELAYS = 5
SHOTS = 256


def section(title: str) -> None:
    print(f"\n{'='*50}")
    print(f"  {title}")
    print('='*50)


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


# ── 1. IBM connection ─────────────────────────────────────────────

def check_ibm_connection() -> object | None:
    section("1. IBM Connection + Backend")
    try:
        from quantum_noise_pipeline.config import IBMConfig
        from quantum_noise_pipeline.utils.ibm_client import IBMClient

        config = IBMConfig()
        client = IBMClient.from_config(config)
        props = client.get_backend_properties()

        ok(f"Connected to {props['name']} ({props['num_qubits']} qubits)")
        ok(f"Basis gates: {props['basis_gates']}")
        ok(f"Operational: {client.is_operational()}")

        # Confirm our target qubits exist on this backend
        for q in QUBITS:
            assert q < props["num_qubits"], f"Qubit {q} doesn't exist on backend"
        ok(f"Target qubits {QUBITS} all valid on this backend")

        return client
    except Exception as e:
        fail(str(e))
        return None


# ── 2. Circuit building ───────────────────────────────────────────

def check_circuit_building() -> dict | None:
    section("2. Circuit Building (T1 / T2 / Readout)")
    try:
        from quantum_noise_pipeline.characterization.t1 import (
            build_t1_circuits, generate_delay_values as t1_delays
        )
        from quantum_noise_pipeline.characterization.t2 import (
            build_t2_circuits, generate_delay_values as t2_delays
        )
        from quantum_noise_pipeline.characterization.readout_error import build_readout_circuits

        delays_t1 = t1_delays(T1_DELAYS, 300.0)
        delays_t2 = t2_delays(T2_DELAYS, 200.0)

        t1_circs, t1_meta = build_t1_circuits(QUBITS, delays_t1)
        t2_circs, t2_meta = build_t2_circuits(QUBITS, delays_t2)
        ro_circs, ro_meta = build_readout_circuits(QUBITS)

        expected_t1 = len(QUBITS) * T1_DELAYS
        expected_t2 = len(QUBITS) * T2_DELAYS
        expected_ro = len(QUBITS) * 2

        assert len(t1_circs) == expected_t1, f"Expected {expected_t1} T1 circuits, got {len(t1_circs)}"
        assert len(t2_circs) == expected_t2, f"Expected {expected_t2} T2 circuits, got {len(t2_circs)}"
        assert len(ro_circs) == expected_ro, f"Expected {expected_ro} readout circuits, got {len(ro_circs)}"

        ok(f"T1: {len(t1_circs)} circuits ({len(QUBITS)} qubits × {T1_DELAYS} delays)")
        ok(f"T2: {len(t2_circs)} circuits ({len(QUBITS)} qubits × {T2_DELAYS} delays)")
        ok(f"Readout: {len(ro_circs)} circuits ({len(QUBITS)} qubits × 2 states)")
        ok(f"Total: {len(t1_circs) + len(t2_circs) + len(ro_circs)} circuits")

        # Verify metadata is intact
        for c in t1_circs:
            assert "qubit" in c.metadata, "T1 circuit missing qubit metadata"
            assert "delay_us" in c.metadata, "T1 circuit missing delay_us metadata"
        ok("Circuit metadata intact")

        return {"t1": t1_circs, "t2": t2_circs, "ro": ro_circs,
                "delays_t1": delays_t1, "delays_t2": delays_t2}
    except Exception as e:
        fail(str(e))
        return None


# ── 3. Transpilation with initial_layout ─────────────────────────

def check_transpilation(client: object, circuits: dict) -> list | None:
    section("3. Transpilation (with per-qubit initial_layout)")
    try:
        from qiskit import transpile

        backend = client.backend  # type: ignore[attr-defined]
        t1_circs = circuits["t1"]
        t2_circs = circuits["t2"]
        ro_circs = circuits["ro"]

        def transpile_qubit(circs: list, qubit: int) -> list:
            return list(transpile(circs, backend=backend,
                                  initial_layout=[qubit], optimization_level=1))

        transpiled: list = []
        for q in QUBITS:
            batch = [c for c in t1_circs if c.metadata["qubit"] == q]
            t = transpile_qubit(batch, q)
            transpiled += t
            ok(f"T1 qubit {q}: transpiled {len(t)} circuits, "
               f"avg depth {sum(c.depth() for c in t) / len(t):.1f}")

        for q in QUBITS:
            batch = [c for c in t2_circs if c.metadata["qubit"] == q]
            t = transpile_qubit(batch, q)
            transpiled += t
            ok(f"T2 qubit {q}: transpiled {len(t)} circuits, "
               f"avg depth {sum(c.depth() for c in t) / len(t):.1f}")

        for q in QUBITS:
            batch = [c for c in ro_circs if c.metadata["qubit"] == q]
            t = transpile_qubit(batch, q)
            transpiled += t
            ok(f"Readout qubit {q}: transpiled {len(t)} circuits")

        ok(f"Total transpiled: {len(transpiled)} circuits — ready for submission")
        return transpiled
    except Exception as e:
        fail(str(e))
        return None


# ── 4. Superstaq dry-run ──────────────────────────────────────────

def check_superstaq() -> bool:
    section("4. Superstaq Dry-Run Compilation")
    try:
        import qiskit_superstaq as qss
        from qiskit import QuantumCircuit

        token = os.environ.get("SUPERSTAQ_API_TOKEN", "")
        provider = qss.SuperstaqProvider(api_key=token)

        circuits_to_test = {
            "bell_state": _make_bell(),
            "ghz_4q": _make_ghz(4),
        }
        for name, qc in circuits_to_test.items():
            result = provider.ibmq_compile(qc, target="ibmq_fez_qpu", dry_run=True)
            compiled = result.circuit
            ok(f"{name}: depth {qc.depth()} → {compiled.depth()} "
               f"(dry-run, no credits)")

        return True
    except Exception as e:
        fail(str(e))
        return False


def _make_bell() -> object:
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(2, 2, name="bell_state")
    qc.h(0); qc.cx(0, 1); qc.measure([0, 1], [0, 1])
    return qc


def _make_ghz(n: int) -> object:
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(n, n, name=f"ghz_{n}q")
    qc.h(0)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    qc.measure(range(n), range(n))
    return qc


# ── 5. Database round-trip ────────────────────────────────────────

def check_database() -> bool:
    section("5. Database Round-Trip")
    try:
        from quantum_noise_pipeline.config import DatabaseConfig
        from quantum_noise_pipeline.database.store import DatabaseStore
        from quantum_noise_pipeline.database.models import T1Result, T2Result

        with tempfile.TemporaryDirectory() as tmpdir:
            class TempDB(DatabaseConfig):
                @property
                def url(self) -> str:
                    return f"sqlite:///{tmpdir}/test.db"

            db = DatabaseStore(TempDB())
            ok("Database initialized")

            r = db.save_t1_result("ibm_fez", qubit=0, t1_us=150.3,
                                  num_delays=5, shots=256, t1_stderr=2.1,
                                  job_id="dry_run_test")
            ok(f"T1 write: {r}")

            results = db.query_results(T1Result, backend_name="ibm_fez", qubit=0)
            assert len(results) == 1 and results[0].t1_us == 150.3
            ok("T1 read-back verified")

            job = db.create_job_record("dry_run_job_001", "ibm_fez", "characterization_batch",
                                       {"qubits": QUBITS, "shots": SHOTS})
            ok(f"Job record created: {job.job_id}")

            db.update_job_status("dry_run_job_001", "DONE")
            pending = db.get_pending_jobs()
            assert len(pending) == 0
            ok("Job status update verified (no pending jobs after DONE)")

        return True
    except Exception as e:
        fail(str(e))
        return False


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nQuantum Noise Pipeline — Pre-Flight Dry Run")
    print("No jobs will be submitted. No credits will be used.")

    client = check_ibm_connection()
    circuits = check_circuit_building()
    transpiled = check_transpilation(client, circuits) if client and circuits else None
    ss_ok = check_superstaq()
    db_ok = check_database()

    section("Summary")
    results = {
        "IBM connection":    client is not None,
        "Circuit building":  circuits is not None,
        "Transpilation":     transpiled is not None,
        "Superstaq dry-run": ss_ok,
        "Database":          db_ok,
    }
    all_ok = True
    for name, passed in results.items():
        status = "OK  " if passed else "FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_ok = False

    print()
    if all_ok:
        print("All checks passed. Pipeline is ready for hardware submission.")
    else:
        print("Fix the failures above before submitting to hardware.")
    sys.exit(0 if all_ok else 1)
