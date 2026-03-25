#!/usr/bin/env python3
"""Entry point for daily automated pipeline execution.

Usage:
    python scripts/run_daily.py

This script is designed to be run by Claude Cowork or a cron job.
It delegates to the scheduler module's main() function.
"""

from quantum_noise_pipeline.scheduler.runner import main

if __name__ == "__main__":
    main()
