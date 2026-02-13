#!/usr/bin/env python3
"""Base health check class — the plugin interface all checks must implement.

Extension Guide:
    1. Create a new file under src/checks/<category>/
    2. Subclass HealthCheck
    3. Implement run() returning CheckResult
    4. Register in your category's __init__.py
    5. Add check definition in config/checks-gpu.yaml or checks-cpu.yaml
"""
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional
import time


class Severity(IntEnum):
    """Check severity classification.
    Determines cordon/uncordon behavior and alerting priority.
    """
    P0_CRITICAL = 0     # Node must be cordoned IMMEDIATELY (hardware failure, GPU dead)
    P1_HIGH = 1         # Node should be cordoned (degraded hardware, ECC errors)
    P2_MEDIUM = 2       # Warning — investigate (thermal throttle, high error rate)
    P3_LOW = 3          # Informational (minor degradation, approaching threshold)


class CheckStatus:
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNKNOWN = "unknown"
    SKIP = "skip"        # Check was skipped (not applicable to this node)


@dataclass
class CheckResult:
    """Result of a single health check execution."""
    check_name: str
    status: str                          # pass / fail / warn / unknown / skip
    severity: Severity                   # P0-P3
    message: str                         # Human-readable description
    component: str                       # gpu / cpu / memory / storage / network / kubernetes
    details: dict = field(default_factory=dict)   # Arbitrary key-value details
    metric_value: float = 0.0            # Numeric value for Prometheus gauge
    timestamp: float = field(default_factory=time.time)
    node: str = ""
    should_cordon: bool = False          # Whether this result should trigger cordon

    @property
    def is_healthy(self) -> bool:
        return self.status in (CheckStatus.PASS, CheckStatus.SKIP)

    @property
    def prometheus_status(self) -> float:
        """0=pass, 1=warn, 2=fail, 3=unknown."""
        return {"pass": 0, "skip": 0, "warn": 1, "fail": 2, "unknown": 3}.get(self.status, 3)


class HealthCheck:
    """Base class for all health checks. Subclass and implement run()."""

    name: str = "unnamed_check"
    description: str = "No description"
    component: str = "unknown"           # gpu, cpu, memory, storage, network, kubernetes
    default_severity: Severity = Severity.P2_MEDIUM
    interval_seconds: int = 60           # How often to run
    timeout_seconds: int = 30            # Max execution time
    enabled: bool = True
    # Which node types this check applies to
    node_types: list = None              # ["gpu", "cpu"] or None for all

    def __init__(self, config: dict = None):
        """Initialize with optional config override."""
        self.config = config or {}
        if "severity" in self.config:
            self.default_severity = Severity(self.config["severity"])
        if "interval" in self.config:
            self.interval_seconds = self.config["interval"]
        if "enabled" in self.config:
            self.enabled = self.config["enabled"]

    def run(self, node_info: dict) -> CheckResult:
        """Execute the health check. Must be implemented by subclasses.

        Args:
            node_info: Dict with node metadata (name, labels, type, etc.)

        Returns:
            CheckResult with the check outcome
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement run()")

    def _pass(self, message: str, **details) -> CheckResult:
        return CheckResult(
            check_name=self.name, status=CheckStatus.PASS,
            severity=self.default_severity, message=message,
            component=self.component, details=details)

    def _fail(self, message: str, severity: Severity = None, cordon: bool = False, **details) -> CheckResult:
        return CheckResult(
            check_name=self.name, status=CheckStatus.FAIL,
            severity=severity or self.default_severity, message=message,
            component=self.component, details=details, should_cordon=cordon)

    def _warn(self, message: str, **details) -> CheckResult:
        return CheckResult(
            check_name=self.name, status=CheckStatus.WARN,
            severity=self.default_severity, message=message,
            component=self.component, details=details)

    def _skip(self, message: str) -> CheckResult:
        return CheckResult(
            check_name=self.name, status=CheckStatus.SKIP,
            severity=Severity.P3_LOW, message=message,
            component=self.component)

    def _unknown(self, message: str) -> CheckResult:
        return CheckResult(
            check_name=self.name, status=CheckStatus.UNKNOWN,
            severity=self.default_severity, message=message,
            component=self.component)
