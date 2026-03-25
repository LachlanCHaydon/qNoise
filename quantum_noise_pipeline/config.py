"""Centralized configuration for the quantum noise pipeline.

Loads API credentials from environment variables and defines default
experiment parameters. Never commit real tokens — use a .env file or
export them in your shell.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class IBMConfig:
    """IBM Quantum connection settings."""

    api_token: str = field(default_factory=lambda: os.environ.get("IBM_QUANTUM_TOKEN", ""))
    channel: str = "ibm_quantum_platform"
    instance: str = field(
        default_factory=lambda: os.environ.get("IBM_QUANTUM_INSTANCE", "ibm-q/open/main")
    )
    default_backend: str = field(
        default_factory=lambda: os.environ.get("IBM_QUANTUM_BACKEND", "ibm_fez")
    )


@dataclass(frozen=True)
class SuperstaqConfig:
    """Superstaq / Infleqtion connection settings."""

    api_token: str = field(
        default_factory=lambda: os.environ.get("SUPERSTAQ_API_TOKEN", "")
    )


@dataclass(frozen=True)
class ExperimentParams:
    """Default parameters for characterization experiments."""

    # Qubits to characterize (subset of device for speed)
    qubits: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])

    # T1 experiment
    t1_num_delays: int = 20
    t1_max_delay_us: float = 300.0  # microseconds

    # T2 (Hahn echo) experiment
    t2_num_delays: int = 20
    t2_max_delay_us: float = 200.0

    # Readout error
    readout_shots: int = 1024

    # General
    default_shots: int = 1024


@dataclass(frozen=True)
class DatabaseConfig:
    """SQLite database settings."""

    db_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("QNP_DB_PATH", "quantum_noise_pipeline.db")
        )
    )

    @property
    def url(self) -> str:
        """SQLAlchemy connection URL."""
        return f"sqlite:///{self.db_path}"


@dataclass(frozen=True)
class PipelineConfig:
    """Top-level config aggregating all sub-configs."""

    ibm: IBMConfig = field(default_factory=IBMConfig)
    superstaq: SuperstaqConfig = field(default_factory=SuperstaqConfig)
    experiments: ExperimentParams = field(default_factory=ExperimentParams)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


def load_config() -> PipelineConfig:
    """Load pipeline configuration from environment variables.

    Returns:
        Fully populated PipelineConfig instance.

    Raises:
        ValueError: If required credentials are missing.
    """
    config = PipelineConfig()

    missing: list[str] = []
    if not config.ibm.api_token:
        missing.append("IBM_QUANTUM_TOKEN")
    if not config.superstaq.api_token:
        missing.append("SUPERSTAQ_API_TOKEN")

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Set them in your shell or a .env file."
        )

    return config
