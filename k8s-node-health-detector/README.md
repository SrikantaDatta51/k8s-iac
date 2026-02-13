# Node Health Detector

**Extensible node health detection engine for Kubernetes GPU and CPU infrastructure.**

Runs as a DaemonSet on every node, executing hardware and software health checks on a configurable schedule. Exposes results as Prometheus metrics, triggers automatic node cordon on critical failures, and provides a professional Grafana dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         K8s Cluster                             │
│                                                                 │
│  ┌───────────────────────────────┐  ┌────────────────────────┐  │
│  │  GPU Node (DaemonSet Pod)     │  │   CPU Node (DaemonSet) │  │
│  │                               │  │                        │  │
│  │  ┌─────────────────────────┐  │  │  ┌──────────────────┐  │  │
│  │  │ Agent (agent.py)        │  │  │  │ Agent            │  │  │
│  │  │  ├─ Check Runner        │  │  │  │  ├─ CPU checks   │  │  │
│  │  │  │  ├─ GPU checks (10)  │  │  │  │  ├─ Memory      │  │  │
│  │  │  │  ├─ Multi-node (6)   │  │  │  │  ├─ Storage     │  │  │
│  │  │  │  ├─ CPU checks (4)   │  │  │  │  ├─ Network     │  │  │
│  │  │  │  ├─ Memory (2)       │  │  │  │  └─ Kubernetes  │  │  │
│  │  │  │  ├─ Storage (3)      │  │  │  │                  │  │  │
│  │  │  │  ├─ Network (2)      │  │  │  ├─ Prometheus     │  │  │
│  │  │  │  └─ Kubernetes (3)   │  │  │  │  Exporter :9101 │  │  │
│  │  │  │                      │  │  │  │                  │  │  │
│  │  │  ├─ Prometheus Exporter │  │  │  └─ Node Controller│  │  │
│  │  │  │  (port 9101)         │  │  │     (cordon/       │  │  │
│  │  │  │                      │  │  │      uncordon)     │  │  │
│  │  │  └─ Node Controller     │  │  └──────────────────┘  │  │
│  │  │     (cordon/uncordon)   │  │                        │  │
│  │  └─────────────────────────┘  │                        │  │
│  └───────────────────────────────┘  └────────────────────────┘  │
│                                                                 │
│  ┌─────────────┐    ┌───────────────┐    ┌──────────────────┐  │
│  │ Prometheus   │◄───│ ServiceMonitor│    │ Grafana          │  │
│  │ (scrape)     │    │ (auto-disc.)  │    │ Dashboard        │  │
│  └──────┬───────┘    └───────────────┘    │ (41 panels)      │  │
│         │                                 └──────────────────┘  │
│         └─────────────────────────────────────────►             │
└─────────────────────────────────────────────────────────────────┘
```

## Check Registry

### GPU Health (GPU nodes only) — 16 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `gpu_dcgm_overall_health` | P0 | DCGM | Yes | DCGM_FI_DEV_GPU_HEALTH status |
| `gpu_ecc_errors` | P0 | DCGM | Yes (DBE) | Double-bit ECC (uncorrectable) = data corruption |
| `gpu_xid_errors` | P0 | dmesg | Yes | Critical XIDs: 31,43,45,48,61-64,68,69,73,74,79,92,94,95,119,120 |
| `gpu_temperature` | P1 | DCGM | Yes (>90C) | GPU temp monitoring. B200 liquid: max 70C sustained |
| `gpu_nvlink_health` | P1 | DCGM | Yes (recovery) | NVLink CRC, replay, recovery errors |
| `gpu_pcie_health` | P1 | DCGM | Warn | PCIe replay counter |
| `gpu_power_violation` | P2 | DCGM | No | Power/thermal throttling duration |
| `gpu_memory_utilization` | P2 | DCGM | No | GPU framebuffer usage (>95%) |
| `gpu_row_remapping` | P0 | DCGM | Yes | HBM row remap pending/failure |
| `multi_node_nccl_allreduce` | P1 | nccl-tests | Yes | All-Reduce BusBW >= 1530 GB/s (85% of NVLink5) |
| `multi_node_nvbandwidth` | P1 | nvbandwidth | Yes | D2D >= 1620 GB/s (90% of 1.8 TB/s) |
| `gpu_topology_check` | P0 | nvidia-smi | Yes | All NVLinks active, NVSwitch topology |
| `infiniband_multi_port` | P0 | ibstat | Yes | All IB ports Active at NDR 400Gb/s |
| `infiniband_error_counters` | P2 | perfquery | Warn | SymbolError, LinkRecover, RcvErrors |
| `nvswitch_health` | P0 | dcgmi | Yes | NVSwitch count matches expected (default: 4) |

### CPU Health (all nodes) — 4 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `cpu_mce_errors` | P0 | dmesg | Yes (uncorrectable) | Machine Check Exceptions |
| `cpu_thermal_throttle` | P2 | sysfs | No | core_throttle_count from thermal_throttle |
| `cpu_load_average` | P2 | /proc/loadavg | No | Load relative to CPU count |
| `cpu_soft_lockup` | P0 | dmesg | Yes | Kernel soft lockup / hung task |

### Memory Health (all nodes) — 2 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `memory_ecc_errors` | P0 | EDAC sysfs | Yes (UE) | Uncorrectable = DIMM failure |
| `memory_pressure` | P1 | /proc/meminfo | No | MemAvailable percentage |

### Storage Health (all nodes) — 3 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `disk_smart_health` | P1 | smartctl | Yes | SMART failure prediction |
| `filesystem_pressure` | P1 | statvfs | Yes (>90%) | /, /var, /var/lib/kubelet usage |
| `disk_io_errors` | P1 | dmesg | Yes (>10) | Kernel I/O error messages |

### Network Health (all nodes) — 2 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `nic_link_health` | P1 | sysfs | Warn | Interface link state, rx/tx errors |
| `infiniband_health` | P0 | sysfs + perfquery | Yes | HCA port state, error counters |

### Kubernetes Health (all nodes) — 3 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `kubelet_health` | P0 | systemctl + healthz | Yes | Kubelet process and health endpoint |
| `container_runtime_health` | P0 | systemctl | Yes | containerd/CRI-O process status |
| `node_pressure_conditions` | P1 | kubectl | No | MemoryPressure, DiskPressure, PIDPressure |

---

## Severity Classification

| Level | Label | Response | Example |
|:------|:------|:---------|:--------|
| **P0** | Critical | Immediate cordon + alert (120s grace) | GPU ECC DBE, XID 79, MCE uncorrectable |
| **P1** | High | Cordon + investigate within 4h | Temperature > 90C, SMART failure, NVLink recovery |
| **P2** | Medium | Warning + investigate within 24h | Thermal throttle, elevated SBE, PCIe replay |
| **P3** | Low | Informational — weekly review | NVMe spare < 80%, minor load elevation |

---

## Deployment

### Prerequisites

- Kubernetes cluster with kube-prometheus-stack (Prometheus + Grafana)
- DCGM Exporter on GPU nodes (for live GPU metrics in dashboard)
- Container image built and pushed to your registry

### Build Image

```bash
docker build -t ghcr.io/your-org/node-health-detector:1.0.0 .
docker push ghcr.io/your-org/node-health-detector:1.0.0
```

### Deploy via Helm

```bash
# GPU nodes
helm install nhd-gpu charts/node-health-detector/ \
  -f charts/node-health-detector/values-gpu.yaml \
  -n monitoring --create-namespace

