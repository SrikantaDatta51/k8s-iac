#!/usr/bin/env python3
"""Day 1 Silent Killers — performance degradation checks that don't crash jobs
but degrade them by 30-90%. These are the "Orange X" markers from SentinAI.

From SentinAI Reliability Master Book, Page 3: Day 1 - The Runtime & Reliability Path.
"""
import subprocess
import os
import re
from ..base import HealthCheck, Severity


class PCIeTrainingCheck(HealthCheck):
    """PCIe link width and generation validation.
    A card meant for Gen5 x16 training at Gen4 or x8 width is a silent killer.
    30-50% bandwidth loss, NCCL degrades, no crash.
    """
    name = "day1_pcie_training"
    description = "PCIe gen/width validation: Gen5 x16 expected, Gen4/x8 = 30-50% bandwidth loss"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            expected_gen = int(self.config.get("expected_pcie_gen", 5))
            expected_width = int(self.config.get("expected_pcie_width", 16))

            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=pcie.link.gen.current,pcie.link.width.current",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                return self._unknown(f"nvidia-smi PCIe query failed: {result.stderr[:200]}")

            degraded = []
            for i, line in enumerate(result.stdout.strip().split("\n")):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    try:
                        gen = int(parts[0])
                        width = int(parts[1])
                        if gen < expected_gen or width < expected_width:
                            degraded.append({
                                "gpu": i, "gen": gen, "width": width,
                                "expected_gen": expected_gen, "expected_width": expected_width
                            })
                    except ValueError:
                        pass

            if degraded:
                return self._fail(
                    f"{len(degraded)} GPU(s) PCIe training degraded "
                    f"(expected Gen{expected_gen} x{expected_width})",
                    severity=Severity.P1_HIGH,
                    degraded_gpus=degraded)

            return self._pass(
                f"All GPUs at PCIe Gen{expected_gen} x{expected_width}",
                gpu_count=len(result.stdout.strip().split("\n")))
        except Exception as e:
            return self._unknown(f"Cannot check PCIe: {e}")


class GPUClockThrottleCheck(HealthCheck):
    """GPU clock speed vs max clocks — >10% delta = thermal/power throttling.
    Silent killer: 30-90% performance loss, job doesn't crash.
    SentinAI NPD check_gpu_clocks.sh equivalent.
    """
    name = "day1_gpu_clock_throttle"
    description = "GPU SM clock vs max: >10% delta = throttling (30-90% perf loss)"
    component = "gpu"
    default_severity = Severity.P2_MEDIUM
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=clocks.current.sm,clocks.max.sm,"
                 "clocks.current.memory,clocks.max.memory",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                return self._unknown(f"nvidia-smi clock query failed")

            throttle_pct = float(self.config.get("throttle_threshold_pct", 10))
            throttled = []

            for i, line in enumerate(result.stdout.strip().split("\n")):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    try:
                        sm_cur = float(parts[0])
                        sm_max = float(parts[1])
                        mem_cur = float(parts[2])
                        mem_max = float(parts[3])

                        sm_delta = ((sm_max - sm_cur) / sm_max * 100) if sm_max > 0 else 0
                        mem_delta = ((mem_max - mem_cur) / mem_max * 100) if mem_max > 0 else 0

                        if sm_delta > throttle_pct or mem_delta > throttle_pct:
                            throttled.append({
                                "gpu": i,
                                "sm_current_mhz": sm_cur, "sm_max_mhz": sm_max,
                                "sm_delta_pct": round(sm_delta, 1),
                                "mem_current_mhz": mem_cur, "mem_max_mhz": mem_max,
                                "mem_delta_pct": round(mem_delta, 1)
                            })
                    except ValueError:
                        pass

            if throttled:
                return self._warn(
                    f"{len(throttled)} GPU(s) clock throttled >{throttle_pct}% below max",
                    throttled_gpus=throttled)

            return self._pass("All GPU clocks within normal range")
        except Exception as e:
            return self._unknown(f"Cannot check GPU clocks: {e}")


