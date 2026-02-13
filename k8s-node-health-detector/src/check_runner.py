#!/usr/bin/env python3
"""Check Runner — discovers and executes all registered health checks.
Manages check scheduling, timeouts, and result collection.
"""
import importlib
import logging
import time
import threading
from typing import List, Dict, Type

from checks.base import HealthCheck, CheckResult, Severity

logger = logging.getLogger("node-health-detector")


class CheckRunner:
    """Discovers, schedules, and runs health checks."""

    def __init__(self, node_type: str = "gpu", config: dict = None):
        """
        Args:
            node_type: "gpu" or "cpu" — determines which checks to run
            config: Check configuration overrides from YAML
        """
        self.node_type = node_type
        self.config = config or {}
        self.checks: List[HealthCheck] = []
        self.results: Dict[str, CheckResult] = {}
        self._lock = threading.Lock()

    def discover_checks(self):
        """Auto-discover all health checks from the checks package."""
        check_modules = {
            "gpu": [("checks.gpu.dcgm_health", "ALL_CHECKS"),
                    ("checks.gpu.multi_node", "ALL_CHECKS"),
                    ("checks.gpu.day0_provisioning", "ALL_CHECKS"),
                    ("checks.gpu.day1_silent_killers", "ALL_CHECKS")],
            "cpu": [("checks.cpu.cpu_health", "ALL_CHECKS")],
            "memory": [("checks.memory.mem_health", "ALL_CHECKS")],
            "storage": [("checks.storage.disk_health", "ALL_CHECKS")],
            "network": [("checks.network.nic_health", "ALL_CHECKS"),
                        ("checks.network.fabric_health", "ALL_CHECKS")],
            "kubernetes": [("checks.kubernetes.k8s_health", "ALL_CHECKS")],
        }

        for category, modules in check_modules.items():
            for module_path, attr_name in modules:
                try:
                    mod = importlib.import_module(module_path)
                    check_classes: List[Type[HealthCheck]] = getattr(mod, attr_name, [])
                    for cls in check_classes:
                        # Skip checks not applicable to this node type
                        if cls.node_types and self.node_type not in cls.node_types:
                            logger.info(f"Skipping {cls.name} (not for {self.node_type} nodes)")
                            continue
                        # Get check-specific config
                        check_config = self.config.get(cls.name, {})
                        if check_config.get("enabled", True) is False:
                            logger.info(f"Skipping {cls.name} (disabled by config)")
                            continue
                        instance = cls(config=check_config)
                        self.checks.append(instance)
                        logger.info(f"Registered: {cls.name} [{category}] "
                                    f"severity={instance.default_severity.name}")
                except ImportError as e:
                    logger.warning(f"Cannot load {module_path}: {e}")

        logger.info(f"Total checks registered: {len(self.checks)}")

    def run_all(self, node_info: dict) -> List[CheckResult]:
        """Execute all checks and return results."""
        results = []
        for check in self.checks:
            if not check.enabled:
                continue
            try:
                start = time.time()
                result = check.run(node_info)
                result.node = node_info.get("name", "unknown")
                elapsed = time.time() - start
                logger.info(f"  {check.name}: {result.status} "
                            f"({elapsed:.2f}s) — {result.message}")
                results.append(result)
            except Exception as e:
                logger.error(f"  {check.name}: EXCEPTION — {e}")
                results.append(CheckResult(
                    check_name=check.name, status="unknown",
                    severity=check.default_severity,
                    message=f"Check execution failed: {e}",
                    component=check.component, node=node_info.get("name", "")))

        with self._lock:
            self.results = {r.check_name: r for r in results}
        return results

    def get_health_summary(self) -> dict:
        """Get overall node health summary from latest results."""
        with self._lock:
            results = list(self.results.values())

        if not results:
            return {"status": "unknown", "checks_run": 0}

        failed = [r for r in results if r.status == "fail"]
        warned = [r for r in results if r.status == "warn"]
        passed = [r for r in results if r.status == "pass"]

        should_cordon = any(r.should_cordon for r in results)
        worst_severity = min((r.severity for r in results if not r.is_healthy),
                             default=Severity.P3_LOW)

        status = "healthy"
        if failed:
            status = "unhealthy"
        elif warned:
            status = "degraded"

        return {
            "status": status,
            "should_cordon": should_cordon,
            "worst_severity": worst_severity.name,
            "checks_run": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "warned": len(warned),
            "failed_checks": [{"name": r.check_name, "severity": r.severity.name,
                               "message": r.message, "component": r.component}
                              for r in failed],
            "warned_checks": [{"name": r.check_name, "message": r.message,
                               "component": r.component}
                              for r in warned],
        }

    def get_metrics(self) -> List[dict]:
        """Get all results as Prometheus-friendly metrics."""
        with self._lock:
            results = list(self.results.values())
        return [
            {
                "name": r.check_name,
                "status": r.prometheus_status,
                "severity": int(r.severity),
                "component": r.component,
                "node": r.node,
                "message": r.message,
                "should_cordon": 1 if r.should_cordon else 0,
                "details": r.details,
            }
            for r in results
        ]
