"""SQLAlchemy ORM models for the quantum noise pipeline database.

Defines tables for storing characterization results, compilation
benchmarks, and job tracking metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Float, Integer, String, DateTime, JSON, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class T1Result(Base):
    """T1 relaxation time measurement result."""

    __tablename__ = "t1_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backend_name: Mapped[str] = mapped_column(String(100), nullable=False)
    qubit: Mapped[int] = mapped_column(Integer, nullable=False)
    t1_us: Mapped[float] = mapped_column(Float, nullable=False, doc="T1 time in microseconds")
    t1_stderr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_delays: Mapped[int] = mapped_column(Integer, nullable=False)
    shots: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    job_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<T1Result qubit={self.qubit} t1={self.t1_us:.1f}µs "
            f"backend={self.backend_name} @ {self.timestamp}>"
        )


class T2Result(Base):
    """T2 coherence time measurement result (Hahn echo)."""

    __tablename__ = "t2_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backend_name: Mapped[str] = mapped_column(String(100), nullable=False)
    qubit: Mapped[int] = mapped_column(Integer, nullable=False)
    t2_us: Mapped[float] = mapped_column(Float, nullable=False, doc="T2 time in microseconds")
    t2_stderr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_delays: Mapped[int] = mapped_column(Integer, nullable=False)
    shots: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    job_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<T2Result qubit={self.qubit} t2={self.t2_us:.1f}µs "
            f"backend={self.backend_name} @ {self.timestamp}>"
        )


class ReadoutErrorResult(Base):
    """Readout assignment error measurement."""

    __tablename__ = "readout_error_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backend_name: Mapped[str] = mapped_column(String(100), nullable=False)
    qubit: Mapped[int] = mapped_column(Integer, nullable=False)
    error_rate_0to1: Mapped[float] = mapped_column(
        Float, nullable=False, doc="P(measure 1 | prepared 0)"
    )
    error_rate_1to0: Mapped[float] = mapped_column(
        Float, nullable=False, doc="P(measure 0 | prepared 1)"
    )
    shots: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    job_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ReadoutError qubit={self.qubit} "
            f"0→1={self.error_rate_0to1:.4f} 1→0={self.error_rate_1to0:.4f} "
            f"backend={self.backend_name}>"
        )


class CompilationBenchmark(Base):
    """Head-to-head compilation benchmark result."""

    __tablename__ = "compilation_benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backend_name: Mapped[str] = mapped_column(String(100), nullable=False)
    circuit_name: Mapped[str] = mapped_column(String(200), nullable=False)
    compiler: Mapped[str] = mapped_column(
        String(50), nullable=False, doc="'qiskit' or 'superstaq'"
    )
    depth_before: Mapped[int] = mapped_column(Integer, nullable=False)
    depth_after: Mapped[int] = mapped_column(Integer, nullable=False)
    cx_count: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Two-qubit gate count after compilation"
    )
    total_gate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fidelity: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, doc="Output state fidelity vs ideal simulation"
    )
    shots: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    job_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<CompilationBenchmark circuit={self.circuit_name} "
            f"compiler={self.compiler} depth={self.depth_after} "
            f"cx={self.cx_count}>"
        )


class JobRecord(Base):
    """Track submitted IBM Quantum jobs for async retrieval."""

    __tablename__ = "job_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    backend_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_type: Mapped[str] = mapped_column(
        String(50), nullable=False, doc="'t1', 't2', 'readout', 'compilation'"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="SUBMITTED"
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, doc="Experiment metadata (qubits, params, etc.)"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<JobRecord {self.job_id} type={self.job_type} "
            f"status={self.status}>"
        )
