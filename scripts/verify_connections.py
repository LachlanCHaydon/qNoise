#!/usr/bin/env python3
"""Verify IBM Quantum and Superstaq connections.

Zero credit cost — no jobs are submitted. Run this before any hardware work
to confirm credentials and backend availability.

Usage:
    python scripts/verify_connections.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env before importing project modules
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv optional; fall back to shell env vars


def check_ibm() -> bool:
    print("\n--- IBM Quantum ---")
    try:
        from quantum_noise_pipeline.config import IBMConfig
        from quantum_noise_pipeline.utils.ibm_client import IBMClient

        config = IBMConfig()
        if not config.api_token:
            print("FAIL: IBM_QUANTUM_TOKEN not set")
            return False

        print(f"  Token: ...{config.api_token[-6:]}")
        print(f"  Channel: {config.channel}")
        print(f"  Instance: {config.instance}")
        print(f"  Target backend: {config.default_backend}")

        # Connect without instance first to discover valid instances
        from qiskit_ibm_runtime import QiskitRuntimeService
        service = QiskitRuntimeService(channel=config.channel, token=config.api_token)

        instances = service.instances()
        print(f"  Available instances: {instances}")

        # Extract CRN string from first available instance
        raw = instances[0] if instances else None
        instance = raw["crn"] if isinstance(raw, dict) else raw
        print(f"  Using instance (CRN): {instance}")

        service2 = QiskitRuntimeService(
            channel=config.channel, token=config.api_token, instance=instance
        )
        backend = service2.backend(config.default_backend)
        target = backend.target
        print(f"  Backend: {backend.name}")
        print(f"  Qubits: {target.num_qubits}")
        print(f"  Basis gates: {list(target.operation_names)}")
        print("OK: IBM connection successful")
        print(f"\n  --> Set IBM_QUANTUM_INSTANCE={instance} in your .env")
        return True

    except Exception as e:
        print(f"FAIL: {e}")
        return False


def check_superstaq() -> bool:
    print("\n--- Superstaq ---")
    try:
        import qiskit_superstaq as qss
        from qiskit import QuantumCircuit

        token = os.environ.get("SUPERSTAQ_API_TOKEN", "")
        if not token:
            print("FAIL: SUPERSTAQ_API_TOKEN not set")
            return False

        print(f"  Token: ...{token[-6:]}")

        provider = qss.SuperstaqProvider(api_key=token)

        # Compile a Bell state with dry-run — free, no credits used
        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure_all()

        result = provider.ibmq_compile(qc, target="ibmq_fez_qpu", dry_run=True)
        print(f"  Dry-run compile result type: {type(result).__name__}")
        print("OK: Superstaq connection successful")
        return True

    except Exception as e:
        print(f"FAIL: {e}")
        return False


if __name__ == "__main__":
    ibm_ok = check_ibm()
    ss_ok = check_superstaq()

    print("\n--- Summary ---")
    print(f"  IBM Quantum:  {'OK' if ibm_ok else 'FAIL'}")
    print(f"  Superstaq:    {'OK' if ss_ok else 'FAIL'}")

    sys.exit(0 if (ibm_ok and ss_ok) else 1)
