# Quantum Noise Pipeline: Characterizing Real Qubits on IBM's 156-Qubit ibm_fez

*A portfolio project by a senior Physics + Information Systems student at Loyola University Chicago, built to demonstrate quantum engineering skills for Infleqtion's internship program.*

---

## The Problem with Quantum Computers: They're Noisy, and That's Fascinating

Here's a thought experiment. Imagine you're trying to build a computer out of soap bubbles. Each bubble can represent a 0 or a 1 — and it can even represent *both at the same time* (that's the quantum part). But soap bubbles don't stay intact for long. The slightest breath of air, the tiniest vibration in the floor, even thermal radiation from the walls of the room can pop them before you've finished your calculation. That's approximately what it's like to work with real quantum hardware.

Quantum computers have been theoretically spectacular for decades. Shor's algorithm would crack RSA encryption. Grover's algorithm speeds up database search. Quantum chemistry simulations could redesign pharmaceuticals from first principles. The catch: all of these algorithms assume qubits that stay coherent — that hold their quantum state — for long enough to actually finish computing. Real qubits don't do that. They decay. They dephase. They get measured wrong. And the rates at which all of this happens vary qubit by qubit, device by device, and *day by day* on the same physical chip.

This project is about measuring that noise, systematically, on real IBM Quantum hardware — and then benchmarking whether better compilation can help work around it.

---

## What Is a Qubit, Actually?

If you've heard the word "qubit" but mostly in the context of "it's like a bit but quantum," let me give you the physical picture.

A classical bit is a voltage level. High voltage = 1, low voltage = 0. It's binary, it's stable, and it's deterministic. We've spent 70 years engineering those voltage levels to be *extremely* stable.

A qubit is a two-level quantum system. On IBM's superconducting processors — which is what we're using here — each qubit is a tiny superconducting circuit called a **transmon**, roughly 100 microns across, cooled to about 15 millikelvin (colder than outer space). The two energy levels of this circuit — call them |0⟩ and |1⟩ — are separated by a microwave frequency, typically around 5 GHz. We manipulate the qubit by hitting it with carefully shaped microwave pulses.

The quantum magic: a qubit can be in a *superposition* of |0⟩ and |1⟩ simultaneously. Mathematically, its state is |ψ⟩ = α|0⟩ + β|1⟩, where α and β are complex numbers whose squared magnitudes sum to 1. This superposition is what gives quantum computers their (potential) power — but it is also what makes them fragile.

**The qubit wants to interact with its environment.** Heat flows in from the walls. The transmon circuit has imperfections. Stray electromagnetic fields from nearby qubits, control electronics, and cosmic rays all conspire to disturb the quantum state. The moment the qubit "leaks" information about its state into the environment, the superposition is destroyed in a process called **decoherence**. Decoherence is the enemy of quantum computation.

So what we're measuring in this project is: *how fast does decoherence happen, and in what ways?*

---

## The Three Noise Metrics This Pipeline Measures

### T1: Energy Relaxation Time

Think of T1 as the "battery life" of a qubit. If you put a qubit in its excited state |1⟩ and then wait, it will eventually relax back to its ground state |0⟩. This happens because the qubit leaks energy into its environment — the microwave photon it was "holding" gets absorbed by the surrounding circuit, the substrate, or radiated away.

The decay follows an exponential curve. If you measure P(still in |1⟩) at various times t after preparing |1⟩, you get:

```
P(|1⟩, t) = A · exp(-t / T1) + C
```

The time constant T1 tells you: after T1 microseconds, the qubit has about a 37% chance of still being in |1⟩. After 5×T1, it's essentially back to ground state with 99%+ probability.

**The experiment:** Build 20 circuits, each of which does:
1. Apply an X gate (flips |0⟩ to |1⟩)
2. Wait for a delay (ranging from 1 µs to 400 µs)
3. Measure

Run each circuit 1024 times. Count how often you see "1". Plot P(1) vs delay. Fit an exponential. The time constant is T1.

The T1 circuits in this project are in `characterization/t1.py`. The key construction is:

```python
qc.x(0)                          # prepare |1⟩
qc.delay(delay_sec, 0, unit="s") # wait
qc.measure(0, 0)                 # measure
```

**Real data from ibm_fez (first run, 3 qubits):**

| Qubit | T1 (µs) |
|-------|---------|
| Q0    | 38.4 ± 1.6 |
| Q1    | 186.5 ± 17.7 |
| Q2    | 60.7 ± 4.9 |

The spread here is remarkable. Qubit 1 lives nearly 5x longer than Qubit 0. They are on the same chip, separated by hundreds of microns, fabricated simultaneously, operated at the same temperature — yet their T1 values differ by almost a factor of 5. This is characteristic of superconducting qubits: local defects in the Josephson junction, trapped charge, two-level systems in the oxide layer, and geometric coupling asymmetries all contribute to this qubit-to-qubit variation. It's one of the central engineering challenges of the field.

To put these numbers in context: a typical two-qubit gate on ibm_fez takes roughly 300–500 ns. With T1 ≈ 38 µs for Q0, you have a budget of about 76–126 gates before energy relaxation becomes the dominant error. For a quantum algorithm requiring thousands of gates, that's a serious bottleneck. Q1 at 186 µs gives you much more runway — around 400+ gates — which is why good qubit characterization informs algorithm scheduling and qubit assignment.

---

### T2: Phase Coherence Time (Hahn Echo)

T1 tells you how long before a qubit loses *energy*. T2 tells you how long before it loses *phase*. These are different things, and the distinction matters.

A superposition state like |+⟩ = (|0⟩ + |1⟩)/√2 is a qubit pointing along the "equator" of the Bloch sphere (if you're familiar with that picture) — it has a definite phase relationship between |0⟩ and |1⟩. Dephasing randomizes this phase without necessarily changing the energy. Imagine two pendulums that start in sync — dephasing is like random fluctuations in the floor that slowly put them out of phase with each other, even if they're still swinging.

The simple dephasing time T2* (T2 star) is measured by a Ramsey experiment. But T2* is corrupted by slow, static noise — inhomogeneities that are constant over a single shot but vary between shots. A more useful quantity is the **Hahn echo** T2, which uses a refocusing pulse to cancel out static noise and isolate the truly incoherent dephasing.

**The Hahn echo sequence:**
1. Apply H (Hadamard gate — creates superposition |+⟩)
2. Wait for half the total delay
3. Apply X (echo refocusing pulse — flips the phase accumulation)
4. Wait for the other half of the delay
5. Apply H again
6. Measure

The X pulse in the middle acts like the "spin echo" in NMR: it inverts the phase accumulation from the first half, so static noise cancels out. What remains is the irreversible dephasing — true T2.

If no decoherence occurred, you'd always measure |0⟩. As decoherence sets in, the probability of measuring |0⟩ decays exponentially with time constant T2.

**Real data from ibm_fez:**

| Qubit | T2 (µs) |
|-------|---------|
| Q0    | 42.8 ± 11.1 |
| Q1    | 257.3 ± 82.0 |
| Q2    | 51.2 ± 1.8 |

A few things to notice. First, Q1 again dramatically outperforms Q0 and Q2 — its T2 of 257 µs suggests remarkably low dephasing noise on that qubit. Second, the large uncertainty on Q1 (±82 µs) is telling: the exponential fit has a lot of variance at the long-delay end of the curve, where the signal is weak. More delay points or more shots would sharpen that estimate. Third, notice that T2 > T1 is physically possible for Hahn echo but the relationship T2 ≤ 2T1 always holds — Q0 at T2=42.8 µs and T1=38.4 µs is close to this limit, suggesting Q0's decoherence is dominated by energy relaxation rather than pure dephasing.

The T2 circuits live in `characterization/t2.py`. The implementation:

```python
qc.h(0)
qc.delay(half_delay_sec, 0, unit="s")
qc.x(0)   # echo pulse
qc.delay(half_delay_sec, 0, unit="s")
qc.h(0)
qc.measure(0, 0)
```

---

### Readout Error: The Confusion Matrix

Even after a quantum computation completes perfectly, you have to *measure* the result. And measurement is its own source of error on superconducting hardware.

When you try to measure a qubit, you're effectively asking: "Is this qubit in |0⟩ or |1⟩?" The measurement works by coupling the qubit to a readout resonator and looking for a transmitted microwave signal at two different frequencies — one if the qubit is in |0⟩, another if it's in |1⟩. But the overlap in those frequency responses, thermal photons in the resonator, and finite measurement time all mean the readout isn't perfect.

We characterize this with a **confusion matrix** (also called an assignment matrix). The experiment is simple:

1. Prepare |0⟩, measure 1024 times. Count how often you accidentally see "1". That's error_0→1 (false positive).
2. Prepare |1⟩, measure 1024 times. Count how often you accidentally see "0". That's error_1→0 (false negative).

**Real data from ibm_fez:**

| Qubit | P(1 \| prep 0) | P(0 \| prep 1) |
|-------|----------------|----------------|
| Q0    | 0.00%          | 3.12%          |
| Q1    | 1.56%          | 1.95%          |
| Q2    | 0.39%          | 3.91%          |

This is fascinating asymmetric noise. Notice that error_0→1 is generally lower than error_1→0. This makes physical sense: |1⟩ is the excited state, so there's a natural tendency for the qubit to decay toward |0⟩ during the measurement window. If the qubit decays to |0⟩ in the middle of being measured, the readout will register "0" even though it started in |1⟩ — that's exactly what error_1→0 is capturing.

Q2's 3.91% error_1→0 is concerning. If your algorithm puts Q2 in |1⟩ at the end, nearly 4% of your measurements will be wrong. For a 1024-shot run, that's ~40 misclassified shots. Mitigation strategies exist (measurement error mitigation, matrix inversion), but the cleaner solution is to work around bad qubits in compilation — which is part of the motivation for Superstaq.

The readout characterization is in `characterization/readout_error.py`. It's the simplest of the three experiments — no delays, no fitting, just state preparation and measurement counting.

---

## The Compilation Problem: Why Qiskit vs Superstaq Is Interesting

Every quantum algorithm you write is expressed in a "logical" language — qubits labeled 0 through N, gates like H, CNOT, Toffoli. But real hardware doesn't speak that language. IBM's ibm_fez only natively supports specific gates: ECR (a two-qubit entangling gate), SX (√X), X, RZ, and Measure. CNOT and Hadamard don't exist in hardware — they have to be *decomposed* into sequences of native gates.

Furthermore, not every qubit is connected to every other qubit. ibm_fez has 156 qubits with a specific connectivity graph — a qubit can only directly interact (via a two-qubit gate) with its physical neighbors. If your algorithm has a CNOT between logical qubits 3 and 7, and those aren't neighbors in hardware, the compiler has to insert SWAP gates to route the computation to adjacent qubits. SWAPs are expensive: each SWAP decomposes into three CNOTs (or ECR gates), tripling the gate count for that operation.

**The compilation problem:** Given a logical circuit, find a physical mapping and routing strategy that minimizes circuit depth and two-qubit gate count on the target hardware. This is an NP-hard optimization problem in general. Compilers use heuristics.

Qiskit's default transpiler is well-engineered and feature-rich. It has four optimization levels (0–3), uses heuristic SWAP routing (SABRE algorithm), and includes a suite of circuit simplification passes. At optimization level 3, it's quite good.

Superstaq, built by [Infleqtion](https://www.infleqtion.com/), takes a different approach. Rather than being a general-purpose compiler, Superstaq is designed as a *hardware-aware compiler optimizer* that targets specific backends — it has deep knowledge of native gate sets, calibration data, and qubit topology. It can apply hardware-specific transformations that Qiskit's generic framework doesn't know about. The claim is: the same logical circuit, compiled through Superstaq, produces shallower circuits with fewer two-qubit gates, which translates directly to lower error rates when run on hardware.

**This project benchmarks that claim.** The benchmark circuits are:

1. **Bell state** — two qubits, one CNOT. The simplest non-trivial entangled circuit.
2. **GHZ-4q** — four-qubit generalization of Bell state, linear CNOT chain.
3. **QFT-4q** — four-qubit Quantum Fourier Transform. Heavy on controlled-phase gates.
4. **QAOA MaxCut-4q** — p=1 Quantum Approximate Optimization Algorithm on a 4-node ring graph. Practically relevant algorithm structure.

For each circuit, we compile with both Qiskit (optimization_level=3) and Superstaq, then measure circuit depth, total gate count, two-qubit gate count, and eventually fidelity on actual hardware.

The benchmark circuit library is in `compilation/benchmark.py`. The comparison logic is straightforward: compile the same logical circuit with both compilers, extract the `CircuitMetrics` dataclass (depth, total gate count, two-qubit gate count), and store the results for both compilers side by side in the database.

---

## Pipeline Architecture

```
quantum_noise_pipeline/
├── characterization/      # T1, T2, readout experiments
│   ├── t1.py
│   ├── t2.py
│   └── readout_error.py
├── compilation/           # Benchmark circuits + compiler wrappers
│   └── benchmark.py
├── database/              # SQLAlchemy ORM + CRUD layer
│   ├── models.py
│   └── store.py
├── utils/                 # IBM Quantum client wrapper
│   └── ibm_client.py
├── scheduler/             # Stateless daily runner
│   └── runner.py
├── dashboard/             # Plotly Dash visualization
│   └── app.py
└── config.py              # Environment-based configuration
```

### `characterization/` — The Physics Layer

This is the heart of the project. Three modules, each following the same pattern:

1. **`build_*_circuits(qubits, params)`** — Constructs the Qiskit `QuantumCircuit` objects for the experiment. Each circuit gets metadata attached (`qc.metadata = {"qubit": q, "delay_us": d}`) so the analysis layer can correctly interpret the results.

2. **`analyze_*_results(counts_list, qubits, params, shots)`** — Takes raw measurement counts (returned by SamplerV2) and extracts the physics. For T1 and T2, this means running `scipy.optimize.curve_fit` on an exponential decay model to extract the time constant and its standard error from the covariance matrix diagonal. For readout, it's pure counting.

All three analyzers return typed dataclasses (`T1ExperimentResult`, `T2ExperimentResult`, `ReadoutErrorExperimentResult`) — no raw dicts floating around.

### `compilation/` — The Compiler Benchmark Layer

`benchmark.py` contains two things: the **benchmark circuit library** (four functions that return `QuantumCircuit` objects) and the **compiler wrappers** (`compile_with_qiskit` and `compile_with_superstaq`).

The Qiskit wrapper calls `qiskit.transpile()` directly. The Superstaq wrapper calls `provider.ibmq_compile()`, which reaches out to Infleqtion's cloud service and returns an optimized circuit. Both wrappers return a `CompilationResult` with a `CircuitMetrics` nested inside — depth, total gate count, and two-qubit gate count specifically.

### `database/` — The Persistence Layer

SQLAlchemy 2.0 with the new `DeclarativeBase` and `Mapped[T]` typed column syntax (no more raw `Column(Float, ...)` calls). Five tables:

- `T1Result` — one row per qubit per measurement run
- `T2Result` — same shape
- `ReadoutErrorResult` — one row per qubit per run, stores both error rates
- `CompilationBenchmark` — one row per (circuit, compiler) pair
- `JobRecord` — tracks submitted IBM Quantum jobs (job_id, status, type, metadata)

The `DatabaseStore` class in `store.py` wraps all CRUD operations. The design keeps SQL out of the higher-level modules — nothing above `database/` imports SQLAlchemy directly.

### `utils/ibm_client.py` — The Hardware Interface

`IBMClient` is a thin, lazy-loading wrapper around `QiskitRuntimeService`. The backend object is fetched on first access and cached. `run_sampler()` instantiates `SamplerV2` in "mode=backend" style (the correct V2 API) and submits a batch of circuits. The method returns a job handle immediately — the actual results are fetched asynchronously by the scheduler.

### `scheduler/runner.py` — The Async Job Manager

Real quantum hardware has queue times. When you submit a batch of 126 circuits to ibm_fez, IBM puts them in a queue. Your job might run in 5 minutes, or it might run in several hours. The scheduler handles this gracefully with a **stateless, two-phase design**:

**Phase 1 — Retrieve:** Check the database for any `JobRecord` with status "SUBMITTED". For each one, query IBM for the job's current status. If "DONE", fetch the result, parse it, and write T1/T2/readout results to their respective tables. If "ERROR" or "CANCELLED", log it and move on.

**Phase 2 — Submit:** If no jobs are pending, build a new characterization batch (T1 + T2 + readout circuits for all configured qubits), transpile it, submit it via `SamplerV2`, and record the job ID in the database.

This design means the runner can be called by a cron job, a GitHub Action, or manually — it will always do the right thing regardless of what state the previous run left things in.

### `dashboard/app.py` — The Visualization Layer

A simple Plotly Dash app that reads from the SQLite database and renders three panels: T1 time series per qubit, T2 time series per qubit, and a grouped bar chart comparing Qiskit vs Superstaq two-qubit gate counts across the four benchmark circuits.

The time series plots are the most interesting feature from a research standpoint. As daily runs accumulate, you'll see whether qubit coherence times drift — they do, on a timescale of days to weeks, due to temperature fluctuations, charge noise, and IBM's own recalibration cycles. The dashboard turns the database into something you can actually see.

Run it with:
```bash
python -m quantum_noise_pipeline.dashboard.app
```

Then open `http://localhost:8050`.

---

## Lessons Learned and Hard-Won Gotchas

This section is where the real engineering knowledge lives. These are the things that aren't in the tutorials and took actual debugging to figure out.

### 1. The `ibm_quantum` → `ibm_quantum_platform` Migration

This one cost several hours. IBM deprecated their original quantum network (ibm_quantum channel) in mid-2024 and migrated everything to IBM Quantum Platform (ibm_quantum_platform channel). The old channel uses `hub/group/project` instance identifiers like `"ibm-q/open/main"`. The new platform uses **CRN (Cloud Resource Name)** identifiers, which look like:

```
crn:v1:bluemix:public:quantum-computing:us-east:a/...
```

If you try to connect with `channel="ibm_quantum"` and a CRN-format instance, you get a cryptic authentication error. If you connect with `channel="ibm_quantum_platform"` and a hub/group/project string, you also get an error. The match has to be exact.

In `config.py`, the channel is hardcoded to `"ibm_quantum_platform"` and the instance is loaded from the `IBM_QUANTUM_INSTANCE` environment variable, which should be your full CRN. This is the correct setup for 2024+ IBM accounts.

```python
channel: str = "ibm_quantum_platform"
instance: str = field(
    default_factory=lambda: os.environ.get("IBM_QUANTUM_INSTANCE", "")
)
```

If you have an older IBM Quantum account and you're seeing `IBMNotAuthorizedError` or `IBMInputValueError`, the first thing to check is whether you're on the old or new platform and whether your instance string matches.

### 2. The `initial_layout` Bug: The Transpiler Doesn't Read Your Metadata

This was subtle and genuinely frustrating. The characterization circuits are built with 1 qubit each (logical qubit 0). The metadata on each circuit says which *physical* qubit it should run on: `qc.metadata = {"qubit": 3}` means this circuit should run on physical qubit 3.

But Qiskit's `transpile()` function does not read `qc.metadata`. It doesn't know which physical qubit you intended. If you call `transpile(circuits, backend=backend)` on a batch of single-qubit circuits, the transpiler will happily map all of them to the same arbitrary physical qubit — whatever looks "best" to it — completely ignoring your intent.

The fix: pass `initial_layout=[qubit]` explicitly to `transpile()`.

```python
def _transpile_qubit(circuits, qubit):
    return list(transpile(circuits, backend=backend,
                          initial_layout=[qubit], optimization_level=1))

for q in QUBITS:
    transpiled += _transpile_qubit(
        [c for c in t1_circuits if c.metadata["qubit"] == q], q
    )
```

By filtering circuits by qubit and transpiling each qubit's circuits separately with the correct `initial_layout`, you guarantee that the T1 experiment for qubit 3 actually runs on physical qubit 3 on the chip — not some random qubit the transpiler chose. Without this, you'd be measuring a different qubit's T1 each run, and your data would be garbage.

### 3. SamplerV2 vs SamplerV1: The API Break

Qiskit 1.0 introduced `SamplerV2` (and `EstimatorV2`) as replacements for the original `Sampler` (now called `SamplerV1`). The APIs are *not* backward compatible. The main differences that matter here:

**V1 API:**
```python
# Old way — instantiate with backend keyword
sampler = Sampler(backend=backend)
job = sampler.run([circuit], shots=1024)
result = job.result()
counts = result.quasi_dists[0]  # Returns quasi-probability dict
```

**V2 API (what this project uses):**
```python
# New way — instantiate with mode=backend
sampler = SamplerV2(mode=backend)
job = sampler.run([circuit], shots=1024)
result = job.result()
# Result is a PrimitiveResult containing PubResult objects
for pub_result in result:
    counts = pub_result.data.c.get_counts()  # Access via classical register name
```

The V2 result structure is completely different. Instead of `quasi_dists`, you get a `PrimitiveResult` that iterates over `PubResult` objects, one per circuit. Each `PubResult` has a `.data` attribute — a `DataBin` — with one attribute per classical register. Since our circuits use `QuantumCircuit(n, n)`, the classical register is named `"c"` by default, so you access it as `pub_result.data.c.get_counts()`.

The extraction logic in `scheduler/runner.py` handles this:

```python
def _extract_counts_from_sampler_result(job_result):
    counts_list = []
    for pub_result in job_result:
        data = pub_result.data
        register = getattr(data, "c", None)
        if register is None:
            register = next(iter(data.__dict__.values()))
        counts_list.append(register.get_counts())
    return counts_list
```

The fallback to `next(iter(data.__dict__.values()))` handles circuits where the classical register might have a different name.

Using `SamplerV1` in 2024+ will throw deprecation warnings and will be removed in future Qiskit versions. V2 is the right API for new code.

### 4. Delay Units: Seconds, Not Microseconds

This is an easy mistake that produces silently wrong results. When you write:

```python
qc.delay(50, 0, unit="us")
```

Qiskit accepts `unit="us"` as microseconds. But internally, Qiskit converts delays to `dt` (device time units) during transpilation, and then to seconds for the hardware. The safe, explicit approach — and the one used throughout this project — is to convert to seconds yourself before construction:

```python
delay_sec = delay_us * 1e-6
qc.delay(delay_sec, 0, unit="s")
```

This makes the unit explicit at the point of construction, avoids any ambiguity in unit handling across Qiskit versions, and ensures the metadata (`delay_us`) stored on the circuit matches what was actually used.

### 5. Job Status Parsing: String vs Enum

IBM's `job.status()` method changed its return type between versions of `qiskit-ibm-runtime`. In some versions it returns a `JobStatus` enum (with a `.name` attribute like `"DONE"`); in others it returns a plain string. The defensive parsing pattern used here:

```python
raw_status = job.status()
status_str = raw_status.name if hasattr(raw_status, "name") else str(raw_status)
if status_str == "DONE":
    ...
```

This handles both cases without depending on the specific runtime version. This kind of defensive coding is important when working with cloud APIs that change faster than your code does.

---

## Testing Without a Quantum Computer

The project has 41 unit tests covering all three characterization analyzers, the database CRUD layer, the compilation benchmark metric extraction, and the scheduler logic. Critically, none of them require IBM Quantum credentials or actual hardware access.

Every test that would normally hit hardware uses `unittest.mock` to substitute fake return values. The IBM client is mocked to return pre-canned count dictionaries. The database uses an in-memory SQLite instance. The curve fitting gets tested with synthetic data that has a known ground-truth T1 or T2.

```bash
pytest tests/ -v
# All 41 tests pass without any API credentials
```

This is non-negotiable for a CI-able project. Hardware queue times can be hours. Tests that depend on hardware can't run in CI. Good mocking also forces you to think clearly about the interface between layers — if a function is hard to mock, that's usually a sign it's doing too much.

---

## The Stack, in Detail

| Component | Version | Why |
|-----------|---------|-----|
| Python | 3.12 | Latest stable, full `match` syntax, improved typing |
| Qiskit | 2.3.1 | Circuit construction and transpilation |
| qiskit-ibm-runtime | 0.46.1 | Cloud access via SamplerV2 |
| qiskit-superstaq | 0.5.63 | Infleqtion's compiler integration |
| SQLAlchemy | 2.0 | ORM with modern `Mapped[T]` syntax |
| Plotly Dash | latest | Interactive browser dashboard |
| scipy | latest | `curve_fit` for exponential decay fitting |
| pytest | latest | Unit testing with mocks |

The project uses `pyproject.toml` for packaging (not legacy `setup.py`). It's installable as a package with `pip install -e ".[dev]"`, which makes imports like `from quantum_noise_pipeline.characterization.t1 import build_t1_circuits` work from anywhere in the project.

---

## What the Real Data Tells Us

Let's take stock of what the first real hardware run on ibm_fez actually showed.

**The qubit lottery.** Qubit 1 is dramatically better than Qubits 0 and 2 on every metric — T1 nearly 5x longer, T2 nearly 6x longer, and symmetric low readout error. This isn't surprising to anyone who's spent time with superconducting hardware: qubit quality varies enormously across a chip, and the best researchers in the field are still working to understand exactly why. If you were running a short algorithm, you'd want to schedule it on Qubit 1.

**Energy relaxation vs dephasing.** For Qubit 0, T2 (42.8 µs) ≈ T1 (38.4 µs). The theoretical maximum for T2 (Hahn echo) is 2×T1. Q0 is close to this limit, which tells us that for Q0, energy relaxation (T1) is the *dominant* decoherence mechanism — pure dephasing is relatively small. Q1, by contrast, has T2 (257 µs) < 2×T1 (373 µs), suggesting there is additional pure dephasing noise on Q1 beyond just energy relaxation.

**Readout errors are asymmetric.** All three qubits show higher 1→0 error than 0→1 error. The physical picture: during measurement, the qubit can decay from |1⟩ to |0⟩ before the measurement discriminator has made its decision. This is T1-during-measurement contamination. A longer T1 doesn't fully solve this because the measurement process itself takes hundreds of nanoseconds.

**Implications for compilation.** These noise characteristics matter directly for how you should compile circuits. A qubit with short T1 should have fewer gates before it's measured. A qubit with high readout error should be given a known final state when possible (if you know the answer should be |0⟩, compile to put the qubit in |0⟩ rather than |1⟩ for measurement, because 0→1 error is lower). Superstaq, with access to backend-specific calibration data, can in principle make these hardware-aware decisions. Qiskit's default transpiler, operating without readout error information, cannot.

---

## Scripts

The `scripts/` directory contains utilities for interacting with hardware:

**`submit_minimal_test.py`** — The primary submission script. Builds T1, T2, and readout circuits for 3 qubits, transpiles with correct `initial_layout`, prompts for confirmation, submits via SamplerV2, and records the job ID in the database. The parameters were tuned after the first run to extend the delay range to 400 µs to properly cover Qubit 1's long coherence times.

**`retrieve_results.py`** — Checks pending jobs and parses completed results into the database.

**`verify_connections.py`** — Sanity check: verifies that IBM credentials are valid and the target backend is accessible.

**`dry_run_hardware.py`** — Runs the full circuit-building pipeline without submitting, printing circuit counts and transpiled circuit statistics. Useful for verifying circuit construction before spending credits.

---

## What's Next

This project is explicitly a learning vehicle and portfolio piece. Here's what the next phases look like:

**Immediate: Complete the compiler benchmark.** The database schema and benchmark circuit library are fully in place. The remaining work is obtaining Superstaq API access, running both compilers over the four benchmark circuits on ibm_fez, and populating the `compilation_benchmarks` table with real data. Then the dashboard's bar chart stops being empty.

**Randomized benchmarking.** T1 and T2 measure individual qubit coherence. For algorithms, what matters more is *gate fidelity*: how accurately does the hardware execute a specific gate? Randomized benchmarking (RB) and interleaved RB are the standard techniques. Adding an RB module would make this characterization pipeline substantially more complete.

**Longitudinal drift analysis.** IBM's qubits drift. T1 can change by 20–30% over a week on the same physical qubit. Running this pipeline on a daily cadence and accumulating data for 4–8 weeks would produce a genuine drift characterization dataset — the kind of data that's valuable for device engineers and useful for calibrating noise models used in classical simulation.

**Measurement error mitigation.** The readout error data collected here can be used to apply probabilistic error mitigation: invert the confusion matrix and apply it to post-process measurement outcomes. This is a classical post-processing step that can substantially improve fidelity estimates.

**More backends.** ibm_fez is a flagship device. It would be interesting to run the same pipeline on ibm_brisbane or ibm_kyoto and compare how noise characteristics vary across devices — not just qubits.

---

## Honest Reflection

This is a student portfolio project, not a published research result. The data is real (those T1 and T2 numbers came from actual circuits running on actual superconducting hardware in a data center in Washington DC), but the sample size is small (one run, three qubits) and the analysis is basic (single exponential fits, no bootstrap uncertainty, no systematic study of fitting robustness).

What this project *does* demonstrate: the ability to work with real quantum hardware APIs at a fairly low level, understand the physics well enough to design meaningful experiments, build a clean software architecture around inherently messy async cloud infrastructure, and think carefully about the interface between quantum algorithms and hardware compilation.

The Superstaq comparison is the most commercially relevant part. Infleqtion's core value proposition is that better compilation leads to better results on real hardware — this pipeline is a direct test of that claim. Whether the results will be dramatic or modest, the methodology for measuring them is sound.

If you're reading this as an Infleqtion engineer evaluating this project: the things I'm most proud of are the `initial_layout` transpilation fix (which required actually understanding why qubit assignment was silently wrong), the SamplerV2 result parsing (which required reading the 2024 Qiskit documentation carefully, not relying on outdated tutorials), and the stateless scheduler design (which required thinking about what happens when the process crashes mid-run). The things I'd improve with more time are the uncertainty quantification on the exponential fits and more delay points for better curve coverage.

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/quantum-noise-pipeline.git
cd quantum-noise-pipeline
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run tests (no credentials needed)
pytest tests/ -v

# Set up credentials
export IBM_QUANTUM_TOKEN="your_ibm_token"
export IBM_QUANTUM_INSTANCE="crn:v1:bluemix:public:..."  # your CRN
export SUPERSTAQ_API_TOKEN="your_superstaq_key"

# Verify connections
python scripts/verify_connections.py

# Dry run (no hardware credits spent)
python scripts/dry_run_hardware.py

# Submit a real characterization run
python scripts/submit_minimal_test.py

# Launch dashboard
python -m quantum_noise_pipeline.dashboard.app
```

---

*Built on ibm_fez (156 qubits, Washington DC). First data collected March 2025. Stack: Python 3.12, Qiskit 2.3.1, qiskit-ibm-runtime 0.46.1, qiskit-superstaq 0.5.63, SQLAlchemy 2.0, Plotly Dash.*
