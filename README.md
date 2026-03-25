# Quantum Circuit Noise Characterization & Compilation Optimization Pipeline

An automated pipeline for characterizing IBM Quantum hardware noise and benchmarking compilation strategies, with a focus on comparing [Infleqtion's Superstaq](https://superstaq.infleqtion.com/) compiler against Qiskit's default transpiler.

**Built by Lachlan Haydon** — Senior Physics & Information Systems student at Loyola University Chicago (graduating May 2026).

## What This Does

1. **Characterizes real quantum hardware** — Runs T1 (energy relaxation), T2 (coherence), and readout error experiments on IBM Quantum devices to measure qubit noise properties.
2. **Benchmarks two compilers head-to-head** — Compiles identical circuits through both Qiskit (optimization level 3) and Superstaq, then runs them on the same hardware to compare output fidelity.
3. **Tracks temporal noise drift** — A stateless runner submits and retrieves jobs on a daily cadence, revealing how qubit properties change over hours.
4. **Visualizes everything** — Plotly Dash app for exploring T1/T2 time series and compiler comparison tables.

## Key Finding: 2-Qubit Gate Count Beats Circuit Depth

On QFT-4q, Superstaq produced a *deeper* circuit (82 vs 60) with *more* total gates (154 vs 81) — but achieved **higher hardware fidelity** (0.9970 vs 0.9914) because it used **2 fewer two-qubit gates** (16 vs 18).

Two-qubit gates have ~10× higher error rates than single-qubit gates on superconducting hardware. Superstaq's optimizer prioritizes minimizing 2Q gates even at the cost of more single-qubit overhead — and the hardware validates that tradeoff.

## Empirical Results

All data collected on **ibm_fez** (156-qubit IBM Heron processor, Washington DC) on March 25, 2026.

### Compilation Benchmark — Qiskit vs Superstaq

| Circuit | Compiler | Depth | 2Q Gates | Total Gates | Fidelity | Winner |
|---------|----------|-------|----------|-------------|----------|--------|
| Bell State | Qiskit (O3) | 7 | 1 | 9 | 0.9726 | |
| Bell State | Superstaq | **6** | 1 | 8 | **0.9791** | Superstaq |
| GHZ-4q | Qiskit (O3) | 13 | 3 | 21 | **0.9521** | Qiskit |
| GHZ-4q | Superstaq | **10** | 3 | 22 | 0.9472 | |
| QFT-4q | Qiskit (O3) | **60** | 18 | 81 | 0.9914 | |
| QFT-4q | Superstaq | 82 | **16** | 154 | **0.9970** | Superstaq |
| QAOA-4q | Qiskit (O3) | **48** | 11 | 77 | — | |
| QAOA-4q | Superstaq | 59 | 11 | 113 | — | |

**Scorecard: Superstaq 2 – Qiskit 1** (by hardware fidelity)

### Qubit Characterization — Temporal Drift

Two characterization runs ~2.5 hours apart reveal significant noise drift:

| Qubit | T1 (Run 1) | T1 (Run 2) | Change | T2 (Run 1) | T2 (Run 2) |
|-------|-----------|-----------|--------|-----------|-----------|
| 0 | 38.4 ± 1.6 µs | 22.9 ± 0.6 µs | **−40%** | 42.8 ± 11.1 µs | 18.3 ± 1.3 µs |
| 1 | 186.5 ± 17.7 µs | 155.6 ± 12.9 µs | −17% | 257.3 ± 82.0 µs | 148.9 ± 28.7 µs |
| 2 | 60.7 ± 4.9 µs | 177.1 ± 14.3 µs | **+192%** | 51.2 ± 1.8 µs | 82.8 ± 7.3 µs |

**Qubit 2's T1 tripled in 2.5 hours** (60.7 → 177.1 µs), going from worst to best. This demonstrates why continuous characterization matters — a compiler that picks qubits based on stale calibration data may route circuits to the wrong qubits.

### Readout Errors

| Qubit | P(1\|prep 0) | P(0\|prep 1) | Total Error |
|-------|-------------|-------------|-------------|
| 0 | 0.10% | 2.54% | 1.32% |
| 1 | 1.56% | 3.12% | 2.34% |
| 2 | 0.39% | 0.59% | 0.49% |

All readout errors under 4% — consistent with state-of-the-art superconducting hardware. Readout errors were stable across runs (unlike T1/T2), suggesting they are dominated by classical electronics rather than qubit coherence.

## Architecture

```
quantum_noise_pipeline/
├── characterization/    # T1, T2, readout error experiments
├── compilation/         # Qiskit vs Superstaq benchmarking
├── database/            # SQLAlchemy models + storage layer
├── scheduler/           # Automated job submission & retrieval
├── dashboard/           # Plotly Dash visualization
└── utils/               # IBM Quantum client wrapper

scripts/
├── submit_minimal_test.py          # Conservative hardware submission
├── retrieve_results.py             # Pull characterization data
├── run_compilation_benchmark.py    # Head-to-head compiler comparison
├── retrieve_benchmark_results.py   # Pull benchmark fidelity data
├── dry_run_hardware.py             # Pre-flight validation (no credits)
└── verify_connections.py           # Test IBM + Superstaq connections
```

## Quick Start

### Prerequisites

- Python 3.10+
- [IBM Quantum account](https://quantum.ibm.com/) (free tier works)
- [Superstaq API key](https://superstaq.infleqtion.com/) (free trial available)

### Installation

```bash
git clone https://github.com/LachlanCHaydon/qNoise.git
cd qNoise
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pip install python-dotenv
```

### Configuration

Create a `.env` file in the project root:

```bash
IBM_QUANTUM_TOKEN=your_ibm_token_here
IBM_QUANTUM_CHANNEL=ibm_quantum_platform
IBM_QUANTUM_INSTANCE=your_crn_instance_here
IBM_QUANTUM_BACKEND=ibm_fez
SUPERSTAQ_API_TOKEN=your_superstaq_token_here
```

> **Note:** Use `ibm_quantum_platform` (not the sunset `ibm_quantum` channel). Your instance is a CRN string — run `python scripts/verify_connections.py` to auto-discover it.

### Validate Setup (No Credits)

```bash
python scripts/dry_run_hardware.py
```

This tests IBM connection, circuit building, transpilation, Superstaq dry-run, and database — all without submitting hardware jobs.

### Run Characterization

```bash
python scripts/submit_minimal_test.py     # Submit to hardware
python scripts/retrieve_results.py        # Pull results when complete
```

### Run Compilation Benchmark

```bash
python scripts/run_compilation_benchmark.py        # Compile + submit
python scripts/retrieve_benchmark_results.py       # Pull fidelity results
```

### Run Tests

```bash
pytest tests/ -v
```

41 tests, all fully mocked — no API credentials or hardware access needed.

## Stack

- **Qiskit 2.3+** — Circuit construction and transpilation
- **qiskit-ibm-runtime 0.46+** — IBM Quantum cloud access (SamplerV2)
- **qiskit-superstaq 0.5+** — Infleqtion's Superstaq compiler
- **SQLAlchemy 2.0** — Structured results database (SQLite)
- **scipy** — Exponential decay curve fitting for T1/T2
- **Plotly Dash** — Interactive visualization
- **pytest** — Unit tests with mocked hardware calls
- **GitHub Actions** — CI/CD (ruff lint, mypy type check, pytest across Python 3.10–3.12)

## Project Status

- [x] Repository structure and CI pipeline
- [x] T1/T2/readout characterization circuits and analysis
- [x] Compilation benchmark circuit library (Bell, GHZ, QFT, QAOA)
- [x] SQLite database with typed ORM models
- [x] Automated scheduler for daily runs
- [x] Full test suite (41 tests, mocked)
- [x] IBM Quantum hardware validation on ibm_fez
- [x] Superstaq vs Qiskit compilation benchmark with real fidelity data
- [x] Temporal noise drift characterization (2 runs)
- [ ] Randomized benchmarking module
- [ ] Dashboard with accumulated data
- [ ] Longitudinal drift analysis (multi-day)
- [ ] Results analysis notebook with figures

## License

MIT
