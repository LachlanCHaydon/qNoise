"""Tests for database storage layer.

Uses an in-memory SQLite database — no files written to disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantum_noise_pipeline.config import DatabaseConfig
from quantum_noise_pipeline.database.models import (
    CompilationBenchmark,
    JobRecord,
    T1Result,
    T2Result,
)
from quantum_noise_pipeline.database.store import DatabaseStore


@pytest.fixture
def db() -> DatabaseStore:
    """Create a fresh in-memory database for each test."""
    config = DatabaseConfig(db_path=Path(":memory:"))
    # Override URL for in-memory
    class InMemConfig(DatabaseConfig):
        @property
        def url(self) -> str:
            return "sqlite:///:memory:"

    return DatabaseStore(InMemConfig())


class TestT1Storage:
    def test_save_and_query(self, db: DatabaseStore) -> None:
        result = db.save_t1_result(
            backend_name="ibm_test",
            qubit=0,
            t1_us=105.3,
            num_delays=20,
            shots=1024,
            t1_stderr=2.1,
            job_id="job_abc123",
        )
        assert result.id is not None
        assert result.t1_us == pytest.approx(105.3)

        queried = db.query_results(T1Result, backend_name="ibm_test")
        assert len(queried) == 1
        assert queried[0].qubit == 0

    def test_query_by_qubit(self, db: DatabaseStore) -> None:
        db.save_t1_result("ibm_test", qubit=0, t1_us=100.0, num_delays=10, shots=512)
        db.save_t1_result("ibm_test", qubit=1, t1_us=120.0, num_delays=10, shots=512)
        db.save_t1_result("ibm_test", qubit=0, t1_us=98.0, num_delays=10, shots=512)

        q0_results = db.query_results(T1Result, qubit=0)
        assert len(q0_results) == 2
        for r in q0_results:
            assert r.qubit == 0


class TestT2Storage:
    def test_save_and_query(self, db: DatabaseStore) -> None:
        result = db.save_t2_result(
            backend_name="ibm_test",
            qubit=2,
            t2_us=55.7,
            num_delays=15,
            shots=2048,
        )
        assert result.id is not None

        queried = db.query_results(T2Result)
        assert len(queried) == 1
        assert queried[0].t2_us == pytest.approx(55.7)


class TestReadoutErrorStorage:
    def test_save(self, db: DatabaseStore) -> None:
        result = db.save_readout_error(
            backend_name="ibm_test",
            qubit=3,
            error_rate_0to1=0.012,
            error_rate_1to0=0.025,
            shots=4096,
        )
        assert result.id is not None
        assert result.error_rate_0to1 == pytest.approx(0.012)


class TestCompilationBenchmarkStorage:
    def test_save(self, db: DatabaseStore) -> None:
        result = db.save_compilation_benchmark(
            backend_name="ibm_test",
            circuit_name="bell_state",
            compiler="qiskit",
            depth_before=3,
            depth_after=8,
            cx_count=1,
            total_gate_count=5,
            shots=1024,
            fidelity=0.97,
        )
        assert result.id is not None

        queried = db.query_results(CompilationBenchmark)
        assert len(queried) == 1
        assert queried[0].compiler == "qiskit"


class TestJobTracking:
    def test_create_and_update(self, db: DatabaseStore) -> None:
        db.create_job_record(
            job_id="test_job_001",
            backend_name="ibm_test",
            job_type="t1",
        )
        pending = db.get_pending_jobs()
        assert len(pending) == 1
        assert pending[0].status == "SUBMITTED"

        db.update_job_status("test_job_001", "DONE")
        pending_after = db.get_pending_jobs()
        assert len(pending_after) == 0

    def test_update_nonexistent_job(self, db: DatabaseStore) -> None:
        # Should not raise, just log a warning
        db.update_job_status("nonexistent_id", "DONE")

    def test_error_status_with_message(self, db: DatabaseStore) -> None:
        db.create_job_record("err_job", "ibm_test", "t2")
        db.update_job_status("err_job", "ERROR", error_message="Backend timeout")

        pending = db.get_pending_jobs()
        assert len(pending) == 0
