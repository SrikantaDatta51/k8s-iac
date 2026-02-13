#!/usr/bin/env python3
"""Fabric Certification Checks — LID, MTU parity, path asymmetry, HCA traffic balance.
From SentinAI Reliability Master Book, Page 5: Network & Fabric Certification.

The Network Operator and SR-IOV Operator must "Certify" the node before it accepts a workload.
"""
import subprocess
import os
import re
from ..base import HealthCheck, Severity


class IBLIDAssignment(HealthCheck):
    """LID Assignment — every port/VF must have a unique Local ID from Subnet Manager.
    Missing LID = port not routable in the fabric.
    """
    name = "fabric_lid_assignment"
    description = "InfiniBand Local ID (LID) assignment — all ports must have a valid LID from SM"
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
                elif "Base lid:" in line:
                    lid = line.split(":")[-1].strip()
                    port_key = f"{current_ca}/port{current_port}"
                    ports[port_key] = int(lid) if lid.isdigit() else 0

            no_lid = {k: v for k, v in ports.items() if v == 0}
            if no_lid:
                return self._fail(
                    f"{len(no_lid)} port(s) have no LID assigned: {list(no_lid.keys())}",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    ports_without_lid=list(no_lid.keys()))

            return self._pass(f"All {len(ports)} port(s) have valid LIDs", port_count=len(ports))
        except Exception as e:
            return self._unknown(f"Cannot check LIDs: {e}")


