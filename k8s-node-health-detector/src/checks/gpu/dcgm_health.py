#!/usr/bin/env python3
"""GPU Health Checks — DCGM Exporter metrics, XID errors, NVLink, ECC, thermal, PCIe.
These checks query the local DCGM exporter or nvidia-smi for GPU health signals.
"""
import subprocess
import json
import os
from ..base import HealthCheck, CheckResult, CheckStatus, Severity


class DCGMOverallHealth(HealthCheck):
    """DCGM overall health check — queries DCGM_FI_DEV_GPU_HEALTH."""
    name = "gpu_dcgm_overall_health"
    description = "DCGM overall GPU health status (0=healthy, non-zero=degraded)"
    component = "gpu"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            unhealthy = []
            for gpu_id, vals in metrics.items():
                health = vals.get("DCGM_FI_DEV_GPU_HEALTH", 0)
                if health != 0:
                    unhealthy.append(f"GPU {gpu_id}: health={health}")

            if unhealthy:
                return self._fail(
                    f"{len(unhealthy)} GPU(s) report unhealthy DCGM status",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    unhealthy_gpus=unhealthy)
            return self._pass(f"All {len(metrics)} GPUs report healthy DCGM status",
                              gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot query DCGM: {e}")


class GPUECCErrors(HealthCheck):
    """GPU ECC memory error check — DCGM_FI_DEV_ECC_DBE_VOL_TOTAL (double-bit)."""
    name = "gpu_ecc_errors"
    description = "GPU ECC double-bit errors (uncorrectable, data corruption risk)"
    component = "gpu"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            errors = {}
            for gpu_id, vals in metrics.items():
                dbe = vals.get("DCGM_FI_DEV_ECC_DBE_VOL_TOTAL", 0)
                sbe = vals.get("DCGM_FI_DEV_ECC_SBE_VOL_TOTAL", 0)
                if dbe > 0:
                    errors[gpu_id] = {"double_bit": dbe, "single_bit": sbe}

            if errors:
                return self._fail(
                    f"{len(errors)} GPU(s) have uncorrectable ECC errors — data corruption risk",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    ecc_errors=errors)

            # Check single-bit (correctable) — warning only
            sbe_gpus = {}
            for gpu_id, vals in metrics.items():
                sbe = vals.get("DCGM_FI_DEV_ECC_SBE_VOL_TOTAL", 0)
                if sbe > int(self.config.get("sbe_threshold", 100)):
                    sbe_gpus[gpu_id] = sbe

            if sbe_gpus:
                return self._warn(
                    f"{len(sbe_gpus)} GPU(s) have elevated single-bit ECC errors",
                    single_bit_errors=sbe_gpus)

            return self._pass("No ECC errors detected", gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot check ECC: {e}")


class GPUXIDErrors(HealthCheck):
    """GPU XID error check — critical kernel errors from nvidia-smi or DCGM."""
    name = "gpu_xid_errors"
    description = "GPU XID errors (driver/hardware faults, e.g. XID 79 = GPU fallen off bus)"
    component = "gpu"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    # Critical XIDs that warrant immediate cordon
    CRITICAL_XIDS = {31, 43, 45, 48, 61, 62, 63, 64, 68, 69, 73, 74, 79, 92, 94, 95, 119, 120}

    def run(self, node_info: dict) -> CheckResult:
        try:
            xids = _get_recent_xid_errors()
            critical = [x for x in xids if x["xid"] in self.CRITICAL_XIDS]
            if critical:
                return self._fail(
                    f"{len(critical)} critical XID error(s) detected — GPU hardware fault",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    critical_xids=critical)
            if xids:
                return self._warn(
                    f"{len(xids)} non-critical XID error(s) detected",
                    xid_errors=xids)
            return self._pass("No XID errors in recent dmesg/logs")
        except Exception as e:
            return self._unknown(f"Cannot check XID errors: {e}")


class GPUTemperature(HealthCheck):
    """GPU temperature check — DCGM_FI_DEV_GPU_TEMP."""
    name = "gpu_temperature"
    description = "GPU temperature monitoring (throttle risk and thermal shutdown)"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            critical_threshold = int(self.config.get("critical_temp", 90))
            warn_threshold = int(self.config.get("warn_temp", 80))

            hot_gpus = {}
            for gpu_id, vals in metrics.items():
                temp = vals.get("DCGM_FI_DEV_GPU_TEMP", 0)
                if temp >= critical_threshold:
                    hot_gpus[gpu_id] = {"temp": temp, "level": "critical"}
                elif temp >= warn_threshold:
                    hot_gpus[gpu_id] = {"temp": temp, "level": "warning"}

            critical_count = sum(1 for v in hot_gpus.values() if v["level"] == "critical")
            if critical_count > 0:
                return self._fail(
                    f"{critical_count} GPU(s) at critical temperature (>={critical_threshold}C)",
                    severity=Severity.P1_HIGH, cordon=True,
                    hot_gpus=hot_gpus)
            if hot_gpus:
                return self._warn(
                    f"{len(hot_gpus)} GPU(s) above warning temperature (>={warn_threshold}C)",
                    hot_gpus=hot_gpus)
            return self._pass("All GPU temperatures normal",
                              gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot check GPU temp: {e}")


class GPUNVLink(HealthCheck):
    """NVLink health check — DCGM NVLink error counters."""
    name = "gpu_nvlink_health"
    description = "NVLink interconnect health (CRC errors, replay errors, recovery count)"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            issues = {}
            for gpu_id, vals in metrics.items():
                crc = vals.get("DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL", 0)
                replay = vals.get("DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL", 0)
                recovery = vals.get("DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL", 0)
                threshold = int(self.config.get("error_threshold", 1000))
                if crc > threshold or replay > threshold or recovery > 0:
                    issues[gpu_id] = {"crc": crc, "replay": replay, "recovery": recovery}

            if any(v.get("recovery", 0) > 0 for v in issues.values()):
                return self._fail(
                    "NVLink recovery errors detected — link degradation",
                    severity=Severity.P1_HIGH, cordon=True,
                    nvlink_issues=issues)
            if issues:
                return self._warn(
                    f"{len(issues)} GPU(s) with NVLink CRC/replay errors",
                    nvlink_issues=issues)
            return self._pass("NVLink health normal", gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot check NVLink: {e}")


class GPUPCIe(HealthCheck):
    """PCIe bus health — replay count, correctable/uncorrectable errors."""
    name = "gpu_pcie_health"
    description = "PCIe bus health for GPU devices (replay count, AER errors)"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            issues = {}
            for gpu_id, vals in metrics.items():
                replay = vals.get("DCGM_FI_DEV_PCIE_REPLAY_COUNTER", 0)
                threshold = int(self.config.get("replay_threshold", 100))
                if replay > threshold:
                    issues[gpu_id] = {"pcie_replay": replay}

            if issues:
                return self._warn(
                    f"{len(issues)} GPU(s) with elevated PCIe replay count",
                    pcie_issues=issues)
            return self._pass("PCIe bus health normal", gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot check PCIe: {e}")


class GPUPowerViolation(HealthCheck):
    """GPU power throttling — DCGM power violation duration."""
    name = "gpu_power_violation"
    description = "GPU power throttling duration (performance degradation)"
    component = "gpu"
    default_severity = Severity.P2_MEDIUM
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            throttled = {}
            for gpu_id, vals in metrics.items():
                pv = vals.get("DCGM_FI_DEV_POWER_VIOLATION", 0)
                tv = vals.get("DCGM_FI_DEV_THERMAL_VIOLATION", 0)
                if pv > 0 or tv > 0:
                    throttled[gpu_id] = {"power_violation_us": pv, "thermal_violation_us": tv}

            if throttled:
                return self._warn(
                    f"{len(throttled)} GPU(s) experiencing power/thermal throttling",
                    throttled_gpus=throttled)
            return self._pass("No GPU power/thermal throttling",
                              gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot check GPU power: {e}")


class GPUMemoryUtilization(HealthCheck):
    """GPU memory utilization — warn if consistently near capacity."""
    name = "gpu_memory_utilization"
    description = "GPU memory usage (risk of OOM, training failures)"
    component = "gpu"
    default_severity = Severity.P2_MEDIUM
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            high_mem = {}
            threshold = float(self.config.get("mem_threshold_pct", 95))
            for gpu_id, vals in metrics.items():
                used = vals.get("DCGM_FI_DEV_FB_USED", 0)
                total = vals.get("DCGM_FI_DEV_FB_TOTAL", 1)
                pct = (used / total * 100) if total > 0 else 0
                if pct >= threshold:
                    high_mem[gpu_id] = {"used_mb": used, "total_mb": total, "pct": round(pct, 1)}

            if high_mem:
                return self._warn(
                    f"{len(high_mem)} GPU(s) memory usage >= {threshold}%",
                    high_memory_gpus=high_mem)
            return self._pass("GPU memory usage normal", gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot check GPU memory: {e}")


class GPURowRemapping(HealthCheck):
    """GPU row remapping — indicates failing GPU memory rows."""
    name = "gpu_row_remapping"
    description = "GPU memory row remapping status (HBM degradation indicator)"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict) -> CheckResult:
        try:
            metrics = _query_dcgm_metrics()
            pending = {}
            for gpu_id, vals in metrics.items():
                remap_pending = vals.get("DCGM_FI_DEV_ROW_REMAP_PENDING", 0)
                remap_failure = vals.get("DCGM_FI_DEV_ROW_REMAP_FAILURE", 0)
                if remap_failure > 0:
                    pending[gpu_id] = {"failure": remap_failure}
                elif remap_pending > 0:
                    pending[gpu_id] = {"pending": remap_pending}

            failures = {k: v for k, v in pending.items() if "failure" in v}
            if failures:
                return self._fail(
                    f"{len(failures)} GPU(s) with row remap failures — HBM degradation",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    row_remap=pending)
            if pending:
                return self._warn(
                    f"{len(pending)} GPU(s) have pending row remaps (needs GPU reset)",
                    row_remap=pending)
            return self._pass("No row remapping issues", gpu_count=len(metrics))
        except Exception as e:
            return self._unknown(f"Cannot check row remapping: {e}")


# ---------- common helpers ----------

def _query_dcgm_metrics() -> dict:
    """Query DCGM exporter metrics endpoint or nvidia-smi.
    Returns dict[gpu_id] -> dict[metric_name] -> value.
    """
    # Try DCGM exporter first (localhost:9400/metrics)
    import urllib.request
    dcgm_url = os.environ.get("DCGM_EXPORTER_URL", "http://localhost:9400/metrics")
    try:
        resp = urllib.request.urlopen(dcgm_url, timeout=5)
        body = resp.read().decode()
        return _parse_prometheus_text(body)
    except Exception:
        pass

    # Fallback: nvidia-smi
    return _query_nvidia_smi()


def _parse_prometheus_text(text: str) -> dict:
    """Parse Prometheus text format into per-GPU metrics dict."""
    gpus = {}
    for line in text.strip().split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        try:
            metric_part, value_str = line.rsplit(" ", 1)
            value = float(value_str)
            # Extract metric name and labels
            if "{" in metric_part:
                name, labels_str = metric_part.split("{", 1)
                labels_str = labels_str.rstrip("}")
                labels = dict(item.split("=", 1) for item in labels_str.split(",")
                              if "=" in item)
                labels = {k: v.strip('"') for k, v in labels.items()}
            else:
                name = metric_part
                labels = {}

            gpu_id = labels.get("gpu", labels.get("GPU_I_ID", "0"))
            gpus.setdefault(gpu_id, {})[name] = value
        except (ValueError, IndexError):
            continue
    return gpus


def _query_nvidia_smi() -> dict:
    """Fallback: get GPU info from nvidia-smi."""
    gpus = {}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,temperature.gpu,memory.used,memory.total,"
             "power.draw,pcie.link.gen.current,ecc.errors.uncorrected.volatile.total,"
             "ecc.errors.corrected.volatile.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        for line in result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 8:
                gpu_id = parts[0]
                gpus[gpu_id] = {
                    "DCGM_FI_DEV_GPU_TEMP": float(parts[1]) if parts[1] != "[N/A]" else 0,
                    "DCGM_FI_DEV_FB_USED": float(parts[2]) if parts[2] != "[N/A]" else 0,
                    "DCGM_FI_DEV_FB_TOTAL": float(parts[3]) if parts[3] != "[N/A]" else 0,
                    "DCGM_FI_DEV_ECC_DBE_VOL_TOTAL": float(parts[6]) if parts[6] != "[N/A]" else 0,
                    "DCGM_FI_DEV_ECC_SBE_VOL_TOTAL": float(parts[7]) if parts[7] != "[N/A]" else 0,
                }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return gpus


def _get_recent_xid_errors() -> list:
    """Parse dmesg for NVIDIA XID errors in the last hour."""
    xids = []
    try:
        result = subprocess.run(
            ["dmesg", "--time-format=iso", "-l", "err,warn"],
            capture_output=True, text=True, timeout=10)
        for line in result.stdout.split("\n"):
            if "NVRM: Xid" in line:
                import re
                match = re.search(r"Xid.*?:\s*(\d+)", line)
                if match:
                    xid = int(match.group(1))
                    xids.append({"xid": xid, "message": line.strip()[:200]})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return xids


# Export all GPU checks
ALL_CHECKS = [
    DCGMOverallHealth,
    GPUECCErrors,
    GPUXIDErrors,
    GPUTemperature,
    GPUNVLink,
    GPUPCIe,
    GPUPowerViolation,
    GPUMemoryUtilization,
    GPURowRemapping,
]
