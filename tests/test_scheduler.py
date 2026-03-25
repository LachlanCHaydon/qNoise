"""Tests for the scheduler/runner module.

IBM Quantum calls are fully mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quantum_noise_pipeline.config import DatabaseConfig
from quantum_noise_pipeline.database.store import DatabaseStore
from quantum_noise_pipeline.scheduler.runner import has_pending_jobs, retrieve_pending_jobs


@pytest.fixture
def db() -> DatabaseStore:
    """In-memory database for scheduler tests."""
    class InMemConfig(DatabaseConfig):
        @property
        def url(self) -> str:
            return "sqlite:///:memory:"

    return DatabaseStore(InMemConfig())


class TestHasPendingJobs:
    def test_no_jobs(self, db: DatabaseStore) -> None:
        assert has_pending_jobs(db) is False

    def test_with_pending_job(self, db: DatabaseStore) -> None:
        db.create_job_record("job1", "ibm_test", "t1")
        assert has_pending_jobs(db) is True

    def test_completed_job_not_pending(self, db: DatabaseStore) -> None:
        db.create_job_record("job1", "ibm_test", "t1")
        db.update_job_status("job1", "DONE")
        assert has_pending_jobs(db) is False


class TestRetrievePendingJobs:
    def test_no_pending(self, db: DatabaseStore) -> None:
        mock_client = MagicMock()
        count = retrieve_pending_jobs(mock_client, db)
        assert count == 0

    def test_retrieves_completed_job(self, db: DatabaseStore) -> None:
        db.create_job_record("job_done", "ibm_test", "t1")

        mock_job = MagicMock()
        mock_job.status.return_value = MagicMock(name="DONE")
        mock_job.status.return_value.name = "DONE"

        mock_client = MagicMock()
        mock_client._service.job.return_value = mock_job

        count = retrieve_pending_jobs(mock_client, db)
        assert count == 1

        # Job should no longer be pending
        assert has_pending_jobs(db) is False

    def test_handles_error_job(self, db: DatabaseStore) -> None:
        db.create_job_record("job_err", "ibm_test", "t2")

        mock_job = MagicMock()
        mock_job.status.return_value = MagicMock(name="ERROR")
        mock_job.status.return_value.name = "ERROR"
        mock_job.error_message.return_value = "Backend crashed"

        mock_client = MagicMock()
        mock_client._service.job.return_value = mock_job

        count = retrieve_pending_jobs(mock_client, db)
        assert count == 0  # Error jobs are not counted as retrieved
        assert has_pending_jobs(db) is False