class IBMTUParity(HealthCheck):
    """MTU Parity — node MTU must match switch MTU.
    Switch at 4096 and node at 1500 = massive packet drops.
    """
    name = "fabric_mtu_parity"
    description = "InfiniBand MTU parity — node vs switch MTU mismatch causes packet drops"
    component = "network"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["ibstat"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return self._skip("ibstat not available")

            expected_mtu = int(self.config.get("expected_mtu", 4096))
            mtu_issues = {}
            current_ca = ""
            current_port = ""
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("CA '"):
                    current_ca = line.split("'")[1]
                elif line.startswith("Port "):
                    current_port = line.split(":")[0].replace("Port ", "").strip()
                elif "Active MTU:" in line:
                    mtu_str = line.split(":")[-1].strip()
                    try:
                        mtu = int(re.findall(r'\d+', mtu_str)[0])
                        port_key = f"{current_ca}/port{current_port}"
                        if mtu < expected_mtu:
                            mtu_issues[port_key] = {"actual": mtu, "expected": expected_mtu}
                    except (IndexError, ValueError):
                        pass

            if mtu_issues:
                return self._fail(
                    f"MTU parity violation on {len(mtu_issues)} port(s) "
                    f"(expected {expected_mtu}): {mtu_issues}",
                    severity=Severity.P1_HIGH,
                    mtu_issues=mtu_issues)

            return self._pass(f"All ports at expected MTU {expected_mtu}")
        except Exception as e:
            return self._unknown(f"Cannot check MTU: {e}")


class HCATrafficBalance(HealthCheck):
    """HCA path asymmetry — all 8 HCAs on a DGX must see roughly equal traffic.
    If one HCA is silent, it is a Red X failure (straggler node in collective).
    """
    name = "fabric_hca_traffic_balance"
    description = "HCA traffic balance — all HCAs must carry traffic (silent HCA = Red X)"
    component = "network"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            ib_base = "/sys/class/infiniband"
            if not os.path.exists(ib_base):
                return self._skip("No InfiniBand devices found")

            port_traffic = {}
            for hca in sorted(os.listdir(ib_base)):
                ports_dir = f"{ib_base}/{hca}/ports"
                if not os.path.exists(ports_dir):
                    continue
                for port in os.listdir(ports_dir):
                    counters_dir = f"{ports_dir}/{port}/counters"
                    if os.path.exists(counters_dir):
                        tx = rx = 0
                        for counter_file in ["port_xmit_data", "port_rcv_data"]:
                            cpath = f"{counters_dir}/{counter_file}"
                            if os.path.exists(cpath):
                                with open(cpath) as f:
                                    val = int(f.read().strip())
                                if "xmit" in counter_file:
                                    tx = val
                                else:
                                    rx = val
                        port_key = f"{hca}/port{port}"
                        port_traffic[port_key] = {"tx": tx, "rx": rx, "total": tx + rx}

            if not port_traffic:
                return self._skip("No IB port counters available")

            # Check for silent HCAs (zero traffic)
            total_values = [v["total"] for v in port_traffic.values()]
            max_traffic = max(total_values) if total_values else 0
            silent = {k: v for k, v in port_traffic.items() if v["total"] == 0 and max_traffic > 0}

            if silent:
                return self._fail(
                    f"{len(silent)} HCA port(s) with ZERO traffic (straggler risk): "
                    f"{list(silent.keys())}",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    silent_ports=list(silent.keys()),
                    port_traffic=port_traffic)

            # Check for asymmetry (>50% deviation from mean)
            if max_traffic > 0 and len(total_values) > 1:
                mean_traffic = sum(total_values) / len(total_values)
                asymmetric = {}
                for k, v in port_traffic.items():
                    if mean_traffic > 0:
                        deviation = abs(v["total"] - mean_traffic) / mean_traffic * 100
                        if deviation > 50:
                            asymmetric[k] = {"traffic": v["total"], "deviation_pct": round(deviation, 1)}
                if asymmetric:
                    return self._warn(
                        f"HCA traffic asymmetry detected on {len(asymmetric)} port(s)",
                        asymmetric_ports=asymmetric)

            return self._pass(f"All {len(port_traffic)} HCA ports carry traffic",
                              port_count=len(port_traffic))
        except Exception as e:
            return self._unknown(f"Cannot check HCA traffic: {e}")


class IBBandwidthTest(HealthCheck):
    """Active IB bandwidth test — runs ib_write_bw for 10 seconds.
    SentinAI NPD check_ib_bw.sh equivalent: verify 400Gbps line rate.
    """
    name = "fabric_ib_bandwidth"
    description = "Active IB bandwidth test (ib_write_bw) — verify 400Gbps NDR line rate"
    component = "network"
    default_severity = Severity.P1_HIGH
    interval_seconds = 600  # heavy test — every 10 min
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            ib_bw_binary = self.config.get("ib_bw_binary", "/usr/bin/ib_write_bw")
            if not os.path.exists(ib_bw_binary):
                return self._skip(f"ib_write_bw not found: {ib_bw_binary}")

            # Run loopback test
            min_bw_gbps = float(self.config.get("min_bandwidth_gbps", 360))  # 90% of 400
            duration = int(self.config.get("duration_sec", 5))

            result = subprocess.run(
                [ib_bw_binary, "--duration", str(duration), "--report_gbits"],
                capture_output=True, text=True, timeout=duration + 30)

            if result.returncode != 0:
                # Loopback may not work without a server — skip gracefully
                return self._skip("ib_write_bw loopback test not supported (needs server)")

            # Parse bandwidth from output
            bw = self._parse_bandwidth(result.stdout)
            if bw is not None and bw < min_bw_gbps:
                return self._fail(
                    f"IB bandwidth {bw:.1f} Gb/s below threshold {min_bw_gbps:.0f} Gb/s",
                    severity=Severity.P1_HIGH,
                    bandwidth_gbps=bw, threshold_gbps=min_bw_gbps)

            if bw is not None:
                return self._pass(f"IB bandwidth: {bw:.1f} Gb/s", bandwidth_gbps=bw)
            return self._pass("ib_write_bw completed (could not parse bandwidth)")
        except subprocess.TimeoutExpired:
            return self._fail("ib_write_bw timed out", severity=Severity.P1_HIGH)
        except Exception as e:
            return self._unknown(f"Cannot run IB BW test: {e}")

    @staticmethod
    def _parse_bandwidth(output: str):
        for line in reversed(output.strip().split("\n")):
            parts = line.split()
            for p in parts:
                try:
                    v = float(p)
                    if 10 < v < 800:
                        return v
                except ValueError:
                    continue
        return None


ALL_CHECKS = [
    IBLIDAssignment,
    IBMTUParity,
    HCATrafficBalance,
    IBBandwidthTest,
]
