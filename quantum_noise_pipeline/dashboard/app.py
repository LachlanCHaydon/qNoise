"""Interactive results dashboard.

Run with: python -m quantum_noise_pipeline.dashboard.app

Displays T1/T2 time series, readout error heatmaps, and
compilation benchmark comparisons from the SQLite database.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html

from quantum_noise_pipeline.config import DatabaseConfig
from quantum_noise_pipeline.database.models import (
    CompilationBenchmark,
    T1Result,
    T2Result,
)
from quantum_noise_pipeline.database.store import DatabaseStore

logger = logging.getLogger(__name__)


def create_app(db: DatabaseStore | None = None) -> Dash:
    """Create and configure the Dash application.

    Args:
        db: Optional DatabaseStore. If None, connects using default config.

    Returns:
        Configured Dash app instance.
    """
    if db is None:
        db = DatabaseStore(DatabaseConfig())

    app = Dash(__name__, title="Quantum Noise Pipeline")

    app.layout = html.Div(
        [
            html.H1("Quantum Noise Characterization Dashboard"),
            html.Hr(),
            html.H2("T1 Relaxation Time"),
            dcc.Graph(id="t1-timeseries", figure=_build_t1_plot(db)),
            html.H2("T2 Coherence Time"),
            dcc.Graph(id="t2-timeseries", figure=_build_t2_plot(db)),
            html.H2("Compilation Benchmarks"),
            dcc.Graph(id="compilation-comparison", figure=_build_compilation_plot(db)),
            html.Hr(),
            html.P("Data updates automatically from daily pipeline runs."),
        ],
        style={"maxWidth": "1200px", "margin": "0 auto", "padding": "20px"},
    )

    return app


def _build_t1_plot(db: DatabaseStore) -> go.Figure:
    """Build T1 time series plot from database."""
    results = db.query_results(T1Result, limit=500)
    if not results:
        return _empty_figure("No T1 data yet. Run the pipeline to collect data.")

    df = pd.DataFrame(
        [
            {
                "timestamp": r.timestamp,
                "qubit": f"Q{r.qubit}",
                "T1 (µs)": r.t1_us,
            }
            for r in results
        ]
    )
    fig = px.scatter(
        df,
        x="timestamp",
        y="T1 (µs)",
        color="qubit",
        title="T1 Relaxation Time Over Time",
    )
    fig.update_layout(xaxis_title="Date", yaxis_title="T1 (µs)")
    return fig


def _build_t2_plot(db: DatabaseStore) -> go.Figure:
    """Build T2 time series plot from database."""
    results = db.query_results(T2Result, limit=500)
    if not results:
        return _empty_figure("No T2 data yet. Run the pipeline to collect data.")

    df = pd.DataFrame(
        [
            {
                "timestamp": r.timestamp,
                "qubit": f"Q{r.qubit}",
                "T2 (µs)": r.t2_us,
            }
            for r in results
        ]
    )
    fig = px.scatter(
        df,
        x="timestamp",
        y="T2 (µs)",
        color="qubit",
        title="T2 Coherence Time Over Time",
    )
    fig.update_layout(xaxis_title="Date", yaxis_title="T2 (µs)")
    return fig


def _build_compilation_plot(db: DatabaseStore) -> go.Figure:
    """Build compilation comparison bar chart."""
    results = db.query_results(CompilationBenchmark, limit=200)
    if not results:
        return _empty_figure("No compilation data yet.")

    df = pd.DataFrame(
        [
            {
                "circuit": r.circuit_name,
                "compiler": r.compiler,
                "depth": r.depth_after,
                "2Q gates": r.cx_count,
            }
            for r in results
        ]
    )
    fig = px.bar(
        df,
        x="circuit",
        y="2Q gates",
        color="compiler",
        barmode="group",
        title="Two-Qubit Gate Count: Qiskit vs Superstaq",
    )
    return fig


def _empty_figure(message: str) -> go.Figure:
    """Create a placeholder figure with a message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=16, color="gray"),
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def main() -> None:
    """Run the dashboard server."""
    app = create_app()
    print("Starting dashboard at http://localhost:8050")
    app.run(debug=True, port=8050)


if __name__ == "__main__":
    main()