# CPU nodes (separate release)
helm install nhd-cpu charts/node-health-detector/ \
  -f charts/node-health-detector/values-cpu.yaml \
  -n monitoring
```

### Deploy via ArgoCD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: node-health-detector-gpu
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/k8s-iac.git
    path: k8s-node-health-detector/charts/node-health-detector
    targetRevision: main
    helm:
      valueFiles:
        - values-gpu.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Import Grafana Dashboard

```bash
# Generate the dashboard JSON
cd dashboards && python3 generate_dashboard.py node-health-dashboard.json

# Import via Grafana UI: Dashboards → Import → Upload JSON
```

---

## Configuration

Configuration is loaded from `/etc/node-health-detector/config.yaml` (mounted from ConfigMap) or via environment variables:

| Env Var | Default | Description |
|:--------|:--------|:------------|
| `NODE_TYPE` | `gpu` | `gpu` or `cpu` — determines which checks run |
| `CHECK_INTERVAL` | `60` | Seconds between check cycles |
| `METRICS_PORT` | `9101` | Prometheus metrics HTTP port |
| `NODE_NAME` | hostname | Node name (set via Downward API in DaemonSet) |
| `CONFIG_PATH` | `/etc/node-health-detector/config.yaml` | Config file path |

### Config File Example

```yaml
node_type: gpu
interval: 60
auto_cordon: true
auto_uncordon: false    # conservative: human must uncordon
dry_run: false          # set to true for testing
cordon_grace_period: 120

