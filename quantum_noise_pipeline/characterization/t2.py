"""T2 coherence time characterization (Hahn echo).

Measures the dephasing time (T2) using a Hahn echo sequence:
  |0⟩ → H → delay/2 → X → delay/2 → H → measure
The X gate refocuses static noise, isolating T2 from T2*.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from scipy.optimize import curve_fit

logger = logging.getLogger(__name__)


@dataclass
class T2ExperimentResult:
    """Result of a single-qubit T2 experiment."""

    qubit: int
    t2_us: float
    t2_stderr: Optional[float]
    delays_us: list[float]
    survival_probabilities: list[float]
    fit_params: dict[str, float]
    job_id: Optional[str] = None


def _exp_decay(t: np.ndarray, a: float, t2: float, c: float) -> np.ndarray:
    """Exponential decay model: a * exp(-t/T2) + c."""
    return a * np.exp(-t / t2) + c


def build_t2_circuits(
    qubits: list[int],
    delays_us: list[float],
) -> tuple[list[Any], dict[str, Any]]:
    """Construct Hahn echo T2 circuits.

    For each qubit and total delay:
    1. H gate (create superposition)
    2. delay/2
    3. X gate (echo refocusing pulse)
    4. delay/2
    5. H gate
    6. Measure

    Args:
        qubits: Physical qubit indices.
        delays_us: Total delay times in microseconds.

    Returns:
        Tuple of (circuits, metadata).
    """
    from qiskit.circuit import QuantumCircuit

    circuits: list[Any] = []
    metadata: dict[str, Any] = {
        "qubits": qubits,
        "delays_us": delays_us,
        "circuit_map": [],
    }

    for qubit in qubits:
        for i, delay in enumerate(delays_us):
            qc = QuantumCircuit(1, 1, name=f"t2_q{qubit}_d{i}")
            half_delay_sec = (delay / 2.0) * 1e-6

            qc.h(0)
            qc.delay(half_delay_sec, 0, unit="s")
            qc.x(0)  # Echo pulse
            qc.delay(half_delay_sec, 0, unit="s")
            qc.h(0)
            qc.measure(0, 0)

            qc.metadata = {"qubit": qubit, "delay_us": delay, "delay_idx": i}
            circuits.append(qc)
            metadata["circuit_map"].append((qubit, i))

    logger.info(
        "Built %d T2 circuits for %d qubits × %d delays",
        len(circuits), len(qubits), len(delays_us),
    )
    return circuits, metadata


def generate_delay_values(
    num_delays: int = 20,
    max_delay_us: float = 200.0,
) -> list[float]:
    """Generate linearly spaced delay values for T2 experiment.

    Args:
        num_delays: Number of delay points.
        max_delay_us: Maximum total delay in microseconds.

    Returns:
        List of delay values in microseconds.
    """
    return list(np.linspace(1.0, max_delay_us, num_delays))


def analyze_t2_results(
    counts_list: list[dict[str, int]],
    qubits: list[int],
    delays_us: list[float],
    shots: int,
) -> list[T2ExperimentResult]:
    """Analyze Hahn echo measurement counts to extract T2.

    For a perfect Hahn echo, P(|0⟩) decays as exp(-t/T2).

    Args:
        counts_list: Measurement counts per circuit.
        qubits: Physical qubit indices.
        delays_us: Delay values in microseconds.
        shots: Shots per circuit.

    Returns:
        List of T2ExperimentResult, one per qubit.
    """
    num_delays = len(delays_us)
    results: list[T2ExperimentResult] = []
    delays_arr = np.array(delays_us)

    for q_idx, qubit in enumerate(qubits):
        survival_probs: list[float] = []
        for d_idx in range(num_delays):
            circuit_idx = q_idx * num_delays + d_idx
            counts = counts_list[circuit_idx]
            # For Hahn echo, P(|0⟩) decays with T2
            n_zero = counts.get("0", 0)
            survival_probs.append(n_zero / shots)

        probs_arr = np.array(survival_probs)

        try:
            p0 = [probs_arr[0] - probs_arr[-1], max(delays_us) / 3, probs_arr[-1]]
            max_delay = max(delays_us)
            popt, pcov = curve_fit(
                _exp_decay, delays_arr, probs_arr,
                p0=p0,
                bounds=([0, 0.1, -0.5], [2.0, max_delay * 10, 1.5]),
                maxfev=5000,
            )
            t2_fit = popt[1]
            t2_stderr = float(np.sqrt(pcov[1, 1])) if pcov is not None else None

            results.append(T2ExperimentResult(
                qubit=qubit,
                t2_us=float(t2_fit),
                t2_stderr=t2_stderr,
                delays_us=delays_us,
                survival_probabilities=survival_probs,
                fit_params={"amplitude": float(popt[0]), "t2": float(popt[1]), "offset": float(popt[2])},
            ))
            logger.info("Qubit %d: T2 = %.1f ± %.1f µs", qubit, t2_fit, t2_stderr or 0.0)

        except (RuntimeError, ValueError) as e:
            logger.warning("T2 fit failed for qubit %d: %s", qubit, e)
            results.append(T2ExperimentResult(
                qubit=qubit,
                t2_us=float("nan"),
                t2_stderr=None,
                delays_us=delays_us,
                survival_probabilities=survival_probs,
                fit_params={},
            ))

    return results
