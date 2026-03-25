#!/usr/bin/env python3
"""Generate a standalone HTML dashboard from the pipeline database.

Outputs docs/index.html — a single file with interactive Plotly.js charts,
no server required. Designed for GitHub Pages deployment and embedding
in external sites via iframe.

Usage:
    python scripts/generate_dashboard.py

Then enable GitHub Pages (Settings → Pages → Source: /docs) to publish at:
    https://lachlanchaydon.github.io/qNoise/
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine

# ── Config ────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent / "quantum_noise_pipeline.db"
OUT_PATH = Path(__file__).parent.parent / "docs" / "index.html"

# Style matching lachlan.site
COLORS = {
    "bg": "#ffffff",
    "card": "#f8f9fa",
    "text": "#1a1a2e",
    "text_secondary": "#6c757d",
    "grid": "#e8e8e8",
    "border": "#dee2e6",
    "qiskit": "#4a90d9",
    "superstaq": "#e8734a",
    "qubit_0": "#4a90d9",
    "qubit_1": "#2ecc71",
    "qubit_2": "#e8734a",
    "qubit_3": "#9b59b6",
    "qubit_4": "#f39c12",
    "qubit_5": "#1abc9c",
}

PLOTLY_LAYOUT = dict(
    font=dict(family="Inter, -apple-system, Helvetica, Arial, sans-serif", color=COLORS["text"], size=13),
    paper_bgcolor=COLORS["bg"],
    plot_bgcolor=COLORS["bg"],
    margin=dict(l=55, r=25, t=45, b=45),
    xaxis=dict(gridcolor=COLORS["grid"], zeroline=False),
    yaxis=dict(gridcolor=COLORS["grid"], zeroline=False),
)


def style(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


def qubit_color(q: int) -> str:
    return COLORS.get(f"qubit_{q}", "#888888")


# ── Data loading ──────────────────────────────────────────────────

def load_data() -> dict[str, pd.DataFrame]:
    engine = create_engine(f"sqlite:///{DB_PATH}")
    return {
        "t1": pd.read_sql("SELECT * FROM t1_results ORDER BY timestamp", engine),
        "t2": pd.read_sql("SELECT * FROM t2_results ORDER BY timestamp", engine),
        "readout": pd.read_sql("SELECT * FROM readout_error_results ORDER BY timestamp", engine),
        "benchmarks": pd.read_sql("SELECT * FROM compilation_benchmarks ORDER BY timestamp", engine),
        "jobs": pd.read_sql("SELECT * FROM job_records ORDER BY submitted_at", engine),
    }


# ── Chart builders ────────────────────────────────────────────────

def make_coherence_chart(t1_df: pd.DataFrame, t2_df: pd.DataFrame) -> str:
    """T1 and T2 over time — the temporal drift chart."""
    t1_df["timestamp"] = pd.to_datetime(t1_df["timestamp"])
    t2_df["timestamp"] = pd.to_datetime(t2_df["timestamp"])

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=("T1 — Energy Relaxation Time", "T2 — Coherence Time (Hahn Echo)"),
        vertical_spacing=0.14,
    )

    for qubit in sorted(t1_df["qubit"].unique()):
        color = qubit_color(qubit)
        qdata = t1_df[t1_df["qubit"] == qubit]
        fig.add_trace(go.Scatter(
            x=qdata["timestamp"], y=qdata["t1_us"],
            error_y=dict(type="data", array=qdata["t1_stderr"].fillna(0).tolist(), visible=True),
            mode="lines+markers", name=f"Qubit {qubit}",
            marker=dict(size=7, color=color), line=dict(color=color, width=2),
            legendgroup=f"q{qubit}",
        ), row=1, col=1)

    for qubit in sorted(t2_df["qubit"].unique()):
        color = qubit_color(qubit)
        qdata = t2_df[t2_df["qubit"] == qubit]
        fig.add_trace(go.Scatter(
            x=qdata["timestamp"], y=qdata["t2_us"],
            error_y=dict(type="data", array=qdata["t2_stderr"].fillna(0).tolist(), visible=True),
            mode="lines+markers", name=f"Qubit {qubit}",
            marker=dict(size=7, color=color), line=dict(color=color, width=2),
            legendgroup=f"q{qubit}", showlegend=False,
        ), row=2, col=1)

    fig.update_yaxes(title_text="T1 (µs)", row=1, col=1)
    fig.update_yaxes(title_text="T2 (µs)", row=2, col=1)
    style(fig)
    fig.update_layout(height=520)
    return fig.to_html(full_html=False, include_plotlyjs=False)


def make_t1_vs_t2_chart(t1_df: pd.DataFrame, t2_df: pd.DataFrame) -> str:
    """T1 vs T2 scatter with physical bound."""
    t1_df["timestamp"] = pd.to_datetime(t1_df["timestamp"])
    t2_df["timestamp"] = pd.to_datetime(t2_df["timestamp"])

    t1_m = t1_df[["qubit", "timestamp", "t1_us", "t1_stderr"]].copy()
    t2_m = t2_df[["qubit", "timestamp", "t2_us", "t2_stderr"]].copy()
    t1_m["ts_round"] = t1_m["timestamp"].dt.round("1min")
    t2_m["ts_round"] = t2_m["timestamp"].dt.round("1min")
    merged = pd.merge(t1_m, t2_m, on=["qubit", "ts_round"], suffixes=("_t1", "_t2"))

    fig = go.Figure()
    max_t1 = merged["t1_us"].max() * 1.2 if len(merged) > 0 else 300
    fig.add_trace(go.Scatter(
        x=[0, max_t1], y=[0, 2 * max_t1],
        mode="lines", name="T2 = 2×T1 limit",
        line=dict(color=COLORS["grid"], dash="dash", width=2),
    ))

    for qubit in sorted(merged["qubit"].unique()):
        color = qubit_color(qubit)
        qdata = merged[merged["qubit"] == qubit]
        fig.add_trace(go.Scatter(
            x=qdata["t1_us"], y=qdata["t2_us"],
            error_x=dict(type="data", array=qdata["t1_stderr"].fillna(0).tolist(), visible=True),
            error_y=dict(type="data", array=qdata["t2_stderr"].fillna(0).tolist(), visible=True),
            mode="markers", name=f"Qubit {qubit}",
            marker=dict(size=11, color=color, line=dict(width=1, color=COLORS["text"])),
        ))

    style(fig)
    fig.update_layout(
        xaxis_title="T1 (µs)", yaxis_title="T2 (µs)", height=420, width=520,
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def make_readout_chart(readout_df: pd.DataFrame) -> str:
    """Readout error grouped bar chart."""
    readout_df["timestamp"] = pd.to_datetime(readout_df["timestamp"])
    latest = readout_df.sort_values("timestamp").groupby("qubit").last().reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[f"Qubit {q}" for q in latest["qubit"]],
        y=latest["error_rate_0to1"] * 100,
        name="P(1|prep 0)", marker_color=COLORS["qiskit"],
    ))
    fig.add_trace(go.Bar(
        x=[f"Qubit {q}" for q in latest["qubit"]],
        y=latest["error_rate_1to0"] * 100,
        name="P(0|prep 1)", marker_color=COLORS["superstaq"],
    ))

    style(fig)
    fig.update_layout(
        yaxis_title="Error Rate (%)", barmode="group", height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def make_benchmark_chart(bm_df: pd.DataFrame) -> str:
    """Compilation depth and 2Q gate comparison."""
    circuits_order = ["bell_state", "ghz_4q", "qft_4q", "qaoa_maxcut_4q"]
    bm = bm_df[bm_df["circuit_name"].isin(circuits_order)].copy()

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=("Circuit Depth", "Two-Qubit Gates"))

    for compiler, color in [("qiskit", COLORS["qiskit"]), ("superstaq", COLORS["superstaq"])]:
        cdata = bm[bm["compiler"] == compiler].copy()
        cdata["circuit_name"] = pd.Categorical(cdata["circuit_name"], categories=circuits_order, ordered=True)
        cdata = cdata.sort_values("circuit_name").groupby("circuit_name").last().reset_index()
        labels = [c.replace("_", " ").title() for c in cdata["circuit_name"]]

        fig.add_trace(go.Bar(
            x=labels, y=cdata["depth_after"], name=compiler.capitalize(),
            marker_color=color, legendgroup=compiler,
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            x=labels, y=cdata["cx_count"], name=compiler.capitalize(),
            marker_color=color, legendgroup=compiler, showlegend=False,
        ), row=1, col=2)

    style(fig)
    fig.update_layout(
        barmode="group", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def make_fidelity_chart(bm_df: pd.DataFrame) -> str:
    """Hardware fidelity comparison — the money chart."""
    circuits_order = ["bell_state", "ghz_4q", "qft_4q", "qaoa_maxcut_4q"]
    bm = bm_df[(bm_df["circuit_name"].isin(circuits_order)) & (bm_df["fidelity"].notna())].copy()

    if len(bm) == 0:
        return "<p>No fidelity data yet.</p>"

    fig = go.Figure()
    for compiler, color in [("qiskit", COLORS["qiskit"]), ("superstaq", COLORS["superstaq"])]:
        cdata = bm[bm["compiler"] == compiler].copy()
        cdata["circuit_name"] = pd.Categorical(cdata["circuit_name"], categories=circuits_order, ordered=True)
        cdata = cdata.sort_values("circuit_name").groupby("circuit_name").last().reset_index()
        labels = [c.replace("_", " ").title() for c in cdata["circuit_name"]]

        fig.add_trace(go.Bar(
            x=labels, y=cdata["fidelity"], name=compiler.capitalize(),
            marker_color=color,
            text=[f"{f:.4f}" for f in cdata["fidelity"]],
            textposition="outside", textfont=dict(size=11),
        ))

    style(fig)
    fig.update_layout(
        yaxis_title="Hellinger Fidelity", yaxis_range=[0.9, 1.005],
        barmode="group", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


# ── Stats generation ──────────────────────────────────────────────

def make_stats_html(data: dict[str, pd.DataFrame]) -> str:
    t1, t2, ro, bm, jobs = data["t1"], data["t2"], data["readout"], data["benchmarks"], data["jobs"]

    total_runs = len(jobs)
    qubits = sorted(t1["qubit"].unique().tolist()) if len(t1) > 0 else []

    date_min = jobs["submitted_at"].min()[:10] if len(jobs) > 0 else "—"
    date_max = jobs["submitted_at"].max()[:10] if len(jobs) > 0 else "—"

    cards = []
    cards.append(f'<div class="stat-card"><div class="stat-number">{total_runs}</div><div class="stat-label">Hardware Runs</div></div>')
    cards.append(f'<div class="stat-card"><div class="stat-number">{len(t1)}</div><div class="stat-label">T1 Measurements</div></div>')
    cards.append(f'<div class="stat-card"><div class="stat-number">{len(t2)}</div><div class="stat-label">T2 Measurements</div></div>')
    cards.append(f'<div class="stat-card"><div class="stat-number">{len(qubits)}</div><div class="stat-label">Qubits Tracked</div></div>')
    cards.append(f'<div class="stat-card"><div class="stat-number">{len(bm)}</div><div class="stat-label">Benchmark Results</div></div>')

    # Date range + last updated as a centered subtitle below the grid
    date_line = f'<div class="date-range">{date_min} &mdash; {date_max} &nbsp;&bull;&nbsp; Last updated: {{generated_at}}</div>'

    return "\n".join(cards) + "\n" + date_line


# ── HTML template ─────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>qNoise — Quantum Hardware Noise Characterization</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}

  body {{
    font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: {bg};
    color: {text};
    margin: 0;
    padding: 0;
    line-height: 1.6;
  }}

  .container {{
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
  }}

  header {{
    text-align: center;
    padding: 2.5rem 0 1rem;
    border-bottom: 1px solid {border};
    margin-bottom: 2rem;
  }}

  header h1 {{
    font-size: 1.75rem;
    font-weight: 600;
    margin: 0 0 0.5rem;
    letter-spacing: -0.02em;
  }}

  header p {{
    color: {text_secondary};
    font-size: 0.95rem;
    margin: 0;
  }}

  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 1rem;
    margin-bottom: 0.75rem;
  }}

  .stat-card {{
    background: {card};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 1.2rem 1rem;
    text-align: center;
  }}

  .stat-number {{
    font-size: 1.5rem;
    font-weight: 700;
    color: {text};
    line-height: 1.2;
  }}

  .stat-label {{
    font-size: 0.8rem;
    color: {text_secondary};
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 0.3rem;
  }}

  section {{
    margin-bottom: 3rem;
  }}

  section h2 {{
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0 0 0.4rem;
    letter-spacing: -0.01em;
  }}

  section .description {{
    color: {text_secondary};
    font-size: 0.9rem;
    margin: 0 0 1rem;
  }}

  .chart-container {{
    border: 1px solid {border};
    border-radius: 8px;
    padding: 0.5rem;
    background: {bg};
  }}

  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
  }}

  @media (max-width: 700px) {{
    .two-col {{ grid-template-columns: 1fr; }}
  }}

  .insight {{
    background: {card};
    border-left: 3px solid {superstaq};
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.2rem;
    margin: 1.5rem 0;
    font-size: 0.92rem;
  }}

  .insight strong {{ color: {text}; }}

  footer {{
    text-align: center;
    padding: 2rem 0;
    border-top: 1px solid {border};
    color: {text_secondary};
    font-size: 0.85rem;
  }}

  footer a {{ color: {qiskit}; text-decoration: none; }}
  footer a:hover {{ text-decoration: underline; }}

  .date-range {{
    text-align: center;
    color: {text_secondary};
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 0.25rem 0 1.5rem;
    padding: 0;
    white-space: nowrap;
  }}

  .purpose {{
    max-width: 720px;
    margin: 0 auto 1rem;
    text-align: left;
    color: {text};
    font-size: 1.02rem;
    line-height: 1.75;
    font-family: Georgia, 'Times New Roman', serif;
    padding: 0;
    opacity: 0.85;
  }}

  .purpose + .purpose {{
    margin-top: 0;
  }}

  .purpose:last-of-type {{
    margin-bottom: 2.5rem;
  }}

  .purpose strong {{
    color: {text};
    opacity: 1;
  }}

  .purpose code {{
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    font-size: 0.88em;
    background: {card};
    padding: 0.1em 0.35em;
    border-radius: 3px;
    border: 1px solid {border};
  }}

  .purpose em {{
    font-style: italic;
  }}

  details.code-details {{
    margin-top: 0.75rem;
    border: 1px solid {border};
    border-radius: 6px;
    overflow: hidden;
  }}

  details.code-details summary {{
    padding: 0.6rem 1rem;
    font-size: 0.82rem;
    color: {text_secondary};
    cursor: pointer;
    background: {card};
    user-select: none;
  }}

  details.code-details summary:hover {{
    color: {text};
  }}

  details.code-details .code-body {{
    padding: 1rem;
    font-size: 0.82rem;
    line-height: 1.6;
    color: {text};
    border-top: 1px solid {border};
  }}

  details.code-details .code-body code {{
    background: {card};
    padding: 0.15em 0.4em;
    border-radius: 3px;
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    font-size: 0.9em;
  }}

  details.code-details .code-body pre {{
    background: {card};
    padding: 0.8rem 1rem;
    border-radius: 6px;
    overflow-x: auto;
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    font-size: 0.85em;
    line-height: 1.5;
    margin: 0.5rem 0;
  }}
</style>
</head>
<body>
<div class="container">

<header>
  <h1>qNoise</h1>
  <p>Quantum hardware noise characterization &amp; compiler benchmarking</p>
  <p style="margin-top: 0.3rem;">ibm_fez (156-qubit Heron processor) &bull; Qiskit vs Superstaq</p>
</header>

<div class="stats-grid">
{stats_html}
</div>

<div class="purpose">
  Every data point on this page was measured on IBM's 156-qubit Heron processor in Washington DC. The project measures three fundamental noise properties of individual qubits: <strong>T1</strong> (how long a qubit holds its excited state before decaying), <strong>T2</strong> (how long a superposition survives after cancelling noise) and <strong>readout assignment error</strong> (how often the measurement electronics misidentify the qubit's state). T1 and T2 values are extracted by fitting exponential decay curves to probabilities across  delay times using scipy's <code>curve_fit</code>.
</div>
<div class="purpose">
  Quantum circuits written in terms of gates (H, CNOT, RZ) that must be compiled down to a gate set (CZ, SX, RZ on ibm_fez) native to the processor and routed across the chip's qubit connectivity graph. This project creates identical circuits through Qiskit's transpiler (optimization level 3) and Infleqtion's Superstaq compiler, then runs both versions on the same hardware in the same job to compare fidelity.
</div>
<div class="purpose">
  Built in Python with Qiskit 2.3 for circuit construction and transpilation, qiskit-ibm-runtime (SamplerV2 primitives) for hardware access, qiskit-superstaq for Infleqtion's compiler, SQLAlchemy 2.0 for structured data storage, scipy for curve fitting, and Plotly for visualization. All hardware calls are managed through a  job scheduler that submits circuits, tracks jobs , and displays results when they're done. 
</div>

<section>
  <h2>Qubit Coherence Over Time</h2>
  <p class="description">T1 (energy relaxation) and T2 (dephasing) measured across multiple runs. Each point is one hardware measurement. Drift between runs reveals noise instability.</p>
  <div class="chart-container">{coherence_chart}</div>
  <details class="code-details">
    <summary>How this is measured</summary>
    <div class="code-body">
      <p><strong>T1 experiment:</strong> Prepare the qubit in |1&rang; with an X gate, wait a variable delay, then measure. The probability of remaining in |1&rang; decays exponentially: P(1) = A&middot;exp(-t/T1) + C.  The curve is fit with <code>scipy.optimize.curve_fit</code> across 10&ndash;20 delay values.</p>
      <pre>qc = QuantumCircuit(1, 1)
qc.x(0)                        # prepare |1&rang;
qc.delay(delay_sec, 0, unit="s")  # wait
qc.measure(0, 0)               # check if it decayed</pre>
      <p><strong>T2 experiment (Hahn echo):</strong> Create a superposition with H, wait half the delay, apply an X refocusing pulse to cancel static noise, wait the other half, then H and measure. The echo isolates true T2 from T2* (which includes inhomogeneous broadening).</p>
      <pre>qc.h(0)                         # superposition
qc.delay(half_delay, 0, unit="s")
qc.x(0)                         # refocusing pulse
qc.delay(half_delay, 0, unit="s")
qc.h(0)                         # interfere
qc.measure(0, 0)</pre>
      <p>Each qubit's circuits are transpiled with <code>initial_layout=[qubit]</code> to make sure the correct quibit is read, not whatever the transpiler picks.</p>
    </div>
  </details>
</section>

<section>
<div class="two-col">
  <div>
    <h2>T1 vs T2 Relationship</h2>
    <p class="description">Physics constrains T2 &le; 2&times;T1. Points near the dashed line indicate energy relaxation dominates.</p>
    <div class="chart-container">{t1_vs_t2_chart}</div>
    <details class="code-details">
      <summary>Why T2 &le; 2&times;T1</summary>
      <div class="code-body">
        <p>Decoherence has two components: <strong>energy relaxation</strong> (T1 &mdash; the qubit loses energy to its environment) and <strong>pure dephasing</strong> (T&phi; &mdash; the phase relationship randomizes without energy exchange). The total coherence time satisfies:</p>
        <pre>1/T2 = 1/(2*T1) + 1/T_phi</pre>
        <p>Since T&phi; &ge; 0, T2 can never exceed 2&times;T1. When T2 &approx; 2&times;T1, pure dephasing is negligible and energy relaxation is the dominant noise channel. When T2 &Lt; 2&times;T1, the qubit suffers additional phase noise (e.g., flux fluctuations, TLS coupling).</p>
      </div>
    </details>
  </div>
  <div>
    <h2>Readout Error</h2>
    <p class="description">Assignment error per qubit. False negatives (1&rarr;0) dominate due to T1 decay during measurement.</p>
    <div class="chart-container">{readout_chart}</div>
    <details class="code-details">
      <summary>How readout error is measured</summary>
      <div class="code-body">
        <p>For each qubit, two circuits are run:</p>
        <pre># Prepare |0&rang; and measure
qc0 = QuantumCircuit(1, 1)
qc0.measure(0, 0)

# Prepare |1&rang; and measure
qc1 = QuantumCircuit(1, 1)
qc1.x(0)
qc1.measure(0, 0)</pre>
        <p><strong>P(1|prep 0)</strong> = fraction of |0&rang; preparations that are misread as |1&rang;. This is typically very low.</p>
        <p><strong>P(0|prep 1)</strong> = fraction of |1&rang; preparations that are misread as |0&rang;. This is higher because the qubit can undergo T1 decay <em>during</em> the measurement process itself, falling from |1&rang; to |0&rang; before the readout completes.</p>
      </div>
    </details>
  </div>
</div>
</section>

<section>
  <h2>Compilation Benchmark — Qiskit vs Superstaq</h2>
  <p class="description">Identical circuits compiled through two optimizers, then executed on the same hardware.</p>
  <div class="chart-container">{benchmark_chart}</div>
  <details class="code-details">
    <summary>How the benchmark works</summary>
    <div class="code-body">
      <p>Four benchmark circuits (Bell state, GHZ-4q, QFT-4q, QAOA MaxCut-4q) are compiled through two paths:</p>
      <p><strong>Qiskit path:</strong> <code>transpile(circuit, backend=ibm_fez, optimization_level=3)</code> &mdash; Qiskit's most aggressive optimization. Decomposes to the native gate set (CZ, SX, RZ), optimizes single-qubit chains, and routes qubits across the hardware topology.</p>
      <p><strong>Superstaq path:</strong> <code>provider.ibmq_compile(circuit, target="ibmq_fez_qpu")</code> &mdash; Infleqtion's cloud compiler. Uses proprietary optimizations including hardware-aware noise models and custom decomposition strategies.</p>
      <p>Both compiled circuits are then submitted to ibm_fez in the same job, ensuring identical hardware conditions for a fair comparison.</p>
    </div>
  </details>
</section>

<section>
  <h2>Hardware Fidelity — The Real Test</h2>
  <p class="description">Hellinger fidelity between measured output and ideal (noiseless) distribution. Higher is better.</p>
  <div class="chart-container">{fidelity_chart}</div>
  <details class="code-details">
    <summary>How fidelity is calculated</summary>
    <div class="code-body">
      <p>I use <strong>Hellinger fidelity</strong> to compare the measured output distribution against the ideal (noiseless) distribution:</p>
      <pre>F_H = (sum_x  sqrt(p_measured(x) * p_ideal(x)))^2</pre>
      <p>F_H = 1.0 means perfect agreement with the ideal circuit. For the Bell state, the ideal distribution is 50% |00&rang; + 50% |11&rang;. For GHZ-4q, it's 50% |0000&rang; + 50% |1111&rang;. For QFT on |0000&rang;, the ideal output is a uniform distribution over all 16 bitstrings.</p>
      <p>This metric captures <em>all</em> noise sources simultaneously &mdash; gate errors, decoherence during the circuit, readout errors, and crosstalk. It's the most honest measure of real-world compiler performance.</p>
    </div>
  </details>
  <div class="insight">
    <strong>Early signal:</strong> So far, Superstaq has won 2 of 3 fidelity comparisons, specifically on QFT-4q, where it achieved fidelity (0.9970 vs 0.9914) even though it produced a deeper circuit. This dataset is too small to make any conclusions, but the early data suggests that optimizing for 2Q gate count might matter more than minimizing depth on noisy hardware. I'm going to be running this a few more times over the next few days to see if this pattern changes. Please check back soon! :) 
  </div>
</section>

<footer>
  Built by <a href="https://lachlan.site">Lachlan Haydon</a> &bull;
  <a href="https://github.com/LachlanCHaydon/qNoise">Source on GitHub</a>
</footer>

</div>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    print("Loading data from database...")
    data = load_data()

    for name, df in data.items():
        print(f"  {name}: {len(df)} rows")

    print("Generating charts...")
    coherence = make_coherence_chart(data["t1"], data["t2"])
    t1_vs_t2 = make_t1_vs_t2_chart(data["t1"], data["t2"])
    readout = make_readout_chart(data["readout"])
    benchmark = make_benchmark_chart(data["benchmarks"]) if len(data["benchmarks"]) > 0 else "<p>No benchmark data yet.</p>"
    fidelity = make_fidelity_chart(data["benchmarks"]) if len(data["benchmarks"]) > 0 else "<p>No fidelity data yet.</p>"
    stats = make_stats_html(data)

    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")
    # Resolve {generated_at} inside the stats HTML before inserting into template
    stats = stats.replace("{generated_at}", generated_at)

    html = HTML_TEMPLATE.format(
        coherence_chart=coherence,
        t1_vs_t2_chart=t1_vs_t2,
        readout_chart=readout,
        benchmark_chart=benchmark,
        fidelity_chart=fidelity,
        stats_html=stats,
        **COLORS,
    )

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(html)
    print(f"\nDashboard written to: {OUT_PATH}")
    print(f"Open in browser:      file://{OUT_PATH.resolve()}")
    print(f"\nTo publish: enable GitHub Pages (Settings → Pages → Source: /docs)")


if __name__ == "__main__":
    main()
