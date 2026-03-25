"""Tests for compilation benchmarking module.

Tests circuit generation and metrics extraction. Actual compilation
against IBM/Superstaq backends is mocked.
"""

from __future__ import annotations

import pytest

from quantum_noise_pipeline.compilation.benchmark import (
    CircuitMetrics,
    extract_circuit_metrics,
    get_benchmark_circuits,
    make_bell_state_circuit,
    make_ghz_circuit,
    make_qaoa_maxcut_circuit,
    make_qft_circuit,
)


class TestBenchmarkCircuits:
    def test_bell_state_structure(self) -> None:
        qc = make_bell_state_circuit()
        assert qc.num_qubits == 2
        assert qc.num_clbits == 2
        op_names = [inst.operation.name for inst in qc.data]
        assert "h" in op_names
        assert "cx" in op_names
        assert "measure" in op_names

    def test_ghz_qubit_count(self) -> None:
        for n in [3, 4, 6]:
            qc = make_ghz_circuit(n)
            assert qc.num_qubits == n
            # GHZ needs n-1 CNOT gates
            cx_count = sum(
                1 for inst in qc.data if inst.operation.name == "cx"
            )
            assert cx_count == n - 1

    def test_qft_qubit_count(self) -> None:
        qc = make_qft_circuit(4)
        assert qc.num_qubits == 4
        assert qc.num_clbits == 4

    def test_qaoa_has_rx_and_rz(self) -> None:
        qc = make_qaoa_maxcut_circuit(4, p=1)
        op_names = {inst.operation.name for inst in qc.data}
        assert "rx" in op_names
        assert "rz" in op_names
        assert "cx" in op_names

    def test_get_benchmark_circuits_returns_all(self) -> None:
        circuits = get_benchmark_circuits()
        assert "bell_state" in circuits
        assert "ghz_4q" in circuits
        assert "qft_4q" in circuits
        assert "qaoa_maxcut_4q" in circuits
        assert len(circuits) == 4


class TestMetricsExtraction:
    def test_bell_state_metrics(self) -> None:
        qc = make_bell_state_circuit()
        metrics = extract_circuit_metrics(qc)
        assert isinstance(metrics, CircuitMetrics)
        assert metrics.two_qubit_gate_count == 1  # one CX
        assert metrics.total_gate_count >= 2  # at least H + CX
        assert metrics.depth > 0

    def test_ghz_two_qubit_count(self) -> None:
        qc = make_ghz_circuit(5)
        metrics = extract_circuit_metrics(qc)
        assert metrics.two_qubit_gate_count == 4  # 5-1 CX gates

    def test_gate_count_by_type(self) -> None:
        qc = make_bell_state_circuit()
        metrics = extract_circuit_metrics(qc)
        assert "h" in metrics.gate_count_by_type
        assert "cx" in metrics.gate_count_by_type
        # measure and barrier should be excluded
        assert "measure" not in metrics.gate_count_by_type

    def test_empty_circuit(self) -> None:
        from qiskit.circuit import QuantumCircuit
        qc = QuantumCircuit(2)
        metrics = extract_circuit_metrics(qc)
        assert metrics.total_gate_count == 0
        assert metrics.two_qubit_gate_count == 0
