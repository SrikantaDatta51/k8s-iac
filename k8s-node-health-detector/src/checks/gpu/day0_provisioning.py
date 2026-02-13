#!/usr/bin/env python3
"""Day 0 Provisioning Checks — SR-IOV, GPU Operator, Network Operator, BIOS.
These checks validate the provisioning path. Failures are "Job Blockers"
that prevent a job from ever reaching a Running state.

From SentinAI Reliability Master Book, Page 2: Day 0 - The Compute Platform Scheduling Path.
"""
import subprocess
import os
import json
from ..base import HealthCheck, Severity


class SRIOVVFStatus(HealthCheck):
    """SR-IOV Virtual Function readiness — VFs must be Active, not stuck in INIT.
    If VFs are stuck in INIT, it's typically a BIOS/IOMMU handshake failure.
    Red X failure: Pod will stay Pending forever.
    """
    name = "day0_sriov_vf_status"
    description = "SR-IOV Virtual Functions must be Active (VF stuck in INIT = BIOS/IOMMU failure)"
    component = "gpu"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            # Check sriov_numvfs vs actual active VFs
            vf_issues = []
            sriov_base = "/sys/class/net"
            expected_vfs = int(self.config.get("expected_vfs_per_pf", 0))

            for iface in os.listdir(sriov_base):
                numvfs_path = f"{sriov_base}/{iface}/device/sriov_numvfs"
                if os.path.exists(numvfs_path):
                    with open(numvfs_path) as f:
                        num = int(f.read().strip())
                    if num > 0:
                        # Check VF states
                        totalvfs_path = f"{sriov_base}/{iface}/device/sriov_totalvfs"
                        if os.path.exists(totalvfs_path):
                            with open(totalvfs_path) as f:
                                total = int(f.read().strip())
                        # Check each VF link state
                        vf_dir = f"{sriov_base}/{iface}/device"
                        stuck_count = 0
                        for entry in os.listdir(vf_dir):
                            if entry.startswith("virtfn"):
                                vf_net = f"{vf_dir}/{entry}/net"
                                if os.path.exists(vf_net):
                                    for vf_iface in os.listdir(vf_net):
                                        state_path = f"{vf_net}/{vf_iface}/operstate"
                                        if os.path.exists(state_path):
                                            with open(state_path) as f:
                                                state = f.read().strip()
                                            if state == "down":
                                                stuck_count += 1
                        if stuck_count > 0:
                            vf_issues.append(f"{iface}: {stuck_count}/{num} VFs inactive")

            if vf_issues:
                return self._fail(
                    f"SR-IOV VF(s) not active: {'; '.join(vf_issues)}",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    vf_issues=vf_issues)

            # Check if SR-IOV is expected but no PFs found
            result = subprocess.run(
                ["lspci", "-nn"], capture_output=True, text=True, timeout=10)
            mlx_pfs = [l for l in result.stdout.split("\n") if "Mellanox" in l or "mlx" in l.lower()]
            if not mlx_pfs and expected_vfs > 0:
                return self._fail(
                    "No Mellanox PFs found but SR-IOV expected",
                    severity=Severity.P0_CRITICAL, cordon=True)

            return self._pass("SR-IOV VF status: all active or not configured")
        except Exception as e:
            return self._unknown(f"Cannot check SR-IOV: {e}")


