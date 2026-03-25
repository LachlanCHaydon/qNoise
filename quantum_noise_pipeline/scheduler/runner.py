"""Automated pipeline runner for scheduled execution.

Designed to be called by a cron job, Claude Cowork, or manually.
Stateless and fault-tolerant: checks for pending jobs, submits
new experiments if idle, and logs all activity.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from quantum_noise_pipeline.config import PipelineConfig, load_config
from quantum_noise_pipeline.database.store import DatabaseStore
from quantum_noise_pipeline.utils.ibm_client import IBMClient

logger = logging.getLogger(__name__)

STATUS_LOG = Path("pipeline_status.log")


def _log_status(message: str) -> None:
    """Append a timestamped status message to the log file."""
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(STATUS_LOG, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    logger.info(message)


def retrieve_pending_jobs(client: IBMClient, db: DatabaseStore) -> int:
    """Check and retrieve results for any pending jobs.

    Args:
        client: IBM Quantum client.
        db: Database store.

    Returns:
        Number of jobs successfully retrieved.
    """
    pending = db.get_pending_jobs()
    if not pending:
        logger.info("No pending jobs to retrieve.")
        return 0

    retrieved = 0
    for record in pending:
        try:
            job = client._service.job(record.job_id)
            status = job.status()

            if status.name == "DONE":
                db.update_job_status(record.job_id, "DONE")
                _log_status(f"Job {record.job_id} completed ({record.job_type})")
                retrieved += 1

            elif status.name in ("ERROR", "CANCELLED"):
                error_msg = getattr(job, "error_message", lambda: "Unknown")()
                db.update_job_status(record.job_id, status.name, error_message=str(error_msg))
                _log_status(f"Job {record.job_id} failed: {status.name}")

            else:
                logger.info("Job %s still %s", record.job_id, status.name)

        except Exception as e:
            logger.error("Error checking job %s: %s", record.job_id, e)
            _log_status(f"Error checking job {record.job_id}: {e}")

    return retrieved


def submit_characterization_batch(
    client: IBMClient,
    db: DatabaseStore,
    config: PipelineConfig,
) -> None:
    """Submit a full characterization batch (T1, T2, readout).

    Args:
        client: IBM Quantum client.
        db: Database store.
        config: Pipeline configuration.
    """
    from qiskit import transpile

    from quantum_noise_pipeline.characterization.t1 import (
        build_t1_circuits,
        generate_delay_values as t1_delays,
    )
    from quantum_noise_pipeline.characterization.t2 import (
        build_t2_circuits,
        generate_delay_values as t2_delays,
    )
    from quantum_noise_pipeline.characterization.readout_error import build_readout_circuits

    params = config.experiments
    qubits = params.qubits

    t1_circuits, _ = build_t1_circuits(
        qubits, t1_delays(params.t1_num_delays, params.t1_max_delay_us)
    )
    t2_circuits, _ = build_t2_circuits(
        qubits, t2_delays(params.t2_num_delays, params.t2_max_delay_us)
    )
    readout_circuits, _ = build_readout_circuits(qubits)

    backend = client.backend
    all_circuits = t1_circuits + t2_circuits + readout_circuits

    logger.info("Transpiling %d circuits for %s...", len(all_circuits), client.backend_name)
    transpiled = transpile(all_circuits, backend=backend, optimization_level=1)

    job = client.run_sampler(transpiled, shots=params.default_shots)

    db.create_job_record(
        job_id=job.job_id(),
        backend_name=client.backend_name,
        job_type="characterization_batch",
        metadata_json={
            "qubits": qubits,
            "num_t1_circuits": len(t1_circuits),
            "num_t2_circuits": len(t2_circuits),
            "num_readout_circuits": len(readout_circuits),
            "shots": params.default_shots,
        },
    )
    _log_status(
        f"Submitted characterization batch: {job.job_id()} "
        f"({len(all_circuits)} circuits on {client.backend_name})"
    )


def has_pending_jobs(db: DatabaseStore) -> bool:
    """Check if there are any jobs still pending."""
    return len(db.get_pending_jobs()) > 0


def main() -> None:
    """Main entry point for the scheduled runner."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        config = load_config()
    except ValueError as e:
        _log_status(f"Configuration error: {e}")
        sys.exit(1)

    db = DatabaseStore(config.database)
    client = IBMClient.from_config(config.ibm)

    if not client.is_operational():
        _log_status(f"Backend {config.ibm.default_backend} is not operational. Exiting.")
        sys.exit(0)

    retrieved = retrieve_pending_jobs(client, db)
    _log_status(f"Retrieved {retrieved} completed jobs.")

    if not has_pending_jobs(db):
        _log_status("No pending jobs. Submitting new characterization batch.")
        submit_characterization_batch(client, db, config)
    else:
        _log_status("Jobs still pending. Skipping new submission.")

    _log_status("Pipeline run complete.")


if __name__ == "__main__":
    main()
