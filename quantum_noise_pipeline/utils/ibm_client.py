"""IBM Quantum connection wrapper.

Provides a thin abstraction over QiskitRuntimeService for connection
management, backend selection, and job submission/retrieval.
"""

from __future__ import annotations

import logging
from typing import Any

from qiskit.circuit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

from quantum_noise_pipeline.config import IBMConfig

logger = logging.getLogger(__name__)


class IBMClient:
    """Manages connection to IBM Quantum Platform."""

    def __init__(self, service: QiskitRuntimeService, backend_name: str) -> None:
        self._service = service
        self._backend_name = backend_name
        self._backend: Any | None = None

    @classmethod
    def from_config(cls, config: IBMConfig) -> "IBMClient":
        """Create client from IBMConfig.

        Args:
            config: IBM connection configuration.

        Returns:
            Initialized IBMClient.
        """
        logger.info("Connecting to IBM Quantum (channel=%s)...", config.channel)
        service = QiskitRuntimeService(
            channel=config.channel,
            token=config.api_token,
            instance=config.instance or None,
        )
        return cls(service=service, backend_name=config.default_backend)

    @property
    def backend(self) -> Any:
        """Lazily fetch and cache the backend object."""
        if self._backend is None:
            logger.info("Fetching backend: %s", self._backend_name)
            self._backend = self._service.backend(self._backend_name)
        return self._backend

    @property
    def backend_name(self) -> str:
        """Name of the target backend."""
        return self._backend_name

    def run_sampler(
        self,
        circuits: list[QuantumCircuit],
        shots: int = 1024,
    ) -> Any:
        """Submit circuits via SamplerV2 primitive.

        Args:
            circuits: Circuits to execute.
            shots: Number of measurement shots per circuit.

        Returns:
            RuntimeJobV2 handle.
        """
        sampler = Sampler(mode=self.backend)
        job = sampler.run(circuits, shots=shots)
        logger.info("Submitted sampler job: %s", job.job_id())
        return job

    def get_backend_properties(self) -> dict[str, Any]:
        """Retrieve current backend calibration properties.

        Returns:
            Dictionary with qubit count, basis gates, and target info.
        """
        backend = self.backend
        target = backend.target
        return {
            "name": backend.name,
            "num_qubits": target.num_qubits,
            "basis_gates": list(target.operation_names),
            "dt": getattr(backend, "dt", None),
        }

    def is_operational(self) -> bool:
        """Check if the backend is currently operational.

        Returns:
            True if the backend is accepting jobs.
        """
        try:
            status = self.backend.status()
            return status.operational
        except Exception:
            logger.warning("Could not fetch backend status", exc_info=True)
            return False
