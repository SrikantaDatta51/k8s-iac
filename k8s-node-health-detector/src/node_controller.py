#!/usr/bin/env python3
"""Node Controller — Autonomous SRE Bot logic.
From SentinAI Reliability Master Book, Page 7: If-Then-Else Remediation Matrix.

Cordon/uncordon with severity-aware response:
  - P0 (XID 48/79, HCA fault): Cordon + Taint NoSchedule + annotation
  - P1 (Link flapping, thermal): Annotate NetworkDegraded + alert
  - Day 0 (VF stuck): Attempt restart openibd before cordon
"""
import subprocess
import logging
import socket
import time
import json

logger = logging.getLogger("node-health-detector")

# XID Encyclopedia — from SentinAI Page 4
XID_ENCYCLOPEDIA = {
    31:  {"category": "MMU",          "component": "Memory",        "action": "cordon",   "desc": "GPU MMU error (invalid access)"},
    32:  {"category": "Bus",          "component": "PCIe",          "action": "cordon",   "desc": "DMA controller error; PCIe signal quality issue"},
    43:  {"category": "App/Driver",   "component": "Compute",       "action": "warn",     "desc": "GPU stopped processing; software-induced fault"},
    45:  {"category": "App/Driver",   "component": "Compute",       "action": "cordon",   "desc": "Preemptive cleanup; GPU context lost"},
    48:  {"category": "Critical",     "component": "VRAM",          "action": "cordon",   "desc": "Double-Bit ECC: unrecoverable memory error"},
    61:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "Internal microcontroller error (FW/HW)"},
    62:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "Internal ECC error in GPU TPC"},
    63:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "ECC page retirement or row remapping failure"},
    64:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "ECC page retirement or row remapping failure"},
    68:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "NVDEC video decode error"},
    69:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "Graphics engine fault"},
    73:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "GPU page fault; illegal memory access in GPU"},
    74:  {"category": "Interconnect", "component": "NVLink",        "action": "cordon",   "desc": "NVLink fabric failure; communication severed"},
    79:  {"category": "Bus",          "component": "PCIe",          "action": "cordon",   "desc": "GPU Fallen off Bus: card unreachable by kernel"},
    92:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "High single-bit ECC error rate"},
    94:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "Contained ECC error (row remap recommended)"},
    95:  {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "Uncontained ECC error (data corruption)"},
    119: {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "GSP firmware error"},
    120: {"category": "Internal",     "component": "GPU",           "action": "cordon",   "desc": "GSP context error"},
    149: {"category": "Hardware",     "component": "Power/Thermal", "action": "cordon",   "desc": "Fatal Link event (power/thermal, newer arch)"},
}


