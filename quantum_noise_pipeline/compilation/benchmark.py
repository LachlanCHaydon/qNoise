"""Compilation benchmarking: Qiskit default vs Superstaq.

Provides benchmark circuits and comparison logic for evaluating
compilation quality across compilers on real hardware.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from qiskit.circuit import QuantumCircuit

logger = logging.getLogger(__name__)


@dataclass
class CircuitMetrics:
    """Metrics extracted from a compiled circuit."""

    depth: int
    total_gate_count: int
    two_qubit_gate_count: int
    gate_count_by_type: dict[str, int]


@dataclass
class CompilationResult:
    """Result of compiling a circuit through one compiler."""

    compiler_name: str
    circuit_name: str
    original_depth: int
    metrics: CircuitMetrics
    compiled_circuit: Any  # QuantumCircuit


def extract_circuit_metrics(circuit: QuantumCircuit) -> CircuitMetrics:
    """Extract gate count and depth metrics from a compiled circuit.

    Args:
        circuit: A transpiled/compiled QuantumCircuit.

    Returns:
        CircuitMetrics with depth, gate counts, and breakdown.
    """
    gate_counts: dict[str, int] = {}
    two_qubit_count = 0

    for instruction in circuit.data:
        gate_name = instruction.operation.name
        if gate_name in ("barrier", "measure"):
            continue
        gate_counts[gate_name] = gate_counts.get(gate_name, 0) + 1
        if instruction.operation.num_qubits == 2:
            two_qubit_count += 1

    total = sum(gate_counts.values())
    return CircuitMetrics(
        depth=circuit.depth(),
        total_gate_count=total,
        two_qubit_gate_count=two_qubit_count,
        gate_count_by_type=gate_counts,
    )


# ── Benchmark circuit library ─────────────────────────────────────


def make_bell_state_circuit() -> QuantumCircuit:
    """Simple Bell state: H-CNOT on 2 qubits."""
    qc = QuantumCircuit(2, 2, name="bell_state")
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


def make_ghz_circuit(n_qubits: int = 4) -> QuantumCircuit:
    """GHZ state: creates maximal entanglement across n qubits."""
    qc = QuantumCircuit(n_qubits, n_qubits, name=f"ghz_{n_qubits}q")
    qc.h(0)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def make_qft_circuit(n_qubits: int = 4) -> QuantumCircuit:
    """Quantum Fourier Transform on n qubits."""
    qc = QuantumCircuit(n_qubits, n_qubits, name=f"qft_{n_qubits}q")

    for i in range(n_qubits):
        qc.h(i)
        for j in range(i + 1, n_qubits):
            angle = 3.14159265 / (2 ** (j - i))
            qc.cp(angle, j, i)

    # Swap qubits for standard QFT ordering
    for i in range(n_qubits // 2):
        qc.swap(i, n_qubits - i - 1)

    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def make_qaoa_maxcut_circuit(n_qubits: int = 4, p: int = 1) -> QuantumCircuit:
    """Single-layer QAOA for MaxCut on a ring graph.

    Args:
        n_qubits: Number of qubits (nodes in the ring).
        p: Number of QAOA layers.

    Returns:
        Parameterized QAOA circuit with fixed angles (gamma=0.5, beta=0.3).
    """
    import numpy as np

    gamma = 0.5
    beta = 0.3

    qc = QuantumCircuit(n_qubits, n_qubits, name=f"qaoa_maxcut_{n_qubits}q_p{p}")

    # Initial superposition
    for i in range(n_qubits):
        qc.h(i)

    for _ in range(p):
        # Problem unitary (ring edges)
        for i in range(n_qubits):
            j = (i + 1) % n_qubits
            qc.cx(i, j)
            qc.rz(2 * gamma, j)
            qc.cx(i, j)

        # Mixer unitary
        for i in range(n_qubits):
            qc.rx(2 * beta, i)

    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def get_benchmark_circuits() -> dict[str, QuantumCircuit]:
    """Return the full set of benchmark circuits.

    Returns:
        Dictionary mapping circuit name to QuantumCircuit.
    """
    return {
        "bell_state": make_bell_state_circuit(),
        "ghz_4q": make_ghz_circuit(4),
        "qft_4q": make_qft_circuit(4),
        "qaoa_maxcut_4q": make_qaoa_maxcut_circuit(4),
    }


# ── Qiskit compilation ────────────────────────────────────────────


def compile_with_qiskit(
    circuit: QuantumCircuit,
    backend: Any,
    optimization_level: int = 3,
) -> CompilationResult:
    """Compile a circuit using Qiskit's default transpiler.

    Args:
        circuit: Input circuit.
        backend: IBM backend for target topology.
        optimization_level: Qiskit optimization level (0-3).

    Returns:
        CompilationResult with metrics.
    """
    from qiskit import transpile

    original_depth = circuit.depth()
    compiled = transpile(
        circuit,
        backend=backend,
        optimization_level=optimization_level,
    )
    metrics = extract_circuit_metrics(compiled)

    logger.info(
        "Qiskit compiled '%s': depth %d→%d, 2q gates=%d",
        circuit.name, original_depth, metrics.depth, metrics.two_qubit_gate_count,
    )
    return CompilationResult(
        compiler_name="qiskit",
        circuit_name=circuit.name or "unnamed",
        original_depth=original_depth,
        metrics=metrics,
        compiled_circuit=compiled,
    )


# ── Superstaq compilation ─────────────────────────────────────────


def compile_with_superstaq(
    circuit: QuantumCircuit,
    provider: Any,
    target: str,
) -> CompilationResult:
    """Compile a circuit using Superstaq's optimizer.

    Args:
        circuit: Input circuit.
        provider: SuperstaqProvider instance.
        target: Target backend string (e.g. "ibmq_brisbane_qpu").

    Returns:
        CompilationResult with metrics.
    """
    original_depth = circuit.depth()

    compiler_output = provider.ibmq_compile(circuit, target=target)
    compiled = compiler_output.circuit

    metrics = extract_circuit_metrics(compiled)

    logger.info(
        "Superstaq compiled '%s': depth %d→%d, 2q gates=%d",
        circuit.name, original_depth, metrics.depth, metrics.two_qubit_gate_count,
    )
    return CompilationResult(
        compiler_name="superstaq",
        circuit_name=circuit.name or "unnamed",
        original_depth=original_depth,
        metrics=metrics,
        compiled_circuit=compiled,
    )
