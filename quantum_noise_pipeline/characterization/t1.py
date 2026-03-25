"""T1 relaxation time characterization.

Measures the energy relaxation time (T1) of qubits by preparing |1⟩,
waiting a variable delay, and measuring the probability of remaining
in |1⟩. Fits an exponential decay to extract T1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from scipy.optimize import curve_fit

logger = logging.getLogger(__name__)


@dataclass
class T1ExperimentResult:
    """Result of a single-qubit T1 experiment."""

    qubit: int
    t1_us: float
    t1_stderr: Optional[float]
    delays_us: list[float]
    survival_probabilities: list[float]
    fit_params: dict[str, float]
    job_id: Optional[str] = None


def _exp_decay(t: np.ndarray, a: float, t1: float, c: float) -> np.ndarray:
    """Exponential decay model: a * exp(-t/T1) + c."""
    return a * np.exp(-t / t1) + c


def build_t1_circuits(
    qubits: list[int],
    delays_us: list[float],
) -> tuple[list[Any], dict[str, Any]]:
    """Construct T1 measurement circuits for given qubits and delays.

    For each qubit and delay value, creates a circuit that:
    1. Applies X gate to prepare |1⟩
    2. Inserts a delay of the specified duration
    3. Measures the qubit

    Args:
        qubits: Physical qubit indices to characterize.
        delays_us: Delay times in microseconds.

    Returns:
        Tuple of (list of QuantumCircuits, metadata dict).
    """
    from qiskit.circuit import QuantumCircuit

    circuits: list[Any] = []
    metadata: dict[str, Any] = {
        "qubits": qubits,
        "delays_us": delays_us,
        "circuit_map": [],  # (qubit, delay_idx) for each circuit
    }

    for qubit in qubits:
        for i, delay in enumerate(delays_us):
            qc = QuantumCircuit(1, 1, name=f"t1_q{qubit}_d{i}")
            qc.x(0)
            # Delay in seconds (Qiskit uses dt units, but we use
            # seconds with the delay instruction for clarity)
            delay_sec = delay * 1e-6
            qc.delay(delay_sec, 0, unit="s")
            qc.measure(0, 0)
            # Store physical qubit mapping for transpiler
            qc.metadata = {"qubit": qubit, "delay_us": delay, "delay_idx": i}
            circuits.append(qc)
            metadata["circuit_map"].append((qubit, i))

    logger.info(
        "Built %d T1 circuits for %d qubits × %d delays",
        len(circuits), len(qubits), len(delays_us),
    )
    return circuits, metadata


def generate_delay_values(
    num_delays: int = 20,
    max_delay_us: float = 300.0,
) -> list[float]:
    """Generate logarithmically spaced delay values.

    Args:
        num_delays: Number of delay points.
        max_delay_us: Maximum delay in microseconds.

    Returns:
        List of delay values in microseconds.
    """
    # Start from 1 µs to avoid zero delay
    return list(np.linspace(1.0, max_delay_us, num_delays))


def analyze_t1_results(
    counts_list: list[dict[str, int]],
    qubits: list[int],
    delays_us: list[float],
    shots: int,
) -> list[T1ExperimentResult]:
    """Analyze raw measurement counts to extract T1 for each qubit.

    Args:
        counts_list: List of count dictionaries, one per circuit,
            ordered as (qubit0_delay0, qubit0_delay1, ..., qubit1_delay0, ...).
        qubits: Physical qubit indices.
        delays_us: Delay values in microseconds.
        shots: Number of shots per circuit.

    Returns:
        List of T1ExperimentResult, one per qubit.
    """
    num_delays = len(delays_us)
    results: list[T1ExperimentResult] = []
    delays_arr = np.array(delays_us)

    for q_idx, qubit in enumerate(qubits):
        # Extract survival probability P(|1⟩) for each delay
        survival_probs: list[float] = []
        for d_idx in range(num_delays):
            circuit_idx = q_idx * num_delays + d_idx
            counts = counts_list[circuit_idx]
            # Count measurements of |1⟩
            n_one = counts.get("1", 0)
            survival_probs.append(n_one / shots)

        probs_arr = np.array(survival_probs)

        # Fit exponential decay
        try:
            p0 = [probs_arr[0] - probs_arr[-1], max(delays_us) / 3, probs_arr[-1]]
            popt, pcov = curve_fit(
                _exp_decay, delays_arr, probs_arr,
                p0=p0,
                bounds=([0, 0.1, -0.5], [2.0, max(delays_us) * 10, 1.5]),
                maxfev=5000,
            )
            t1_fit = popt[1]
            t1_stderr = float(np.sqrt(pcov[1, 1])) if pcov is not None else None

            results.append(T1ExperimentResult(
                qubit=qubit,
                t1_us=float(t1_fit),
                t1_stderr=t1_stderr,
                delays_us=delays_us,
                survival_probabilities=survival_probs,
                fit_params={"amplitude": float(popt[0]), "t1": float(popt[1]), "offset": float(popt[2])},
            ))
            logger.info("Qubit %d: T1 = %.1f ± %.1f µs", qubit, t1_fit, t1_stderr or 0.0)

        except (RuntimeError, ValueError) as e:
            logger.warning("T1 fit failed for qubit %d: %s", qubit, e)
            results.append(T1ExperimentResult(
                qubit=qubit,
                t1_us=float("nan"),
                t1_stderr=None,
                delays_us=delays_us,
                survival_probabilities=survival_probs,
                fit_params={},
            ))

    return results
