"""Readout (measurement) error characterization.

Measures the assignment error matrix for each qubit by preparing
known basis states and measuring the confusion probabilities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReadoutErrorExperimentResult:
    """Readout error result for a single qubit."""

    qubit: int
    error_rate_0to1: float  # P(measure 1 | prepared 0)
    error_rate_1to0: float  # P(measure 0 | prepared 1)
    total_error: float      # Average assignment error
    job_id: str | None = None


def build_readout_circuits(
    qubits: list[int],
) -> tuple[list[Any], dict[str, Any]]:
    """Build readout calibration circuits.

    For each qubit, creates two circuits:
    - Prepare |0⟩ and measure (identity circuit)
    - Prepare |1⟩ and measure (X gate then measure)

    Args:
        qubits: Physical qubit indices.

    Returns:
        Tuple of (circuits, metadata).
    """
    from qiskit.circuit import QuantumCircuit

    circuits: list[Any] = []
    metadata: dict[str, Any] = {
        "qubits": qubits,
        "circuit_map": [],  # (qubit, prepared_state)
    }

    for qubit in qubits:
        # Prepare |0⟩
        qc0 = QuantumCircuit(1, 1, name=f"readout_q{qubit}_prep0")
        qc0.measure(0, 0)
        qc0.metadata = {"qubit": qubit, "prepared_state": 0}
        circuits.append(qc0)
        metadata["circuit_map"].append((qubit, 0))

        # Prepare |1⟩
        qc1 = QuantumCircuit(1, 1, name=f"readout_q{qubit}_prep1")
        qc1.x(0)
        qc1.measure(0, 0)
        qc1.metadata = {"qubit": qubit, "prepared_state": 1}
        circuits.append(qc1)
        metadata["circuit_map"].append((qubit, 1))

    logger.info("Built %d readout calibration circuits for %d qubits", len(circuits), len(qubits))
    return circuits, metadata


def analyze_readout_results(
    counts_list: list[dict[str, int]],
    qubits: list[int],
    shots: int,
) -> list[ReadoutErrorExperimentResult]:
    """Analyze readout calibration counts.

    Args:
        counts_list: Counts per circuit (2 per qubit: prep|0⟩, prep|1⟩).
        qubits: Physical qubit indices.
        shots: Shots per circuit.

    Returns:
        List of ReadoutErrorExperimentResult, one per qubit.
    """
    results: list[ReadoutErrorExperimentResult] = []

    for q_idx, qubit in enumerate(qubits):
        # Prep |0⟩ circuit
        counts_prep0 = counts_list[q_idx * 2]
        # Prep |1⟩ circuit
        counts_prep1 = counts_list[q_idx * 2 + 1]

        # P(measure 1 | prepared 0) — false positive
        error_0to1 = counts_prep0.get("1", 0) / shots
        # P(measure 0 | prepared 1) — false negative
        error_1to0 = counts_prep1.get("0", 0) / shots
        total_error = (error_0to1 + error_1to0) / 2.0

        results.append(ReadoutErrorExperimentResult(
            qubit=qubit,
            error_rate_0to1=error_0to1,
            error_rate_1to0=error_1to0,
            total_error=total_error,
        ))
        logger.info(
            "Qubit %d readout error: 0→1=%.4f, 1→0=%.4f, avg=%.4f",
            qubit, error_0to1, error_1to0, total_error,
        )

    return results