checks:
  gpu_temperature:
    enabled: true
    severity: 1
    critical_temp: 90
    warn_temp: 80
  gpu_ecc_errors:
    enabled: true
    severity: 0
    sbe_threshold: 100
```

---

## Prometheus Metrics

All metrics use the `node_health_` prefix:

| Metric | Type | Labels | Description |
|:-------|:-----|:-------|:------------|
| `node_health_node_healthy` | gauge | node | 1 = healthy, 0 = unhealthy |
| `node_health_should_cordon` | gauge | node | 1 = cordon recommended |
| `node_health_checks_run` | gauge | node | Total checks executed |
| `node_health_passed` | gauge | node | Checks in pass state |
| `node_health_failed` | gauge | node | Checks in fail state |
| `node_health_warned` | gauge | node | Checks in warn state |
| `node_health_check_status` | gauge | node, check, component, severity | Per-check: 0=pass, 1=warn, 2=fail, 3=unknown |
| `node_health_check_cordon` | gauge | node, check, component | Per-check: 1 if cordon requested |
| `node_health_component_status` | gauge | node, component | Worst status per component |
| `node_health_last_check_timestamp_seconds` | gauge | node | Unix timestamp of last check |

---

## Extension Guide — Adding New Checks

This framework is designed for multiple teams to add their own checks.

### Step 1: Create a Check File

Create a new file under `src/checks/<your_category>/`:

```python
# src/checks/storage/nfs_health.py
from ..base import HealthCheck, Severity

class NFSMountHealth(HealthCheck):
    name = "nfs_mount_health"
    description = "Check NFS mount points are responsive"
    component = "storage"            # Your team's component
    default_severity = Severity.P1_HIGH
    interval_seconds = 60
    node_types = None                # None = all nodes, ["gpu"] = GPU only

    def run(self, node_info: dict):
        # Your check logic here
        import os
        nfs_mounts = self.config.get("nfs_mounts", ["/mnt/shared"])
        for mount in nfs_mounts:
            if not os.path.ismount(mount):
                return self._fail(
                    f"NFS mount {mount} is not mounted",
                    severity=Severity.P1_HIGH, cordon=True,
                    mount=mount)
            try:
                os.listdir(mount)
            except OSError as e:
                return self._fail(
                    f"NFS mount {mount} is unresponsive: {e}",
                    cordon=True, mount=mount)
        return self._pass(f"All {len(nfs_mounts)} NFS mounts healthy")

ALL_CHECKS = [NFSMountHealth]
```

### Step 2: Register the Module

Add to `src/check_runner.py` in the `check_modules` dict:

```python
check_modules = {
    "gpu": [...],
    "storage": [
        ("checks.storage.disk_health", "ALL_CHECKS"),
        ("checks.storage.nfs_health", "ALL_CHECKS"),   # YOUR NEW MODULE
    ],
    ...
}
```

### Step 3: Configure

Add to your config YAML:

```yaml
checks:
  nfs_mount_health:
    enabled: true
    severity: 1
    nfs_mounts: ["/mnt/shared", "/mnt/data"]