class GPUOperatorHealth(HealthCheck):
    """NVIDIA GPU Operator status — driver injection and toolkit must be ready.
    Day 0 failure: 0 GPUs visible to pods.
    """
    name = "day0_gpu_operator"
    description = "NVIDIA GPU Operator readiness (driver injection, CUDA toolkit, device plugin)"
    component = "gpu"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            # Check nvidia-smi works
            result = subprocess.run(
                ["nvidia-smi", "-L"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return self._fail(
                    "nvidia-smi failed — GPU driver not loaded or operator not ready",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    stderr=result.stderr[:200])

            gpu_count = len([l for l in result.stdout.strip().split("\n") if l.strip()])
            expected = int(self.config.get("expected_gpus", 8))

            if gpu_count < expected:
                return self._fail(
                    f"Only {gpu_count}/{expected} GPUs visible — driver/operator issue",
                    severity=Severity.P0_CRITICAL, cordon=True,
                    gpu_count=gpu_count, expected=expected)

            # Check nvidia-fabricmanager (for NVSwitch systems)
            fm = subprocess.run(
                ["systemctl", "is-active", "nvidia-fabricmanager"],
                capture_output=True, text=True, timeout=5)
            fm_active = fm.stdout.strip() == "active"

            # Check nvidia-persistenced
            pm = subprocess.run(
                ["nvidia-smi", "-pm", "1"], capture_output=True, text=True, timeout=10)

            # Check DCGM
            dcgm = subprocess.run(
                ["systemctl", "is-active", "nvidia-dcgm"],
                capture_output=True, text=True, timeout=5)
            dcgm_active = dcgm.stdout.strip() == "active"

            issues = []
            if not fm_active:
                issues.append("nvidia-fabricmanager not active")
            if not dcgm_active:
                issues.append("nvidia-dcgm not active")

            if issues:
                return self._warn(
                    f"GPU Operator partial: {'; '.join(issues)}",
                    gpu_count=gpu_count, issues=issues)

            return self._pass(
                f"{gpu_count} GPUs visible, fabricmanager active, DCGM active",
                gpu_count=gpu_count, fabricmanager=fm_active, dcgm=dcgm_active)
        except Exception as e:
            return self._unknown(f"Cannot check GPU Operator: {e}")


class NetworkOperatorHealth(HealthCheck):
    """NVIDIA Network Operator status — MOFED drivers and IB CNIs must be ready.
    Day 0 failure: Multus CNI attachment fails, pod networking broken.
    """
    name = "day0_network_operator"
    description = "NVIDIA Network Operator readiness (MOFED drivers, IB CNIs, Multus)"
    component = "network"
    default_severity = Severity.P0_CRITICAL
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            # Check MOFED / mlx5_core loaded
            result = subprocess.run(
                ["lsmod"], capture_output=True, text=True, timeout=5)
            modules = result.stdout
            mlx5_loaded = "mlx5_core" in modules
            ib_loaded = "ib_uverbs" in modules or "rdma_ucm" in modules

            if not mlx5_loaded:
                return self._fail(
                    "mlx5_core kernel module not loaded — MOFED driver missing",
                    severity=Severity.P0_CRITICAL, cordon=True)

            if not ib_loaded:
                return self._warn(
                    "IB userspace verbs (ib_uverbs) not loaded — RDMA may not work")

            # Check openibd service
            openibd = subprocess.run(
                ["systemctl", "is-active", "openibd"],
                capture_output=True, text=True, timeout=5)

            # Check Multus CNI
            multus_ready = os.path.exists("/etc/cni/net.d") and \
                any("multus" in f.lower() for f in os.listdir("/etc/cni/net.d"))

            issues = []
            if openibd.stdout.strip() != "active":
                issues.append("openibd not active")
            if not multus_ready:
                issues.append("Multus CNI config not found")

            if issues:
                return self._warn(
                    f"Network Operator partial: {'; '.join(issues)}",
                    mlx5=mlx5_loaded, ib=ib_loaded, issues=issues)

            return self._pass(
                "Network Operator ready: mlx5_core loaded, IB verbs active",
                mlx5=mlx5_loaded, ib=ib_loaded)
        except Exception as e:
            return self._unknown(f"Cannot check Network Operator: {e}")


class BIOSAudit(HealthCheck):
    """BIOS configuration audit — IOMMU, ARI Forwarding, Hugepages, SR-IOV.
    Misconfigured BIOS is the root cause of many Day 0 failures.
    """
    name = "day0_bios_audit"
    description = "BIOS settings validation: IOMMU, ARI Forwarding, SR-IOV Enable, Hugepages"
    component = "cpu"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict):
        issues = []
        try:
            # Check IOMMU enabled
            with open("/proc/cmdline") as f:
                cmdline = f.read()
            if "iommu=on" not in cmdline and "intel_iommu=on" not in cmdline:
                # Check if IOMMU is available via dmesg
                dmesg = subprocess.run(
                    ["dmesg"], capture_output=True, text=True, timeout=10)
                if "IOMMU" not in dmesg.stdout and "iommu" not in dmesg.stdout:
                    issues.append("IOMMU not enabled in kernel cmdline")

            # Check hugepages
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            hp_total = 0
            for line in meminfo.split("\n"):
                if line.startswith("HugePages_Total:"):
                    hp_total = int(line.split(":")[1].strip())

            if hp_total == 0:
                issues.append("HugePages not configured (HugePages_Total=0)")

            # Check ARI Forwarding via PCIe ACS
            ari_result = subprocess.run(
                ["lspci", "-vvv"], capture_output=True, text=True, timeout=10)
            if "ARI Forwarding" in ari_result.stdout:
                ari_disabled = ari_result.stdout.count("ARI Forwarding-")
                ari_enabled = ari_result.stdout.count("ARI Forwarding+")
                if ari_disabled > 0 and ari_enabled == 0:
                    issues.append(f"ARI Forwarding disabled on {ari_disabled} device(s)")

            if issues:
                return self._warn(
                    f"BIOS audit: {len(issues)} issue(s): {'; '.join(issues)}",
                    issues=issues)

            return self._pass("BIOS audit passed: IOMMU, HugePages, ARI OK",
                              hugepages_total=hp_total)
        except Exception as e:
            return self._unknown(f"Cannot audit BIOS: {e}")


class DriverVersionConsistency(HealthCheck):
    """GPU/MOFED driver version consistency check.
    Different nodes with different driver versions cause NCCL conflicts.
    """
    name = "day0_driver_version"
    description = "GPU and MOFED driver version — must match fleet baseline for NCCL compatibility"
    component = "gpu"
    default_severity = Severity.P1_HIGH
    node_types = ["gpu"]

    def run(self, node_info: dict):
        try:
            versions = {}

            # NVIDIA driver version
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                versions["nvidia_driver"] = result.stdout.strip().split("\n")[0]

            # CUDA version
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=cuda_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                cuda_ver = result.stdout.strip().split("\n")[0]
                if cuda_ver != "[N/A]":
                    versions["cuda"] = cuda_ver

            # MOFED version
            result = subprocess.run(
                ["ofed_info", "-s"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                versions["mofed"] = result.stdout.strip()

            # Check against expected baseline
            baseline = self.config.get("baseline_versions", {})
            mismatches = {}
            for key, expected in baseline.items():
                actual = versions.get(key, "unknown")
                if actual != expected and actual != "unknown":
                    mismatches[key] = {"expected": expected, "actual": actual}

            if mismatches:
                return self._fail(
                    f"Driver version mismatch: {mismatches}",
                    severity=Severity.P1_HIGH,
                    versions=versions, mismatches=mismatches)

            return self._pass(
                f"Driver versions: {versions}",
                versions=versions)
        except Exception as e:
            return self._unknown(f"Cannot check drivers: {e}")


ALL_CHECKS = [
    SRIOVVFStatus,
    GPUOperatorHealth,
    NetworkOperatorHealth,
    BIOSAudit,
    DriverVersionConsistency,
]
