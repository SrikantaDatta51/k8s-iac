#!/usr/bin/env python3
"""Storage Health Checks — disk SMART, filesystem pressure, I/O errors."""
import subprocess
import os
from ..base import HealthCheck, Severity


class DiskSMART(HealthCheck):
    name = "disk_smart_health"
    description = "Disk SMART health status (predictive failure detection)"
    component = "storage"
    default_severity = Severity.P1_HIGH

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,TYPE,SIZE"],
                capture_output=True, text=True, timeout=10)
            disks = [l.split()[0] for l in result.stdout.strip().split("\n")
                     if l.split() and l.split()[1] == "disk"]
            failing = []
            for disk in disks:
                try:
                    smart = subprocess.run(
                        ["smartctl", "-H", f"/dev/{disk}"],
                        capture_output=True, text=True, timeout=10)
                    if "FAILED" in smart.stdout.upper():
                        failing.append(disk)
                except FileNotFoundError:
                    return self._skip("smartctl not installed")

            if failing:
                return self._fail(
                    f"SMART failure on disk(s): {', '.join(failing)}",
                    severity=Severity.P1_HIGH, cordon=True,
                    failing_disks=failing)
            return self._pass(f"All {len(disks)} disk(s) pass SMART",
                              disk_count=len(disks))
        except Exception as e:
            return self._unknown(f"Cannot check SMART: {e}")


class FilesystemPressure(HealthCheck):
    name = "filesystem_pressure"
    description = "Filesystem usage on critical mount points (/, /var, kubelet root)"
    component = "storage"
    default_severity = Severity.P1_HIGH

    def run(self, node_info: dict):
        critical_mounts = self.config.get("mounts", ["/", "/var", "/var/lib/kubelet"])
        issues = {}
        crit_pct = float(self.config.get("critical_pct", 90))
        warn_pct = float(self.config.get("warn_pct", 80))
        try:
            for mp in critical_mounts:
                if not os.path.exists(mp):
                    continue
                st = os.statvfs(mp)
                total = st.f_blocks * st.f_frsize
                avail = st.f_bavail * st.f_frsize
                used_pct = (1 - avail / total) * 100 if total > 0 else 0
                if used_pct >= crit_pct:
                    issues[mp] = {"pct": round(used_pct, 1), "level": "critical"}
                elif used_pct >= warn_pct:
                    issues[mp] = {"pct": round(used_pct, 1), "level": "warning"}

            critical = {k: v for k, v in issues.items() if v["level"] == "critical"}
            if critical:
                return self._fail(
                    f"Filesystem critically full: {', '.join(f'{k}={v['pct']}%' for k,v in critical.items())}",
                    severity=Severity.P1_HIGH, cordon=True,
                    filesystem_issues=issues)
            if issues:
                return self._warn(
                    f"Filesystem warning: {', '.join(f'{k}={v['pct']}%' for k,v in issues.items())}",
                    filesystem_issues=issues)
            return self._pass("All critical filesystems within limits")
        except Exception as e:
            return self._unknown(f"Cannot check filesystem: {e}")


class IOErrors(HealthCheck):
    name = "disk_io_errors"
    description = "Disk I/O errors from kernel messages"
    component = "storage"
    default_severity = Severity.P1_HIGH

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["dmesg", "-l", "err,crit"],
                capture_output=True, text=True, timeout=10)
            io_errors = [l for l in result.stdout.split("\n")
                         if any(x in l.lower() for x in
                                ["i/o error", "read error", "write error",
                                 "medium error", "blk_update_request", "buffer i/o"])]
            if len(io_errors) > 10:
                return self._fail(
                    f"{len(io_errors)} disk I/O errors in kernel log",
                    severity=Severity.P1_HIGH, cordon=True,
                    error_count=len(io_errors))
            if io_errors:
                return self._warn(f"{len(io_errors)} disk I/O error(s) detected",
                                  error_count=len(io_errors))
            return self._pass("No disk I/O errors")
        except Exception as e:
            return self._unknown(f"Cannot check I/O errors: {e}")


ALL_CHECKS = [DiskSMART, FilesystemPressure, IOErrors]
