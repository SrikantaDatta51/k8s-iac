#!/usr/bin/env python3
"""CPU Health Checks — MCE, thermal throttling, load, frequency."""
import subprocess
import os
from ..base import HealthCheck, CheckResult, Severity


class CPUMachineCheckErrors(HealthCheck):
    """Machine Check Exception (MCE) errors — hardware CPU/memory faults."""
    name = "cpu_mce_errors"
    description = "Machine Check Exceptions indicating CPU/memory hardware faults"
    component = "cpu"
    default_severity = Severity.P0_CRITICAL

    def run(self, node_info: dict) -> CheckResult:
        try:
            result = subprocess.run(
                ["dmesg"], capture_output=True, text=True, timeout=10)
            mce_lines = [l for l in result.stdout.split("\n")
                         if "mce:" in l.lower() or "machine check" in l.lower()]
            uncorrectable = [l for l in mce_lines if "uncorrected" in l.lower()]

            if uncorrectable:
                return self._fail(
                    f"{len(uncorrectable)} uncorrectable MCE error(s) — CPU/memory hardware fault",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    mce_count=len(mce_lines), uncorrectable=len(uncorrectable))
            if mce_lines:
                return self._warn(
                    f"{len(mce_lines)} correctable MCE error(s) detected",
                    mce_count=len(mce_lines))
            return self._pass("No MCE errors detected")
        except Exception as e:
            return self._unknown(f"Cannot check MCE: {e}")


class CPUThermalThrottle(HealthCheck):
    """CPU thermal throttling — core_throttle_count from sysfs."""
    name = "cpu_thermal_throttle"
    description = "CPU thermal throttling events indicating cooling issues"
    component = "cpu"
    default_severity = Severity.P2_MEDIUM

    def run(self, node_info: dict) -> CheckResult:
        try:
            total_throttle = 0
            pkg_count = 0
            base = "/sys/devices/system/cpu"
            for f in os.listdir(base):
                if f.startswith("cpu") and f[3:].isdigit():
                    throttle_path = f"{base}/{f}/thermal_throttle/core_throttle_count"
                    if os.path.exists(throttle_path):
                        with open(throttle_path) as fh:
                            count = int(fh.read().strip())
                            total_throttle += count
                            pkg_count += 1

            threshold = int(self.config.get("throttle_threshold", 100))
            if total_throttle > threshold:
                return self._warn(
                    f"CPU thermal throttle count: {total_throttle} across {pkg_count} cores",
                    throttle_count=total_throttle, core_count=pkg_count)
            return self._pass(f"CPU thermal throttle count: {total_throttle}",
                              throttle_count=total_throttle, core_count=pkg_count)
        except Exception as e:
            return self._unknown(f"Cannot check CPU thermal: {e}")


class CPULoadAverage(HealthCheck):
    """CPU load average — system overload detection."""
    name = "cpu_load_average"
    description = "System load average relative to CPU count"
    component = "cpu"
    default_severity = Severity.P2_MEDIUM

    def run(self, node_info: dict) -> CheckResult:
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
            load1, load5, load15 = float(parts[0]), float(parts[1]), float(parts[2])
            cpu_count = os.cpu_count() or 1
            ratio = load5 / cpu_count
            warn_ratio = float(self.config.get("warn_ratio", 2.0))
            crit_ratio = float(self.config.get("critical_ratio", 5.0))

            if ratio >= crit_ratio:
                return self._fail(
                    f"System load extremely high: {load5:.1f} ({ratio:.1f}x CPU count)",
                    severity=Severity.P1_HIGH,
                    load1=load1, load5=load5, load15=load15, cpu_count=cpu_count)
            if ratio >= warn_ratio:
                return self._warn(
                    f"System load elevated: {load5:.1f} ({ratio:.1f}x CPU count)",
                    load1=load1, load5=load5, load15=load15, cpu_count=cpu_count)
            return self._pass(
                f"System load normal: {load5:.1f} ({ratio:.1f}x CPU count)",
                load1=load1, load5=load5, load15=load15, cpu_count=cpu_count)
        except Exception as e:
            return self._unknown(f"Cannot check load: {e}")


class CPUSoftLockup(HealthCheck):
    """CPU soft lockup detection from kernel messages."""
    name = "cpu_soft_lockup"
    description = "CPU soft lockup events (kernel stuck on CPU for extended period)"
    component = "cpu"
    default_severity = Severity.P0_CRITICAL

    def run(self, node_info: dict) -> CheckResult:
        try:
            result = subprocess.run(
                ["dmesg", "-l", "err,crit,alert,emerg"],
                capture_output=True, text=True, timeout=10)
            lockups = [l for l in result.stdout.split("\n")
                       if "soft lockup" in l.lower() or "rcu_sched" in l.lower()
                       or "hung_task" in l.lower()]
            if lockups:
                return self._fail(
                    f"{len(lockups)} CPU soft lockup / hung task event(s) detected",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    lockup_count=len(lockups), sample=lockups[0][:200])
            return self._pass("No CPU soft lockup events")
        except Exception as e:
            return self._unknown(f"Cannot check lockups: {e}")


ALL_CHECKS = [
    CPUMachineCheckErrors,
    CPUThermalThrottle,
    CPULoadAverage,
    CPUSoftLockup,
]