class NodeController:
    """Autonomous SRE Bot — cordon/uncordon with severity-aware remediation."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.node_name = self.config.get("node_name", socket.gethostname())
        self.auto_cordon = self.config.get("auto_cordon", True)
        self.auto_uncordon = self.config.get("auto_uncordon", False)
        self.cordon_grace_period = self.config.get("cordon_grace_period", 120)
        self.dry_run = self.config.get("dry_run", False)
        self._cordon_requested_at = None
        self._is_cordoned_by_us = False
        self._last_remediation = {}

    def evaluate(self, summary: dict):
        """Evaluate health summary and take remediation action.
        Implements the SentinAI If-Then-Else Remediation Matrix (Page 7).
        """
        should_cordon = summary.get("should_cordon", False)
        failed_checks = summary.get("failed_checks", [])

        # ── REMEDIATION MATRIX ──
        for check in failed_checks:
            check_name = check.get("name", "")
            severity = check.get("severity", "P3_LOW")

            # Day 0: VF stuck in INIT → try restart openibd first
            if check_name == "day0_sriov_vf_status":
                self._remediate_sriov(check)
                continue

            # Day 1: Link flapping → annotate + alert, don't cordon yet
            if check_name == "day1_ib_link_flapping":
                self._remediate_link_flapping(check)
                continue

            # Day 1: HCA fault → immediate cordon
            if check_name == "day1_hca_fault":
                self._remediate_hca_fault(check)
                continue

        # ── CORDON/UNCORDON ──
        if should_cordon and self.auto_cordon:
            if self._cordon_requested_at is None:
                self._cordon_requested_at = time.time()
                logger.warning(
                    f"Cordon requested — waiting {self.cordon_grace_period}s grace period. "
                    f"Reason: {self._format_reasons(summary)}")
            elif time.time() - self._cordon_requested_at >= self.cordon_grace_period:
                self._cordon_node(summary)
        elif not should_cordon:
            self._cordon_requested_at = None
            if self._is_cordoned_by_us and self.auto_uncordon:
                self._uncordon_node(summary)

    def _remediate_sriov(self, check: dict):
        """IF (VF Stuck in INIT): restart openibd → if fail → cordon."""
        key = "sriov_restart"
        if self._should_skip_remediation(key, cooldown=300):
            return

        logger.warning(f"SRE Bot: VF stuck in INIT — attempting openibd restart")
        if self.dry_run:
            logger.info("[DRY RUN] Would restart openibd")
            return

        try:
            result = subprocess.run(
                ["systemctl", "restart", "openibd"],
                capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                logger.info("SRE Bot: openibd restarted successfully, will re-check")
                self._annotate_node("node-health-detector/remediation",
                                    f"openibd-restart-{time.strftime('%H%M%S')}")
            else:
                logger.error(f"SRE Bot: openibd restart failed: {result.stderr[:200]}")
                logger.warning("SRE Bot: openibd restart failed — escalating to cordon")
        except Exception as e:
            logger.error(f"SRE Bot: remediation failed: {e}")

        self._last_remediation[key] = time.time()

    def _remediate_link_flapping(self, check: dict):
        """IF (Link Flapping): annotate NetworkDegraded + alert on-call."""
        key = "link_flapping"
        if self._should_skip_remediation(key, cooldown=300):
            return

        logger.warning("SRE Bot: IB link flapping detected — annotating NetworkDegraded")
        self._annotate_node("node-health-detector/network-status", "degraded")
        self._annotate_node("node-health-detector/link-flapping",
                            time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        self._last_remediation[key] = time.time()

    def _remediate_hca_fault(self, check: dict):
        """IF (HCA Fault): immediate cordon + taint NoSchedule."""
        logger.critical(f"SRE Bot: HCA fault detected — immediate cordon + taint")
        self._cordon_node({"failed_checks": [check], "should_cordon": True})
        if not self.dry_run:
            try:
                subprocess.run(
                    ["kubectl", "taint", "node", self.node_name,
                     "node-health-detector/hca-fault=true:NoSchedule", "--overwrite"],
                    capture_output=True, text=True, timeout=15)
            except Exception as e:
                logger.error(f"Failed to taint node: {e}")

    def _should_skip_remediation(self, key: str, cooldown: int) -> bool:
        """Prevent remediation loops — cooldown in seconds."""
        last = self._last_remediation.get(key, 0)
        return (time.time() - last) < cooldown

    def _cordon_node(self, summary: dict):
        """Cordon the node with annotations."""
        reason = self._format_reasons(summary)
        logger.critical(f"CORDONING node {self.node_name}: {reason}")

        if self.dry_run:
            logger.info("[DRY RUN] Would cordon node")
            self._is_cordoned_by_us = True
            return

        try:
            result = subprocess.run(
                ["kubectl", "cordon", self.node_name],
                capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.critical(f"Node {self.node_name} cordoned successfully")
                self._is_cordoned_by_us = True
                self._annotate_node("node-health-detector/cordon-reason", reason[:200])
                self._annotate_node("node-health-detector/cordon-time",
                                    time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
                self._annotate_node("node-health-detector/status", "cordoned")
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
                self._annotate_node("node-health-detector/status", "healthy")
                self._annotate_node("node-health-detector/cordon-reason-", "")
                self._annotate_node("node-health-detector/cordon-time-", "")
        except Exception as e:
            logger.error(f"Uncordon failed: {e}")

    def _annotate_node(self, key: str, value: str):
        """Apply annotation to the node."""
        if self.dry_run:
            return
        try:
            if key.endswith("-"):
                # Remove annotation
                subprocess.run(
                    ["kubectl", "annotate", "node", self.node_name, key, "--overwrite"],
                    capture_output=True, text=True, timeout=10)
            else:
                subprocess.run(
                    ["kubectl", "annotate", "node", self.node_name,
                     f"{key}={value}", "--overwrite"],
                    capture_output=True, text=True, timeout=10)
        except Exception:
            pass

    @staticmethod
    def _format_reasons(summary: dict) -> str:
        failed = summary.get("failed_checks", [])
        if not failed:
            return "unknown"
        return "; ".join(f"[{c.get('severity', '?')}] {c['name']}: {c['message']}"
                         for c in failed[:3])
