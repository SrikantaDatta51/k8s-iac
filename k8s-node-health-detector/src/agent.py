#!/usr/bin/env python3
"""Node Health Detector Agent — main entry point.
Runs health checks on a schedule, exposes Prometheus metrics, manages node cordon.
"""
import os
import sys
import time
import json
import signal
import socket
import logging
import yaml

# Ensure the src directory is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_runner import CheckRunner
from prometheus_exporter import PrometheusExporter
from node_controller import NodeController

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("node-health-detector")


class Agent:
    """Main agent loop — runs checks, exports metrics, manages node state."""

    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.node_type = os.environ.get("NODE_TYPE",
                                        self.config.get("node_type", "gpu"))
        self.interval = int(os.environ.get("CHECK_INTERVAL",
                                           self.config.get("interval", 60)))
        self.metrics_port = int(os.environ.get("METRICS_PORT",
                                               self.config.get("metrics_port", 9101)))
        self.node_name = os.environ.get("NODE_NAME", socket.gethostname())

        # Initialize components
        self.runner = CheckRunner(
            node_type=self.node_type,
            config=self.config.get("checks", {}))
        self.exporter = PrometheusExporter(port=self.metrics_port)
        self.controller = NodeController(config={
            "node_name": self.node_name,
            "auto_cordon": self.config.get("auto_cordon", True),
            "auto_uncordon": self.config.get("auto_uncordon", False),
            "dry_run": self.config.get("dry_run", False),
            "cordon_grace_period": self.config.get("cordon_grace_period", 120),
        })

        self._running = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _load_config(self, path: str = None) -> dict:
        """Load config from YAML file or env var."""
        config_file = path or os.environ.get("CONFIG_PATH", "/etc/node-health-detector/config.yaml")
        if os.path.exists(config_file):
            with open(config_file) as f:
                logger.info(f"Loaded config from {config_file}")
                return yaml.safe_load(f) or {}
        logger.info("No config file found, using defaults")
        return {}

    def _handle_signal(self, sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        self._running = False

    def run(self):
        """Main agent loop."""
        logger.info("=" * 60)
        logger.info(f"Node Health Detector Agent starting")
        logger.info(f"  Node:       {self.node_name}")
        logger.info(f"  Type:       {self.node_type}")
        logger.info(f"  Interval:   {self.interval}s")
        logger.info(f"  Metrics:    :{self.metrics_port}/metrics")
        logger.info(f"  Auto-cordon:{self.controller.auto_cordon}")
        logger.info(f"  Dry-run:    {self.controller.dry_run}")
        logger.info("=" * 60)

        # Discover and register checks
        self.runner.discover_checks()

        # Start Prometheus exporter
        self.exporter.start()

        node_info = {"name": self.node_name, "type": self.node_type}
        iteration = 0

        while self._running:
            iteration += 1
            logger.info(f"--- Check cycle {iteration} ---")
            start = time.time()

            try:
                # Run all checks
                self.runner.run_all(node_info)

                # Get summary and metrics
                summary = self.runner.get_health_summary()
                summary["node"] = self.node_name
                metrics = self.runner.get_metrics()

                # Update Prometheus exporter
                self.exporter.update_metrics(metrics, summary)

                # Evaluate cordon/uncordon
                self.controller.evaluate(summary)

                # Log summary
                elapsed = time.time() - start
                logger.info(f"Cycle {iteration} complete in {elapsed:.1f}s — "
                            f"status={summary['status']}, "
                            f"passed={summary['passed']}, "
                            f"warned={summary['warned']}, "
                            f"failed={summary['failed']}")

                if summary["status"] != "healthy":
                    logger.warning(f"Node health: {summary['status'].upper()} — "
                                   f"worst severity: {summary['worst_severity']}")
                    for fc in summary.get("failed_checks", []):
                        logger.warning(f"  FAIL [{fc['severity']}] {fc['name']}: {fc['message']}")

            except Exception as e:
                logger.error(f"Check cycle {iteration} failed: {e}")

            # Wait for next cycle
            remaining = max(0, self.interval - (time.time() - start))
            if self._running and remaining > 0:
                time.sleep(remaining)

        logger.info("Agent shutting down")
        self.exporter.stop()


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    agent = Agent(config_path=config_path)
    agent.run()


if __name__ == "__main__":
    main()