```

### Step 4: Create Your Team's Grafana Dashboard (optional)

Other teams can create their own dashboards using the same `node_health_check_status` metrics:

```promql
# Your team's check status
node_health_check_status{component="storage", check=~"nfs_.*"}
```

---

## Team Responsibility Model

| Team | Component | Checks They Own | Dashboard |
|:-----|:----------|:----------------|:----------|
| **Compute Platform** | gpu, cpu, memory | GPU DCGM, ECC, XID, NVLink, NCCL, topology, MCE, ECC | Node Health Detector (included) |
| Storage | storage | Disk SMART, filesystem, NFS, Ceph | Team creates own dashboard |
| Network | network | NIC, InfiniBand, BGP, DNS | Team creates own dashboard |
| Platform/SRE | kubernetes | Kubelet, runtime, node conditions | Team creates own dashboard |

The Compute Platform team's dashboard is the one generated by this project. Other teams follow the Extension Guide above to add their checks to the same agent, then build their own Grafana dashboards filtering by their `component` label.

---

## Cordon / Uncordon Behavior

```
Check Fails (should_cordon=True)
         │
         ▼
   ┌─────────────┐
   │ Grace Period │ (default: 120s)
   │ Re-check     │ ← if check passes during grace period,
   │ every cycle  │   cordon is cancelled
   └──────┬──────┘
          │ still failing after grace period
          ▼
   ┌─────────────┐
   │ kubectl      │
   │ cordon node  │
   │              │
   │ + annotate:  │
   │ cordon-reason│
   │ cordon-time  │
   └──────┬──────┘
          │
          ▼
   Node is Unschedulable
   (existing pods keep running)
          │
          │ All checks pass again
          ▼
   ┌─────────────────┐
   │ auto_uncordon:   │
   │   true → uncordon│
   │   false → manual │ (default)
   └─────────────────┘
```

**auto_uncordon defaults to false** (conservative). A human operator must manually uncordon via `kubectl uncordon <node>` after investigating the root cause.

---

## File Structure

```
k8s-node-health-detector/
├── README.md                            # This file
├── Dockerfile
├── config/
│   ├── checks-gpu.yaml                  # GPU node check config
│   └── checks-cpu.yaml                  # CPU node check config
├── src/
│   ├── agent.py                         # Main agent loop
│   ├── check_runner.py                  # Check discovery & execution
│   ├── prometheus_exporter.py           # Metrics HTTP server
│   ├── node_controller.py              # Cordon/uncordon logic
│   └── checks/
│       ├── base.py                      # Base check class (EXTEND THIS)
│       ├── gpu/
│       │   ├── dcgm_health.py           # 10 GPU checks
│       │   └── multi_node.py            # 6 multi-node checks
│       ├── cpu/
│       │   └── cpu_health.py            # 4 CPU checks
│       ├── memory/
│       │   └── mem_health.py            # 2 memory checks
│       ├── storage/
│       │   └── disk_health.py           # 3 storage checks
│       ├── network/
│       │   └── nic_health.py            # 2 network checks
│       └── kubernetes/
│           └── k8s_health.py            # 3 kubernetes checks
├── charts/
│   └── node-health-detector/
│       ├── Chart.yaml
│       ├── values.yaml                  # Default values
│       ├── values-gpu.yaml              # GPU node variant
│       ├── values-cpu.yaml              # CPU node variant
│       └── templates/
│           ├── _helpers.tpl
│           ├── daemonset.yaml
│           ├── rbac.yaml
│           ├── service.yaml             # + ServiceMonitor
│           └── configmap.yaml
└── dashboards/
    ├── generate_dashboard.py            # Dashboard generator
    └── node-health-dashboard.json       # Generated (41 panels)
```

---

## Related: Day Zero / Day Two SOP

This project implements the automated Day Two monitoring defined in:

**SOP: Certify Node is Healthy** (`docs/2026-02-12_SOP_Certify_Node_Healthy.md`)

| SOP Section | Covered By |
|:------------|:-----------|
| §3.1 GPU Metrics (DCGM) | `gpu_dcgm_overall_health`, `gpu_ecc_errors`, `gpu_temperature`, `gpu_nvlink_health`, `gpu_pcie_health`, `gpu_power_violation`, `gpu_row_remapping` |
| §3.2 System Metrics | `cpu_mce_errors`, `disk_smart_health`, `infiniband_error_counters` |
| §3.2 Severity P1/P2/P3 | Severity classification in check configs |
| §2.4 NCCL Performance | `multi_node_nccl_allreduce` |
| §2.6 NVLink/NVSwitch | `gpu_topology_check`, `nvswitch_health`, `multi_node_nvbandwidth` |
| §2.6 InfiniBand | `infiniband_multi_port`, `infiniband_error_counters` |
| §2.1 XID Errors | `gpu_xid_errors` (critical XID list from SOP) |
