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
from typing import Any

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


def _extract_counts_from_sampler_result(job_result: Any) -> list[dict[str, int]]:
    """Convert SamplerV2 PrimitiveResult into a list of counts dicts.

    SamplerV2 returns one PubResult per circuit. Each PubResult has a
    DataBin with a classical register (named 'c' by default). This
    extracts plain {bitstring: count} dicts in circuit order.

    Args:
        job_result: The result object from job.result().

    Returns:
        List of count dicts, one per circuit, in submission order.
    """
    counts_list: list[dict[str, int]] = []
    for pub_result in job_result:
        data = pub_result.data
        # Classical register is named 'c' for QuantumCircuit(n, n) circuits
        register = getattr(data, "c", None)
        if register is None:
            # Fall back to first available register
            register = next(iter(data.__dict__.values()))
        counts_list.append(register.get_counts())
    return counts_list


def _parse_and_store_job_results(job: Any, record: Any, db: DatabaseStore) -> None:
    """Parse a completed SamplerV2 job and store results in the database.

    Args:
        job: Completed RuntimeJobV2 instance.
        record: The JobRecord from the database.
        db: DatabaseStore for persisting results.
    """
    from quantum_noise_pipeline.characterization.t1 import analyze_t1_results, generate_delay_values as t1_delays
    from quantum_noise_pipeline.characterization.t2 import analyze_t2_results, generate_delay_values as t2_delays
    from quantum_noise_pipeline.characterization.readout_error import analyze_readout_results

    meta = record.metadata_json or {}
    qubits: list[int] = meta.get("qubits", [])
    shots: int = meta.get("shots", 1024)
    n_t1 = meta.get("num_t1_circuits", 0)
    n_t2 = meta.get("num_t2_circuits", 0)
    n_ro = meta.get("num_readout_circuits", 0)

    if not qubits:
        logger.warning("No qubit metadata on job %s, skipping result parse", record.job_id)
        return

    try:
        raw_result = job.result()
        all_counts = _extract_counts_from_sampler_result(raw_result)
    except Exception as e:
        logger.error("Failed to extract counts from job %s: %s", record.job_id, e)
        return

    # Slice counts back into per-experiment groups (same order as submission)
    t1_counts = all_counts[:n_t1]
    t2_counts = all_counts[n_t1:n_t1 + n_t2]
    ro_counts = all_counts[n_t1 + n_t2:n_t1 + n_t2 + n_ro]

    num_t1_delays = n_t1 // len(qubits) if qubits else 0
    num_t2_delays = n_t2 // len(qubits) if qubits else 0

    try:
        t1_results = analyze_t1_results(
            t1_counts, qubits, t1_delays(num_t1_delays, 300.0), shots
        )
        for r in t1_results:
            db.save_t1_result(
                backend_name=record.backend_name,
                qubit=r.qubit,
                t1_us=r.t1_us,
                num_delays=num_t1_delays,
                shots=shots,
                t1_stderr=r.t1_stderr,
                job_id=record.job_id,
                raw_data={"delays_us": r.delays_us, "survival_probs": r.survival_probabilities},
            )
    except Exception as e:
        logger.error("T1 analysis failed for job %s: %s", record.job_id, e)

    try:
        t2_results = analyze_t2_results(
            t2_counts, qubits, t2_delays(num_t2_delays, 200.0), shots
        )
        for r in t2_results:
            db.save_t2_result(
                backend_name=record.backend_name,
                qubit=r.qubit,
                t2_us=r.t2_us,
                num_delays=num_t2_delays,
                shots=shots,
                t2_stderr=r.t2_stderr,
                job_id=record.job_id,
                raw_data={"delays_us": r.delays_us, "survival_probs": r.survival_probabilities},
            )
    except Exception as e:
        logger.error("T2 analysis failed for job %s: %s", record.job_id, e)

    try:
        ro_results = analyze_readout_results(ro_counts, qubits, shots)
        for r in ro_results:
            db.save_readout_error(
                backend_name=record.backend_name,
                qubit=r.qubit,
                error_rate_0to1=r.error_rate_0to1,
                error_rate_1to0=r.error_rate_1to0,
                shots=shots,
                job_id=record.job_id,
            )
    except Exception as e:
        logger.error("Readout analysis failed for job %s: %s", record.job_id, e)

    logger.info("Stored results for job %s", record.job_id)


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
            raw_status = job.status()
            # status() may return a string or an enum with .name
            status_str = raw_status.name if hasattr(raw_status, "name") else str(raw_status)

            if status_str == "DONE":
                db.update_job_status(record.job_id, "DONE")
                _parse_and_store_job_results(job, record, db)
                _log_status(f"Job {record.job_id} completed ({record.job_type})")
                retrieved += 1

            elif status_str in ("ERROR", "CANCELLED"):
                error_msg = getattr(job, "error_message", lambda: "Unknown")()
                db.update_job_status(record.job_id, status_str, error_message=str(error_msg))
                _log_status(f"Job {record.job_id} failed: {status_str}")

            else:
                logger.info("Job %s still %s", record.job_id, status_str)

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

    # Transpile each qubit's circuits separately with the correct physical qubit
    # via initial_layout — without this, the transpiler maps all 1-qubit circuits
    # to the same arbitrary qubit regardless of the metadata "qubit" field.
    def _transpile_qubit(circuits: list, qubit: int) -> list:
        return list(transpile(circuits, backend=backend,
                              initial_layout=[qubit], optimization_level=1))

    transpiled: list = []
    for q in qubits:
        transpiled += _transpile_qubit([c for c in t1_circuits if c.metadata["qubit"] == q], q)
    for q in qubits:
        transpiled += _transpile_qubit([c for c in t2_circuits if c.metadata["qubit"] == q], q)
    for q in qubits:
        transpiled += _transpile_qubit([c for c in readout_circuits if c.metadata["qubit"] == q], q)

    logger.info("Transpiled %d circuits for %s", len(transpiled), client.backend_name)

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
