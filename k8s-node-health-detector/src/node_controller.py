#!/usr/bin/env python3
"""Node Controller — cordon/uncordon node based on health check results.
Only cordons when P0/P1 checks fail with should_cordon=True.
Auto-uncordons when all checks pass (configurable).
"""
import subprocess
import logging
import socket
import time

logger = logging.getLogger("node-health-detector")


class NodeController:
    """Controls node cordon/uncordon based on health check results."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.node_name = self.config.get("node_name", socket.gethostname())
        self.auto_cordon = self.config.get("auto_cordon", True)
        self.auto_uncordon = self.config.get("auto_uncordon", False)  # Conservative default
        self.cordon_grace_period = self.config.get("cordon_grace_period", 120)  # seconds
        self.dry_run = self.config.get("dry_run", False)
        self._cordon_requested_at = None
        self._is_cordoned_by_us = False

    def evaluate(self, summary: dict):
        """Evaluate health summary and take cordon/uncordon action.

        Args:
            summary: Health summary dict from CheckRunner.get_health_summary()
        """
        should_cordon = summary.get("should_cordon", False)

        if should_cordon and self.auto_cordon:
            if self._cordon_requested_at is None:
                self._cordon_requested_at = time.time()
                logger.warning(f"Cordon requested — waiting {self.cordon_grace_period}s grace period. "
                               f"Reason: {self._format_reasons(summary)}")
            elif time.time() - self._cordon_requested_at >= self.cordon_grace_period:
                self._cordon_node(summary)
        elif not should_cordon:
            self._cordon_requested_at = None
            if self._is_cordoned_by_us and self.auto_uncordon:
                self._uncordon_node(summary)

    def _cordon_node(self, summary: dict):
        """Cordon the node."""
        reason = self._format_reasons(summary)
        logger.critical(f"CORDONING node {self.node_name}: {reason}")

        if self.dry_run:
            logger.info("[DRY RUN] Would cordon node")
            self._is_cordoned_by_us = True
            return

        try:
            result = subprocess.run(
                ["kubectl", "cordon", self.node_name,
                 f"--reason=node-health-detector: {reason[:200]}"],
                capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.critical(f"Node {self.node_name} cordoned successfully")
                self._is_cordoned_by_us = True

                # Add annotation
                subprocess.run(
                    ["kubectl", "annotate", "node", self.node_name,
                     f"node-health-detector/cordon-reason={reason[:200]}",
                     f"node-health-detector/cordon-time={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
                     "--overwrite"],
                    capture_output=True, text=True, timeout=15)
            else:
                logger.error(f"Failed to cordon: {result.stderr}")
        except Exception as e:
            logger.error(f"Cordon failed: {e}")

    def _uncordon_node(self, summary: dict):
        """Uncordon the node after all checks pass."""
        logger.info(f"UNCORDONING node {self.node_name} — all checks passing")

        if self.dry_run:
            logger.info("[DRY RUN] Would uncordon node")
            self._is_cordoned_by_us = False
            return

        try:
            result = subprocess.run(
                ["kubectl", "uncordon", self.node_name],
                capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.info(f"Node {self.node_name} uncordoned successfully")
                self._is_cordoned_by_us = False
                subprocess.run(
                    ["kubectl", "annotate", "node", self.node_name,
                     "node-health-detector/cordon-reason-",
                     "node-health-detector/cordon-time-"],
                    capture_output=True, text=True, timeout=15)
        except Exception as e:
            logger.error(f"Uncordon failed: {e}")

    @staticmethod
    def _format_reasons(summary: dict) -> str:
        failed = summary.get("failed_checks", [])
        if not failed:
            return "unknown"
        return "; ".join(f"[{c['severity']}] {c['name']}: {c['message']}"
                         for c in failed[:3])
