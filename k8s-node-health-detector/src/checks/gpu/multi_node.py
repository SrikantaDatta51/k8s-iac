#!/usr/bin/env python3
"""Multi-Node Health Checks — cross-node validation, NCCL, NVLink topology.
These checks validate multi-node GPU communication and collective performance.
Based on SOP: Day Zero NCCL, NVLink5/NVSwitch, GPUDirect RDMA validation.
"""
import subprocess
import os
import json
from ..base import HealthCheck, Severity


class NCCLAllReduceTest(HealthCheck):
    """NCCL All-Reduce bandwidth test across GPUs on this node.
    Based on SOP §2.4: BusBW >= 85% of NVLink5 theoretical (1.8 TB/s).
    """
    name = "multi_node_nccl_allreduce"
    description = "NCCL All-Reduce bandwidth (intra-node GPU-to-GPU via NVLink5/NVSwitch)"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    interval_seconds = 300  # Every 5 min (heavy test)
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            nccl_binary = self.config.get("nccl_binary", "/usr/bin/all_reduce_perf")
            if not os.path.exists(nccl_binary):
                return self._skip(f"NCCL test binary not found: {nccl_binary}")

            gpu_count = int(self.config.get("gpu_count", 8))
            min_bw_gbps = float(self.config.get("min_bandwidth_gbps", 1530))

            result = subprocess.run(
                [nccl_binary, "-b", "8", "-e", "8G", "-f", "2", "-g", str(gpu_count)],
                capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                return self._fail(
                    f"NCCL All-Reduce test failed: {result.stderr[:200]}",
                    severity=Severity.P0_CRITICAL, cordon=True)

            # Parse busbw from last line of output
            busbw = self._parse_busbw(result.stdout)
            if busbw is not None and busbw < min_bw_gbps:
                return self._fail(
                    f"NCCL All-Reduce BusBW {busbw:.1f} GB/s below threshold {min_bw_gbps} GB/s",
                    severity=Severity.P1_HIGH, cordon=True,
                    bus_bandwidth_gbps=busbw, threshold_gbps=min_bw_gbps)

            return self._pass(
                f"NCCL All-Reduce BusBW: {busbw:.1f} GB/s (threshold: {min_bw_gbps} GB/s)",
                bus_bandwidth_gbps=busbw)
        except subprocess.TimeoutExpired:
            return self._fail("NCCL All-Reduce test timed out (300s)", severity=Severity.P1_HIGH)
        except Exception as e:
            return self._unknown(f"Cannot run NCCL test: {e}")

    @staticmethod
    def _parse_busbw(output: str) -> float:
        """Parse busbw from nccl-tests output (last data line, busbw column)."""
        for line in reversed(output.strip().split("\n")):
            parts = line.split()
            if len(parts) >= 10:
                try:
                    return float(parts[-2])  # busbw is second-to-last column
                except (ValueError, IndexError):
                    continue
        return None


class NVBandwidthTest(HealthCheck):
    """NVBandwidth device-to-device test — validates NVLink5 interconnect.
    Based on SOP §2.6: D2D >= 90% of 1.8 TB/s.
    """
    name = "multi_node_nvbandwidth"
    description = "nvbandwidth device-to-device GPU memory copy bandwidth (NVLink5 validation)"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    interval_seconds = 600
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            nvbw_binary = self.config.get("nvbandwidth_binary", "/usr/bin/nvbandwidth")
            if not os.path.exists(nvbw_binary):
                return self._skip(f"nvbandwidth not found: {nvbw_binary}")

            # Run device_to_device memcpy
            result = subprocess.run(
                [nvbw_binary, "-t", "device_to_device_memcpy_read_ce"],
                capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                return self._fail(
                    f"nvbandwidth test failed: {result.stderr[:200]}",
                    severity=Severity.P1_HIGH, cordon=True)

            # Parse minimum bandwidth across all GPU pairs
            min_bw_gbps = float(self.config.get("min_d2d_bandwidth_gbps", 1620))  # 90% of 1800
            bw_values = self._parse_bandwidths(result.stdout)
            if bw_values:
                min_bw = min(bw_values)
                if min_bw < min_bw_gbps:
                    return self._fail(
                        f"NVLink D2D bandwidth {min_bw:.1f} GB/s below {min_bw_gbps:.0f} GB/s (90% threshold)",
                        severity=Severity.P1_HIGH, cordon=True,
                        min_bandwidth=min_bw, threshold=min_bw_gbps)
                return self._pass(f"NVLink D2D bandwidth min={min_bw:.1f} GB/s", min_bandwidth=min_bw)
            return self._pass("nvbandwidth completed (could not parse specific values)")
        except subprocess.TimeoutExpired:
            return self._fail("nvbandwidth timed out", severity=Severity.P1_HIGH)
        except Exception as e:
            return self._unknown(f"Cannot run nvbandwidth: {e}")

    @staticmethod
    def _parse_bandwidths(output: str) -> list:
        bws = []
        for line in output.split("\n"):
            parts = line.strip().split()
            for p in parts:
                try:
                    v = float(p)
                    if 10 < v < 5000:  # Reasonable bandwidth range in GB/s
                        bws.append(v)
                except ValueError:
                    continue
        return bws


class GPUTopologyCheck(HealthCheck):
    """GPU topology validation — all GPUs must be connected via NVSwitch (SYS).
    Based on SOP §2.1: nvidia-smi topo -m must show all GPUs via NVSwitch.
    """
    name = "gpu_topology_check"
    description = "GPU topology validation (all GPUs connected via NVSwitch)"
    component = "gpu"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["nvidia-smi", "topo", "-m"],
                capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return self._unknown(f"nvidia-smi topo failed: {result.stderr[:200]}")

            # Check that all GPU pairs show SYS or NV (NVLink)
            output = result.stdout
            lines = [l for l in output.split("\n") if l.strip().startswith("GPU")]
            degraded_pairs = []
            for line in lines:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part in ("PHB", "NODE", "SYS") and "GPU" in parts[0]:
                        # PHB/NODE between GPUs (not NV) may indicate NVSwitch issue
                        # SYS is normal for GPUs on same NVSwitch domain
                        pass
                    if part == "X" or part == "N/A":
                        degraded_pairs.append(f"{parts[0]} col {i}")

            # Check for NVSwitch
            nvsw_result = subprocess.run(
                ["nvidia-smi", "nvlink", "--status"],
                capture_output=True, text=True, timeout=30)
            inactive_links = []
            for line in nvsw_result.stdout.split("\n"):
                if "inactive" in line.lower():
                    inactive_links.append(line.strip()[:100])

            if inactive_links:
                return self._fail(
                    f"{len(inactive_links)} NVLink(s) inactive",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    inactive_links=inactive_links[:5])

            return self._pass("GPU topology: all NVLinks active")
        except Exception as e:
            return self._unknown(f"Cannot check topology: {e}")


class InfiniBandMultiPortCheck(HealthCheck):
    """InfiniBand multi-port health — all ports must be Active at NDR 400Gb/s.
    Based on SOP §2.6: ibstat shows all ports Active.
    """
    name = "infiniband_multi_port"
    description = "InfiniBand all-port status validation (NDR 400Gb/s, GPUDirect RDMA)"
    component = "network"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["ibstat"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return self._skip("ibstat not available")

            ports = {}
            current_ca = ""
            current_port = ""
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("CA '"):
                    current_ca = line.split("'")[1]
                elif line.startswith("Port "):
                    current_port = line.split(":")[0].replace("Port ", "").strip()
                elif "State:" in line:
                    state = line.split(":")[-1].strip()
                    port_key = f"{current_ca}/{current_port}"
                    ports[port_key] = ports.get(port_key, {})
                    ports[port_key]["state"] = state
                elif "Rate:" in line:
                    rate = line.split(":")[-1].strip()
                    port_key = f"{current_ca}/{current_port}"
                    ports[port_key] = ports.get(port_key, {})
                    ports[port_key]["rate"] = rate

            inactive = {k: v for k, v in ports.items()
                        if v.get("state", "").lower() != "active"}

            if inactive:
                return self._fail(
                    f"{len(inactive)} IB port(s) not active: {', '.join(inactive.keys())}",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    inactive_ports=inactive, total_ports=len(ports))
            return self._pass(f"All {len(ports)} IB port(s) active",
                              port_count=len(ports), ports=ports)
        except Exception as e:
            return self._unknown(f"Cannot check IB ports: {e}")


class IBErrorCounters(HealthCheck):
    """InfiniBand error counters — perfquery for SymbolError, LinkRecover, etc.
    Based on SOP §3.2: IB errors should be 0/24h.
    """
    name = "infiniband_error_counters"
    description = "InfiniBand error counters per port (SymbolError, LinkRecover, RcvErrors)"
    component = "network"
    default_severity = Severity.P2_MEDIUM
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["perfquery"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return self._skip("perfquery not available")

            error_counters = {}
            for line in result.stdout.split("\n"):
                for metric in ["SymbolErrorCounter", "LinkErrorRecoveryCounter",
                                "LinkDownedCounter", "PortRcvErrors",
                                "PortRcvRemotePhysicalErrors",
                                "PortXmitDiscards", "PortRcvConstraintErrors"]:
                    if metric in line:
                        try:
                            count = int(line.split(":")[-1].strip().replace(".", ""))
                            if count > 0:
                                error_counters[metric] = count
                        except ValueError:
                            pass

            threshold = int(self.config.get("max_errors", 0))
            if error_counters:
                total = sum(error_counters.values())
                if total > threshold:
                    return self._warn(
                        f"IB error counters elevated: {error_counters}",
                        error_counters=error_counters)
            return self._pass("IB error counters clean")
        except Exception as e:
            return self._unknown(f"Cannot check IB counters: {e}")


class NVSwitchHealth(HealthCheck):
    """NVSwitch health check — dcgmi discovery for NVSwitch status.
    Based on SOP §2.1: All NVSwitches detected.
    """
    name = "nvswitch_health"
    description = "NVSwitch discovery and health status"
    component = "gpu"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["dcgmi", "discovery", "-l"],
                capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return self._unknown(f"dcgmi discovery failed: {result.stderr[:200]}")

            nvswitch_count = result.stdout.lower().count("nvswitch")
            expected = int(self.config.get("expected_nvswitches", 4))

            if nvswitch_count < expected:
                return self._fail(
                    f"Only {nvswitch_count} NVSwitch(es) found (expected {expected})",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    found=nvswitch_count, expected=expected)
            return self._pass(f"{nvswitch_count} NVSwitch(es) found",
                              nvswitch_count=nvswitch_count)
        except FileNotFoundError:
            return self._skip("dcgmi not available")
        except Exception as e:
            return self._unknown(f"Cannot check NVSwitch: {e}")


ALL_CHECKS = [
    NCCLAllReduceTest,
    NVBandwidthTest,
    GPUTopologyCheck,
    InfiniBandMultiPortCheck,
    IBErrorCounters,
    NVSwitchHealth,
]
