#!/usr/bin/env python3
"""Network Health Checks — NIC errors, link status, InfiniBand/RoCE."""
import subprocess
import os
from ..base import HealthCheck, Severity


class NICHealth(HealthCheck):
    name = "nic_link_health"
    description = "Network interface link status and error counters"
    component = "network"
    default_severity = Severity.P1_HIGH

    def run(self, node_info: dict):
        try:
            issues = {}
            base = "/sys/class/net"
            for iface in os.listdir(base):
                if iface == "lo":
                    continue
                operstate_path = f"{base}/{iface}/operstate"
                if not os.path.exists(operstate_path):
                    continue
                with open(operstate_path) as f:
                    state = f.read().strip()
                stats = {}
                for counter in ["rx_errors", "tx_errors", "rx_dropped", "tx_dropped"]:
                    cpath = f"{base}/{iface}/statistics/{counter}"
                    if os.path.exists(cpath):
                        with open(cpath) as f:
                            stats[counter] = int(f.read().strip())

                threshold = int(self.config.get("error_threshold", 100))
                total_errors = stats.get("rx_errors", 0) + stats.get("tx_errors", 0)
                if state == "down" and iface not in self.config.get("ignore_interfaces", []):
                    issues[iface] = {"state": state, "errors": total_errors}
                elif total_errors > threshold:
                    issues[iface] = {"state": state, "errors": total_errors}

            link_down = {k: v for k, v in issues.items() if v["state"] == "down"}
            if link_down:
                return self._fail(
                    f"Network interface(s) DOWN: {', '.join(link_down.keys())}",
                    severity=Severity.P1_HIGH, nic_issues=issues)
            if issues:
                return self._warn(
                    f"Network interface errors: {', '.join(issues.keys())}",
                    nic_issues=issues)
            return self._pass("All network interfaces healthy")
        except Exception as e:
            return self._unknown(f"Cannot check NIC health: {e}")


class InfiniBandHealth(HealthCheck):
    name = "infiniband_health"
    description = "InfiniBand / RoCE port health (HCA status, link errors)"
    component = "network"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            ib_base = "/sys/class/infiniband"
            if not os.path.exists(ib_base):
                return self._skip("No InfiniBand devices found")

            issues = {}
            for hca in os.listdir(ib_base):
                ports_dir = f"{ib_base}/{hca}/ports"
                if not os.path.exists(ports_dir):
                    continue
                for port in os.listdir(ports_dir):
                    state_path = f"{ports_dir}/{port}/state"
                    phys_path = f"{ports_dir}/{port}/phys_state"
                    if os.path.exists(state_path):
                        with open(state_path) as f:
                            state = f.read().strip()
                        phys = ""
                        if os.path.exists(phys_path):
                            with open(phys_path) as f:
                                phys = f.read().strip()
                        if "ACTIVE" not in state.upper():
                            issues[f"{hca}/{port}"] = {"state": state, "phys": phys}

            # Check counters
            try:
                result = subprocess.run(
                    ["perfquery"], capture_output=True, text=True, timeout=10)
                for line in result.stdout.split("\n"):
                    if "SymbolError" in line or "LinkRecover" in line:
                        count = int(line.split(":")[-1].strip().replace(".", ""))
                        if count > int(self.config.get("ib_error_threshold", 100)):
                            issues["counters"] = {"high_error_counters": True}
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            if issues:
                return self._fail(
                    f"InfiniBand issue(s): {', '.join(issues.keys())}",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    ib_issues=issues)
            return self._pass("InfiniBand ports healthy")
        except Exception as e:
            return self._unknown(f"Cannot check InfiniBand: {e}")


ALL_CHECKS = [NICHealth, InfiniBandHealth]
