# Quantum Circuit Noise Characterization & Compilation Optimization Pipeline

An automated pipeline for characterizing IBM Quantum hardware noise and benchmarking compilation strategies, with a focus on comparing [Infleqtion's Superstaq](https://superstaq.infleqtion.com/) compiler against Qiskit's default transpiler.

## What This Does

1.  Runs T1, T2, and readout error experiments on real IBM Quantum devices to measure qubit coherence and measurement fidelity.
2.  Compiles identical benchmark circuits (Bell state, GHZ, QFT, QAOA) through both Qiskit and Superstaq, then compares circuit depth, two-qubit gate count, and output fidelity on real hardware.
3.  A stateless runner submits and retrieves jobs on a daily cadence, accumulating longitudinal drift data.
4.  Plotly Dash app for exploring T1/T2 time series, gate fidelity heatmaps, and compiler comparison tables.

## Architecture

```
quantum_noise_pipeline/
├── characterization/    # T1, T2, readout error experiments
├── compilation/         # Qiskit vs Superstaq benchmarking
├── database/            # SQLAlchemy models + storage layer
├── scheduler/           # Automated job submission & retrieval
├── dashboard/           # Plotly Dash visualization
└── utils/               # IBM Quantum client wrapper
```

## Quick Start

### Prerequisites

- Python 3.10+
- [IBM Quantum account](https://quantum.ibm.com/) (free tier works)
- [Superstaq API key](https://superstaq.infleqtion.com/) (free trial available)

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/quantum-noise-pipeline.git
cd qNoise
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### Configuration

Set environment variables (or create a `.env` file):

```bash
export IBM_QUANTUM_TOKEN="your_ibm_token_here"
export SUPERSTAQ_API_TOKEN="your_superstaq_token_here"
export IBM_QUANTUM_BACKEND="ibm_brisbane"  # optional, this is the default
```

### Run Tests

```bash
pytest tests/ -v
```

Tests are fully mocked and do not require API credentials or hardware access.

### Run a Characterization Batch

```bash
python scripts/run_daily.py
```

### Launch the Dashboard

```bash
python -m quantum_noise_pipeline.dashboard.app
```

## Compilation Benchmark Results

*Results will be populated here as data accumulates from daily automated runs.*

| Circuit | Compiler | Depth | 2Q Gates | Fidelity |
|---------|----------|-------|----------|----------|
| Bell State | Qiskit (O3) | — | — | — |
| Bell State | Superstaq | — | — | — |
| QFT (4q) | Qiskit (O3) | — | — | — |
| QFT (4q) | Superstaq | — | — | — |

## Stack

- **Qiskit 2.3+** — Circuit construction and transpilation
- **qiskit-ibm-runtime 0.45+** — IBM Quantum cloud access (SamplerV2)
- **qiskit-superstaq 0.5+** — Infleqtion's Superstaq compiler
- **SQLAlchemy 2.0** — Structured results database
- **Plotly Dash** — Interactive visualization
- **pytest** — Unit tests with mocked hardware calls
- **GitHub Actions** — CI/CD (lint, type check, test)

## Project Status

- [x] Repository structure and CI pipeline
- [x] T1/T2/readout characterization circuits and analysis
- [x] Compilation benchmark circuit library
- [x] SQLite database with typed ORM models
- [x] Automated scheduler (run_daily.py)
- [x] Full test suite (mocked, no hardware needed)
- [ ] Superstaq integration testing on real hardware
- [ ] Randomized benchmarking module
- [ ] Dashboard with accumulated data
- [ ] Longitudinal drift analysis write-up

## License

MIT
