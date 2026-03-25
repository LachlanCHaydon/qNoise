"""Database session management and result storage.

Provides a DatabaseStore class wrapping SQLAlchemy session lifecycle
and typed methods for inserting and querying experiment results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence, Type, TypeVar

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from quantum_noise_pipeline.config import DatabaseConfig
from quantum_noise_pipeline.database.models import (
    Base,
    CompilationBenchmark,
    JobRecord,
    ReadoutErrorResult,
    T1Result,
    T2Result,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", T1Result, T2Result, ReadoutErrorResult, CompilationBenchmark)


class DatabaseStore:
    """Manages database connections and provides typed result storage."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = create_engine(config.url, echo=False)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)
        logger.info("Database initialized at %s", config.db_path)

    def _session(self) -> Session:
        """Create a new database session."""
        return self._session_factory()

    # ── Insert operations ──────────────────────────────────────────

    def save_t1_result(
        self,
        backend_name: str,
        qubit: int,
        t1_us: float,
        num_delays: int,
        shots: int,
        t1_stderr: Optional[float] = None,
        job_id: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> T1Result:
        """Store a T1 measurement result.

        Args:
            backend_name: IBM backend that ran the experiment.
            qubit: Physical qubit index.
            t1_us: Fitted T1 time in microseconds.
            num_delays: Number of delay points in the experiment.
            shots: Measurement shots per circuit.
            t1_stderr: Standard error of the T1 fit.
            job_id: IBM job ID for provenance.
            raw_data: Optional raw counts/fit data.

        Returns:
            The persisted T1Result object.
        """
        result = T1Result(
            backend_name=backend_name,
            qubit=qubit,
            t1_us=t1_us,
            t1_stderr=t1_stderr,
            num_delays=num_delays,
            shots=shots,
            job_id=job_id,
            raw_data=raw_data,
        )
        with self._session() as session:
            session.add(result)
            session.commit()
            session.refresh(result)
            logger.info("Saved %s", result)
        return result

    def save_t2_result(
        self,
        backend_name: str,
        qubit: int,
        t2_us: float,
        num_delays: int,
        shots: int,
        t2_stderr: Optional[float] = None,
        job_id: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> T2Result:
        """Store a T2 (Hahn echo) measurement result."""
        result = T2Result(
            backend_name=backend_name,
            qubit=qubit,
            t2_us=t2_us,
            t2_stderr=t2_stderr,
            num_delays=num_delays,
            shots=shots,
            job_id=job_id,
            raw_data=raw_data,
        )
        with self._session() as session:
            session.add(result)
            session.commit()
            session.refresh(result)
            logger.info("Saved %s", result)
        return result

    def save_readout_error(
        self,
        backend_name: str,
        qubit: int,
        error_rate_0to1: float,
        error_rate_1to0: float,
        shots: int,
        job_id: Optional[str] = None,
    ) -> ReadoutErrorResult:
        """Store a readout error measurement."""
        result = ReadoutErrorResult(
            backend_name=backend_name,
            qubit=qubit,
            error_rate_0to1=error_rate_0to1,
            error_rate_1to0=error_rate_1to0,
            shots=shots,
            job_id=job_id,
        )
        with self._session() as session:
            session.add(result)
            session.commit()
            session.refresh(result)
            logger.info("Saved %s", result)
        return result

    def save_compilation_benchmark(
        self,
        backend_name: str,
        circuit_name: str,
        compiler: str,
        depth_before: int,
        depth_after: int,
        cx_count: int,
        total_gate_count: int,
        shots: int,
        fidelity: Optional[float] = None,
        job_id: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> CompilationBenchmark:
        """Store a compilation benchmark result."""
        result = CompilationBenchmark(
            backend_name=backend_name,
            circuit_name=circuit_name,
            compiler=compiler,
            depth_before=depth_before,
            depth_after=depth_after,
            cx_count=cx_count,
            total_gate_count=total_gate_count,
            shots=shots,
            fidelity=fidelity,
            job_id=job_id,
            raw_data=raw_data,
        )
        with self._session() as session:
            session.add(result)
            session.commit()
            session.refresh(result)
            logger.info("Saved %s", result)
        return result

    # ── Job tracking ───────────────────────────────────────────────

    def create_job_record(
        self,
        job_id: str,
        backend_name: str,
        job_type: str,
        metadata_json: Optional[dict] = None,
    ) -> JobRecord:
        """Create a record for a submitted IBM Quantum job."""
        record = JobRecord(
            job_id=job_id,
            backend_name=backend_name,
            job_type=job_type,
            metadata_json=metadata_json,
        )
        with self._session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info("Created job record: %s", record)
        return record

    def update_job_status(
        self,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update a job record's status."""
        with self._session() as session:
            record = session.execute(
                select(JobRecord).where(JobRecord.job_id == job_id)
            ).scalar_one_or_none()
            if record is None:
                logger.warning("Job record not found: %s", job_id)
                return
            record.status = status
            if status in ("DONE", "ERROR", "CANCELLED"):
                record.completed_at = datetime.now(timezone.utc)
            if error_message:
                record.error_message = error_message
            session.commit()
            logger.info("Updated job %s → %s", job_id, status)

    def get_pending_jobs(self) -> Sequence[JobRecord]:
        """Retrieve all jobs with SUBMITTED status."""
        with self._session() as session:
            return list(
                session.execute(
                    select(JobRecord).where(JobRecord.status == "SUBMITTED")
                ).scalars().all()
            )

    # ── Query operations ───────────────────────────────────────────

    def query_results(
        self,
        model: Type[T],
        backend_name: Optional[str] = None,
        qubit: Optional[int] = None,
        limit: int = 100,
    ) -> Sequence[T]:
        """Query results with optional filters.

        Args:
            model: The ORM model class to query.
            backend_name: Filter by backend name.
            qubit: Filter by qubit index (for characterization models).
            limit: Max number of results.

        Returns:
            Sequence of result objects, newest first.
        """
        with self._session() as session:
            stmt = select(model).order_by(model.timestamp.desc()).limit(limit)  # type: ignore[attr-defined]
            if backend_name is not None:
                stmt = stmt.where(model.backend_name == backend_name)  # type: ignore[attr-defined]
            if qubit is not None and hasattr(model, "qubit"):
                stmt = stmt.where(model.qubit == qubit)  # type: ignore[attr-defined]
            return list(session.execute(stmt).scalars().all())
