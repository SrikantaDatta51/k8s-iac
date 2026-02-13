#!/usr/bin/env python3
"""Kubernetes Health Checks — kubelet, container runtime, pod pressure."""
import subprocess
import json
from ..base import HealthCheck, Severity


class KubeletHealth(HealthCheck):
    name = "kubelet_health"
    description = "Kubelet process and healthz endpoint status"
    component = "kubernetes"
    default_severity = Severity.P0_CRITICAL

    def run(self, node_info: dict):
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "kubelet"],
                capture_output=True, text=True, timeout=10)
            if result.stdout.strip() != "active":
                return self._fail(
                    f"Kubelet not active: {result.stdout.strip()}",
                    severity=Severity.P0_CRITICAL, cordon=True)

            import urllib.request
            try:
                resp = urllib.request.urlopen("http://localhost:10248/healthz", timeout=5)
                if resp.read().decode().strip() == "ok":
                    return self._pass("Kubelet active and healthz endpoint OK")
                return self._warn("Kubelet active but healthz not OK")
            except Exception:
                return self._warn("Kubelet active but healthz endpoint unreachable")
        except Exception as e:
            return self._unknown(f"Cannot check kubelet: {e}")


class ContainerRuntimeHealth(HealthCheck):
    name = "container_runtime_health"
    description = "Container runtime (containerd/CRI-O) process status"
    component = "kubernetes"
    default_severity = Severity.P0_CRITICAL

    def run(self, node_info: dict):
        runtimes = ["containerd", "crio", "dockerd"]
        try:
            for rt in runtimes:
                result = subprocess.run(
                    ["systemctl", "is-active", rt],
                    capture_output=True, text=True, timeout=5)
                if result.stdout.strip() == "active":
                    return self._pass(f"Container runtime '{rt}' is active")

            result = subprocess.run(
                ["pgrep", "-l", "containerd"],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return self._pass("containerd process running")

            return self._fail(
                "No container runtime found active",
                severity=Severity.P0_CRITICAL, cordon=True)
        except Exception as e:
            return self._unknown(f"Cannot check runtime: {e}")


class NodePressure(HealthCheck):
    name = "node_pressure_conditions"
    description = "Node pressure conditions (memory, disk, PID)"
    component = "kubernetes"
    default_severity = Severity.P1_HIGH

    def run(self, node_info: dict):
        try:
            if not subprocess.run(["which", "kubectl"], capture_output=True).returncode == 0:
                return self._skip("kubectl not available")

            import socket
            node_name = socket.gethostname()
            result = subprocess.run(
                ["kubectl", "get", "node", node_name, "-o", "json"],
                capture_output=True, text=True, timeout=15)
            data = json.loads(result.stdout)
            conditions = {c["type"]: c["status"]
                          for c in data.get("status", {}).get("conditions", [])}

            pressures = {}
            for cond in ["MemoryPressure", "DiskPressure", "PIDPressure"]:
                if conditions.get(cond) == "True":
                    pressures[cond] = True

            if pressures:
                return self._fail(
                    f"Node pressure conditions active: {', '.join(pressures.keys())}",
                    severity=Severity.P1_HIGH, cordon=False,
                    pressure_conditions=pressures)

            if conditions.get("Ready") != "True":
                return self._fail(
                    "Node is NOT Ready",
                    severity=Severity.P0_CRITICAL, cordon=True)

            return self._pass(
                "Node Ready, no pressure conditions",
                conditions=conditions)
        except Exception as e:
            return self._unknown(f"Cannot check node conditions: {e}")


ALL_CHECKS = [KubeletHealth, ContainerRuntimeHealth, NodePressure]
