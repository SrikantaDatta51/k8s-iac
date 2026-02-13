#!/usr/bin/env python3
"""Memory Health Checks — ECC errors, DIMM failures, memory pressure."""
import subprocess
import os
from ..base import HealthCheck, Severity


class MemoryECCErrors(HealthCheck):
    name = "memory_ecc_errors"
    description = "System memory ECC errors (correctable and uncorrectable)"
    component = "memory"
    default_severity = Severity.P0_CRITICAL

    def run(self, node_info: dict):
        try:
            ue_count = 0
            ce_count = 0
            edac_base = "/sys/devices/system/edac/mc"
            if os.path.exists(edac_base):
                for mc in os.listdir(edac_base):
                    ue_path = f"{edac_base}/{mc}/ue_count"
                    ce_path = f"{edac_base}/{mc}/ce_count"
                    if os.path.exists(ue_path):
                        with open(ue_path) as f:
                            ue_count += int(f.read().strip())
                    if os.path.exists(ce_path):
                        with open(ce_path) as f:
                            ce_count += int(f.read().strip())

            if ue_count > 0:
                return self._fail(
                    f"Uncorrectable memory errors: {ue_count} — DIMM failure risk",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    ue_count=ue_count, ce_count=ce_count)
            ce_threshold = int(self.config.get("ce_threshold", 1000))
            if ce_count > ce_threshold:
                return self._warn(
                    f"Correctable memory errors: {ce_count} (above {ce_threshold})",
                    ue_count=ue_count, ce_count=ce_count)
            return self._pass(f"Memory ECC: UE={ue_count}, CE={ce_count}",
                              ue_count=ue_count, ce_count=ce_count)
        except Exception as e:
            return self._unknown(f"Cannot check ECC: {e}")


class MemoryPressure(HealthCheck):
    name = "memory_pressure"
    description = "System memory pressure (available memory, OOM risk)"
    component = "memory"
    default_severity = Severity.P1_HIGH

    def run(self, node_info: dict):
        try:
            with open("/proc/meminfo") as f:
                meminfo = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = int(parts[1].strip().split()[0]) * 1024
                        meminfo[key] = val
            total = meminfo.get("MemTotal", 1)
            avail = meminfo.get("MemAvailable", 0)
            pct_used = (1 - avail / total) * 100

            crit = float(self.config.get("critical_pct", 95))
            warn = float(self.config.get("warn_pct", 85))
            if pct_used >= crit:
                return self._fail(
                    f"Memory {pct_used:.1f}% used — OOM risk",
                    severity=Severity.P1_HIGH, cordon=False,
                    pct_used=round(pct_used, 1), avail_gb=round(avail/1073741824, 2))
            if pct_used >= warn:
                return self._warn(
                    f"Memory {pct_used:.1f}% used",
                    pct_used=round(pct_used, 1), avail_gb=round(avail/1073741824, 2))
            return self._pass(
                f"Memory {pct_used:.1f}% used ({avail/1073741824:.1f} GB available)",
                pct_used=round(pct_used, 1), avail_gb=round(avail/1073741824, 2))
        except Exception as e:
            return self._unknown(f"Cannot check memory: {e}")


ALL_CHECKS = [MemoryECCErrors, MemoryPressure]
