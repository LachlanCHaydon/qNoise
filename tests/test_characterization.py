"""Tests for characterization modules.

All IBM Quantum API calls are mocked — these tests run without
any hardware access or API credentials.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantum_noise_pipeline.characterization.t1 import (
    T1ExperimentResult,
    analyze_t1_results,
    build_t1_circuits,
    generate_delay_values,
)
from quantum_noise_pipeline.characterization.t2 import (
    T2ExperimentResult,
    analyze_t2_results,
    build_t2_circuits,
    generate_delay_values as t2_generate_delays,
)
from quantum_noise_pipeline.characterization.readout_error import (
    ReadoutErrorExperimentResult,
    analyze_readout_results,
    build_readout_circuits,
)


# ── T1 tests ──────────────────────────────────────────────────────


class TestT1DelayGeneration:
    def test_correct_count(self) -> None:
        delays = generate_delay_values(num_delays=15, max_delay_us=200.0)
        assert len(delays) == 15

    def test_starts_at_one(self) -> None:
        delays = generate_delay_values(num_delays=10, max_delay_us=100.0)
        assert delays[0] == pytest.approx(1.0)

    def test_ends_at_max(self) -> None:
        delays = generate_delay_values(num_delays=10, max_delay_us=250.0)
        assert delays[-1] == pytest.approx(250.0)

    def test_monotonically_increasing(self) -> None:
        delays = generate_delay_values(num_delays=20, max_delay_us=300.0)
        for i in range(1, len(delays)):
            assert delays[i] > delays[i - 1]


class TestT1CircuitBuilding:
    def test_circuit_count(self) -> None:
        qubits = [0, 1, 2]
        delays = [10.0, 50.0, 100.0]
        circuits, metadata = build_t1_circuits(qubits, delays)
        assert len(circuits) == len(qubits) * len(delays)

    def test_metadata_structure(self) -> None:
        qubits = [0, 3]
        delays = [10.0, 20.0]
        circuits, metadata = build_t1_circuits(qubits, delays)
        assert metadata["qubits"] == qubits
        assert metadata["delays_us"] == delays
        assert len(metadata["circuit_map"]) == len(circuits)

    def test_circuit_has_measurement(self) -> None:
        circuits, _ = build_t1_circuits([0], [10.0])
        qc = circuits[0]
        op_names = [inst.operation.name for inst in qc.data]
        assert "measure" in op_names

    def test_circuit_starts_with_x(self) -> None:
        circuits, _ = build_t1_circuits([0], [10.0])
        qc = circuits[0]
        assert qc.data[0].operation.name == "x"


class TestT1Analysis:
    def _make_synthetic_counts(
        self,
        qubits: list[int],
        delays_us: list[float],
        t1_true: float,
        shots: int,
    ) -> list[dict[str, int]]:
        """Generate synthetic counts from an ideal exponential decay."""
        rng = np.random.default_rng(42)
        counts_list: list[dict[str, int]] = []
        for _ in qubits:
            for delay in delays_us:
                prob_one = 0.95 * np.exp(-delay / t1_true) + 0.02
                n_one = int(rng.binomial(shots, min(prob_one, 1.0)))
                counts_list.append({"0": shots - n_one, "1": n_one})
        return counts_list

    def test_fit_recovers_t1(self) -> None:
        qubits = [0]
        delays = list(np.linspace(1.0, 300.0, 20))
        shots = 4096
        t1_true = 100.0

        counts = self._make_synthetic_counts(qubits, delays, t1_true, shots)
        results = analyze_t1_results(counts, qubits, delays, shots)

        assert len(results) == 1
        assert isinstance(results[0], T1ExperimentResult)
        assert abs(results[0].t1_us - t1_true) / t1_true < 0.3

    def test_multiple_qubits(self) -> None:
        qubits = [0, 1, 2]
        delays = list(np.linspace(1.0, 200.0, 15))
        shots = 2048
        counts = self._make_synthetic_counts(qubits, delays, 80.0, shots)
        results = analyze_t1_results(counts, qubits, delays, shots)
        assert len(results) == 3
        for r in results:
            assert not np.isnan(r.t1_us)


# ── T2 tests ──────────────────────────────────────────────────────


class TestT2CircuitBuilding:
    def test_circuit_count(self) -> None:
        qubits = [0, 1]
        delays = [10.0, 50.0]
        circuits, _ = build_t2_circuits(qubits, delays)
        assert len(circuits) == 4

    def test_hahn_echo_structure(self) -> None:
        circuits, _ = build_t2_circuits([0], [20.0])
        qc = circuits[0]
        op_names = [inst.operation.name for inst in qc.data]
        assert op_names[0] == "h"
        assert "x" in op_names
        assert op_names.count("h") == 2
        assert "measure" in op_names


class TestT2Analysis:
    def test_fit_with_synthetic_data(self) -> None:
        qubits = [0]
        delays = list(np.linspace(1.0, 200.0, 20))
        shots = 4096
        t2_true = 60.0

        rng = np.random.default_rng(123)
        counts_list: list[dict[str, int]] = []
        for delay in delays:
            prob_zero = 0.9 * np.exp(-delay / t2_true) + 0.05
            n_zero = int(rng.binomial(shots, min(prob_zero, 1.0)))
            counts_list.append({"0": n_zero, "1": shots - n_zero})

        results = analyze_t2_results(counts_list, qubits, delays, shots)
        assert len(results) == 1
        assert abs(results[0].t2_us - t2_true) / t2_true < 0.3


# ── Readout error tests ──────────────────────────────────────────


class TestReadoutCircuitBuilding:
    def test_two_circuits_per_qubit(self) -> None:
        qubits = [0, 1, 3]
        circuits, metadata = build_readout_circuits(qubits)
        assert len(circuits) == 6

    def test_prep0_has_no_x_gate(self) -> None:
        circuits, _ = build_readout_circuits([0])
        prep0 = circuits[0]
        op_names = [inst.operation.name for inst in prep0.data]
        assert "x" not in op_names

    def test_prep1_has_x_gate(self) -> None:
        circuits, _ = build_readout_circuits([0])
        prep1 = circuits[1]
        op_names = [inst.operation.name for inst in prep1.data]
        assert "x" in op_names


class TestReadoutAnalysis:
    def test_perfect_readout(self) -> None:
        qubits = [0]
        shots = 1000
        counts = [
            {"0": 1000, "1": 0},
            {"0": 0, "1": 1000},
        ]
        results = analyze_readout_results(counts, qubits, shots)
        assert results[0].error_rate_0to1 == 0.0
        assert results[0].error_rate_1to0 == 0.0

    def test_noisy_readout(self) -> None:
        qubits = [0]
        shots = 1000
        counts = [
            {"0": 950, "1": 50},
            {"0": 30, "1": 970},
        ]
        results = analyze_readout_results(counts, qubits, shots)
        assert results[0].error_rate_0to1 == pytest.approx(0.05)
        assert results[0].error_rate_1to0 == pytest.approx(0.03)
        assert results[0].total_error == pytest.approx(0.04)