class IBLinkFlappingCheck(HealthCheck):
    """InfiniBand link flapping detection — links toggling cause NCCL re-transmissions.
    Silent killer: NCCL timeout risk, 50%+ perf degradation.
    """
    name = "day1_ib_link_flapping"
    description = "InfiniBand link flapping (toggling up/down causes NCCL re-transmissions)"
    component = "network"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            # Check dmesg for mlx5_core link state changes
            result = subprocess.run(
                ["dmesg"], capture_output=True, text=True, timeout=10)

            link_events = []
            for line in result.stdout.split("\n"):
                if "mlx5_core" in line and ("Link down" in line or "Link up" in line):
                    link_events.append(line.strip()[:200])

            # Count link state transitions
            down_count = sum(1 for e in link_events if "Link down" in e)
            up_count = sum(1 for e in link_events if "Link up" in e)
            flap_threshold = int(self.config.get("flap_threshold", 3))

            if down_count >= flap_threshold:
                return self._fail(
                    f"IB link flapping detected: {down_count} link-down events "
                    f"(threshold: {flap_threshold})",
                    severity=Severity.P1_HIGH,
                    link_down_count=down_count, link_up_count=up_count,
                    recent_events=link_events[-5:])

            if down_count > 0:
                return self._warn(
                    f"IB link events: {down_count} down, {up_count} up",
                    link_down_count=down_count, link_up_count=up_count)

            return self._pass("No IB link flapping detected")
        except Exception as e:
            return self._unknown(f"Cannot check IB flapping: {e}")


class HCAFaultCheck(HealthCheck):
    """ConnectX-7 HCA hardware faults — card panic detection.
    Hard failure: RDMA traffic blackholed.
    """
    name = "day1_hca_fault"
    description = "ConnectX-7 HCA hardware fault detection (panic, FW assert, internal error)"
    component = "network"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["dmesg", "-l", "err,crit,alert,emerg"],
                capture_output=True, text=True, timeout=10)

            hca_errors = []
            for line in result.stdout.split("\n"):
                if any(x in line for x in [
                    "mlx5_core.*internal error",
                    "mlx5_core.*assert",
                    "mlx5_core.*panic",
                    "mlx5_core.*health compromised",
                    "mlx5_core.*cmd timeout",
                ]):
                    hca_errors.append(line.strip()[:200])

            if hca_errors:
                return self._fail(
                    f"HCA fault detected: {len(hca_errors)} error(s)",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    hca_errors=hca_errors[:5])

            return self._pass("No HCA faults detected")
        except Exception as e:
            return self._unknown(f"Cannot check HCA: {e}")


class FabricSubnetManagerCheck(HealthCheck):
    """Subnet Manager convergence — SM must be active for IB routing.
    Fabric partitioning: SM fails to converge, blackholes all RDMA traffic.
    """
    name = "day1_subnet_manager"
    description = "IB Subnet Manager convergence (SM down = fabric partition, all RDMA blackholed)"
    component = "network"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            # Check sminfo for SM status
            result = subprocess.run(
                ["sminfo"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                # sminfo not available, try ibstat
                result = subprocess.run(
                    ["ibstat"], capture_output=True, text=True, timeout=10)
                if "Active" in result.stdout:
                    return self._pass("IB ports active (sminfo not available)")
                return self._unknown("Cannot determine SM status")

            if "MASTER" not in result.stdout.upper() and "STANDBY" not in result.stdout.upper():
                return self._fail(
                    "No Subnet Manager found in MASTER or STANDBY state",
                    severity=Severity.P0_CRITICAL,
                    sm_output=result.stdout[:200])

            return self._pass("Subnet Manager reachable")
        except Exception as e:
            return self._unknown(f"Cannot check SM: {e}")


ALL_CHECKS = [
    PCIeTrainingCheck,
    GPUClockThrottleCheck,
    IBLinkFlappingCheck,
    HCAFaultCheck,
    FabricSubnetManagerCheck,
]
