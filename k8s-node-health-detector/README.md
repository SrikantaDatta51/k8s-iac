# SentinAI Node Health Detector

**Extensible, autonomous node health detection engine for Kubernetes AI infrastructure.**

SentinAI is designed to move from **Alert → Pinpoint Diagnosis in under 120 seconds**. It shifts observability to the edge using a DaemonSet agent on every node, executing hardware and software health checks on a configurable schedule. Results are exposed as Prometheus metrics, with automatic node cordon on critical failures and a professional 55-panel Grafana dashboard.

A node is only **"AI Ready"** when the high-speed InfiniBand fabric, NVLink interconnects, and GPU drivers are not just present, but performing at peak theoretical bandwidth.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         K8s Cluster                                 │
│                                                                     │
│  ┌──────────────────────────────┐  ┌─────────────────────────────┐  │
│  │  GPU Node (DaemonSet Pod)    │  │  CPU Node (DaemonSet Pod)   │  │
│  │                              │  │                             │  │
│  │  ┌─────────────────────┐    │  │  ┌────────────────────┐    │  │
│  │  │ SentinAI Agent      │    │  │  │ SentinAI Agent     │    │  │
│  │  │ ├─ Day 0 Checks (5) │    │  │  │ ├─ CPU checks (4)  │    │  │
│  │  │ ├─ Day 1 Checks (5) │    │  │  │ ├─ Memory (2)      │    │  │
│  │  │ ├─ DCGM/GPU (10)    │    │  │  │ ├─ Storage (3)     │    │  │
│  │  │ ├─ Multi-Node (6)   │    │  │  │ ├─ Network (2)     │    │  │
│  │  │ ├─ Fabric (4)       │    │  │  │ └─ Kubernetes (3)  │    │  │
│  │  │ ├─ CPU/Mem/Disk     │    │  │  │                    │    │  │
│  │  │ ├─ Network/K8s      │    │  │  ├─ Prometheus :9101  │    │  │
│  │  │ │                   │    │  │  └─ Node Controller   │    │  │
│  │  │ ├─ Prometheus :9101 │    │  └─────────────────────────────┘  │
│  │  │ ├─ SRE Bot          │    │                                   │
│  │  │ │  (remediation)    │    │  ┌──────────────────────────────┐ │
│  │  │ └─ Node Controller  │    │  │ NPD (Node Problem Detector)  │ │
│  │  └─────────────────────┘    │  │ ├─ GPU XID Log Monitor       │ │
│  └──────────────────────────────┘  │ ├─ Network Log Monitor      │ │
│                                     │ ├─ System Log Monitor       │ │
│  ┌────────────┐  ┌──────────────┐  │ ├─ check_ib_bw.sh          │ │
│  │ Prometheus  │  │ Grafana      │  │ └─ check_gpu_clocks.sh     │ │
│  │ (scrape)    │  │ "4K Sharp"   │  └──────────────────────────────┘ │
│  │             │  │ (55 panels)  │                                   │
│  └──────┬──────┘  └──────────────┘                                   │
│         └────────────────────────────────►                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## The 4-Layer Analysis Model

| Layer | Phase | What it Catches | Check Modules |
|:------|:------|:----------------|:--------------|
| **Layer 1: Day 0 Provisioning** | Job Blockers | VF stuck, driver mismatch, BIOS, operators | `day0_provisioning.py` |
| **Layer 2: Day 1 Silent Killers** | Performance (30-90% loss) | PCIe training, clock throttle, IB flap | `day1_silent_killers.py` |
| **Layer 3: Day 1 Hard Failures** | Job Crash | XID 48/79, HCA fault, SM partition | `dcgm_health.py`, `day1_silent_killers.py` |
| **Layer 4: Fabric & Collective** | Straggler Detection | LID, MTU, HCA balance, NCCL BW | `fabric_health.py`, `multi_node.py` |

---

## Check Registry — 44 Checks

### Day 0: Provisioning (GPU nodes) — 5 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `day0_sriov_vf_status` | P0 | sysfs | Yes | VF stuck in INIT = BIOS/IOMMU failure |
| `day0_gpu_operator` | P0 | nvidia-smi | Yes | GPU count, fabricmanager, DCGM agent |
| `day0_network_operator` | P0 | lsmod | Yes | mlx5_core, ib_uverbs, Multus CNI |
| `day0_bios_audit` | P1 | /proc + lspci | Warn | IOMMU, ARI Forwarding, HugePages |
| `day0_driver_version` | P1 | nvidia-smi + ofed_info | No | GPU/MOFED version vs fleet baseline |

### Day 1: Silent Killers & Hard Failures (GPU nodes) — 5 checks

| Check | Severity | Marker | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `day1_pcie_training` | P1 | Orange X | Yes | Gen5 x16 expected; Gen4/x8 = 30-50% BW loss |
| `day1_gpu_clock_throttle` | P2 | Orange X | Warn | SM clock >10% below max = throttling |
| `day1_ib_link_flapping` | P1 | Orange X | Yes | mlx5_core Link down events → NCCL retransmits |
| `day1_hca_fault` | P0 | Red X | Yes | ConnectX-7 panic/assert/health compromised |
| `day1_subnet_manager` | P0 | Red X | Yes | SM down = all RDMA blackholed |

### GPU/DCGM Checks (GPU nodes) — 10 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `gpu_dcgm_overall_health` | P0 | DCGM | Yes | DCGM_FI_DEV_GPU_HEALTH |
| `gpu_ecc_errors` | P0 | DCGM | Yes (DBE) | Double-bit ECC = data corruption |
| `gpu_xid_errors` | P0 | dmesg | Yes | XIDs: 31,43,45,48,61-64,68,69,73,74,79,92,94,95,119,120 |
| `gpu_temperature` | P1 | DCGM | Yes (>90C) | Liquid-cooled B200: max 70C sustained |
| `gpu_nvlink_health` | P1 | DCGM | Yes | NVLink CRC, replay, recovery errors |
| `gpu_pcie_health` | P1 | DCGM | Warn | PCIe replay counter |
| `gpu_power_violation` | P2 | DCGM | No | Power/thermal throttling duration |
| `gpu_memory_utilization` | P2 | DCGM | No | GPU framebuffer >95% |
| `gpu_row_remapping` | P0 | DCGM | Yes | HBM row remap pending/failure |

### Multi-Node & NVLink (GPU nodes) — 6 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `multi_node_nccl_allreduce` | P1 | nccl-tests | Yes | BusBW >= 1530 GB/s (85% NVLink5) |
| `multi_node_nvbandwidth` | P1 | nvbandwidth | Yes | D2D >= 1620 GB/s (90% of 1.8 TB/s) |
| `gpu_topology_check` | P0 | nvidia-smi | Yes | All NVLinks active, NVSwitch topology |
| `infiniband_multi_port` | P0 | ibstat | Yes | All IB ports Active at NDR 400Gb/s |
| `infiniband_error_counters` | P2 | perfquery | Warn | SymbolError, LinkRecover, RcvErrors |
| `nvswitch_health` | P0 | dcgmi | Yes | NVSwitch count matches expected |

### Fabric Certification (GPU nodes) — 4 checks

| Check | Severity | Source | Cordon | Description |
|:------|:---------|:-------|:-------|:------------|
| `fabric_lid_assignment` | P0 | ibstat | Yes | Every port must have a unique LID from SM |
| `fabric_mtu_parity` | P1 | ibstat | No | Switch at 4096, node at 1500 = packet drops |
| `fabric_hca_traffic_balance` | P0 | sysfs | Yes | Silent HCA = straggler in collective |
| `fabric_ib_bandwidth` | P1 | ib_write_bw | Yes | Active BW test >= 360 Gb/s (90% of NDR 400G) |

### CPU, Memory, Storage, Network, K8s (all nodes) — 14 checks

| Check | Severity | Source | Cordon |
|:------|:---------|:-------|:-------|
| `cpu_mce_errors` | P0 | dmesg | Yes (uncorrectable) |
| `cpu_thermal_throttle` | P2 | sysfs | No |
| `cpu_load_average` | P2 | /proc/loadavg | No |
| `cpu_soft_lockup` | P0 | dmesg | Yes |
| `memory_ecc_errors` | P0 | EDAC sysfs | Yes (UE) |
| `memory_pressure` | P1 | /proc/meminfo | No |
| `disk_smart_health` | P1 | smartctl | Yes |
| `filesystem_pressure` | P1 | statvfs | Yes (>90%) |
| `disk_io_errors` | P1 | dmesg | Yes |
| `nic_link_health` | P1 | sysfs | Warn |
| `infiniband_health` | P0 | perfquery | Yes |
| `kubelet_health` | P0 | healthz | Yes |
| `container_runtime_health` | P0 | systemctl | Yes |
| `node_pressure_conditions` | P1 | kubectl | No |

---

## XID Encyclopedia (from SentinAI Page 4)

The SRE Bot maps kernel XIDs to specific hardware components:

| XID | Category | Component | Root Cause | Action |
|:----|:---------|:----------|:-----------|:-------|
| 31 | MMU | Memory | GPU MMU error (invalid access) | Cordon |
| 32 | Bus | PCIe | DMA controller error; PCIe signal quality | Cordon |
| 43 | App/Driver | Compute | GPU stopped processing; software fault | Warn |
| 48 | **Critical** | **VRAM** | **Double-Bit ECC: unrecoverable** | **Cordon + Taint** |
| 61 | Internal | GPU | Microcontroller error (FW/HW) | Cordon |
| 74 | Interconnect | **NVLink** | **NVLink fabric failure** | **Cordon** |
| 79 | Bus | **PCIe** | **GPU Fallen off Bus** | **Cordon + Taint** |
| 94 | Internal | GPU | Contained ECC (row remap recommended) | Cordon |
| 95 | Internal | GPU | Uncontained ECC (data corruption) | Cordon |
| 119 | Internal | GPU | GSP firmware error | Cordon |
| 149 | Hardware | Power/Thermal | Fatal Link event (newer arch) | Cordon |

---

## Autonomous SRE Bot — Remediation Matrix

| Trigger | Action | Reason |
|:--------|:-------|:-------|
| **XID 48 or 79** | Cordon + Taint `NoSchedule` + Terminate Pods | High risk of data corruption |
| **HCA Fault** | Immediate cordon + taint | RDMA traffic blackholed |
| **Link Flapping** | Annotate `NetworkDegraded` + Alert on-call | Perf impact only (don't crash job yet) |
| **VF Stuck in INIT** | `systemctl restart openibd` → if fail → cordon | Try soft fix first |
| **P0 Critical (any)** | Cordon after 120s grace period | Grace period allows re-check |
| **All checks pass** | Auto-uncordon (if enabled; default: off) | Conservative: human must uncordon |

---

## Grafana "4K Sharp" Dashboard — 55 Panels

Split into Day 0 and Day 1 panes matching the SentinAI architecture:

| Section | Panels | What It Shows |
|:--------|:-------|:-------------|
| **Node Health Overview** | 12 | Health/Cordon stat, pass/warn/fail counts, per-component status |
| **All Checks Table** | 1 | Every check with color-coded status, severity, component |
| **Check Status Over Time** | 3 | Component health, failed counts, individual check lines |
| **GPU Health** | 7 | DCGM: temp, ECC, power, NVLink, memory, check/cordon status |
| **Day 0 — Provisioning** | 2 | SR-IOV, operators, BIOS, driver checks + cordon signals |
| **Day 1 — Runtime** | 7 | Silent killers, hard failures, XID timeline, PCIe gen/width, SM clocks, violations |
| **Fabric & IB** | 2 | Fabric cert checks, HCA traffic balance |
| **CPU/Memory/Storage** | 2 | Non-GPU component checks |
| **Severity Breakdown** | 5 | P0-P3 counts + failing-by-severity timeline |
| **Cordon History** | 4 | Cordon signal, last check, freshness, health status |

---

## NPD (Node Problem Detector) Integration

Custom log monitors and active check plugins deployed via ConfigMap:

### Log Monitors
| Monitor | Regex Pattern | NPD Condition |
|:--------|:--------------|:-------------|
| GPU XID 48 | `NVRM: Xid.*48` | `GPUHardwareFail` |
| GPU XID 79 | `NVRM: Xid.*79` | `GPUHardwareFail` |
| NVLink XID 74 | `NVRM: Xid.*74` | `GPUNVLinkFail` |
| IB Link Down | `mlx5_core.*Link down` | `NetworkLinkFail` |
| HCA Fault | `mlx5_core.*internal error` | `HCAFault` |
| MCE | `mce:.*uncorrected` | `KernelHardwareFault` |
| Soft Lockup | `BUG: soft lockup` | `KernelHardwareFault` |
| OOM Kill | `Out of memory.*Kill` | (temporary event) |

### Active Check Plugins
| Plugin | Interval | What It Does |
|:-------|:---------|:-------------|
| `check_ib_bw.sh` | 600s | Verifies IB port is Active (400Gbps NDR) |
| `check_gpu_clocks.sh` | 120s | SM clock vs max; >10% delta = throttle |

---

## Deployment

### Build & Push

```bash
docker build -t ghcr.io/your-org/node-health-detector:1.0.0 .
docker push ghcr.io/your-org/node-health-detector:1.0.0
```

### Deploy via Helm

```bash
# GPU nodes (44 checks)
helm install nhd-gpu charts/node-health-detector/ \
  -f charts/node-health-detector/values-gpu.yaml \
  -n monitoring --create-namespace

# CPU nodes (14 checks)
helm install nhd-cpu charts/node-health-detector/ \
  -f charts/node-health-detector/values-cpu.yaml \
  -n monitoring
```

### Deploy via ArgoCD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sentinai-gpu
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
cd dashboards && python3 generate_dashboard.py
# Import node-health-dashboard.json → Grafana → Dashboards → Import
```

---

## Prometheus Metrics

All metrics use the `node_health_` prefix:

| Metric | Type | Labels | Description |
|:-------|:-----|:-------|:------------|
| `node_health_node_healthy` | gauge | node | 1 = healthy, 0 = unhealthy |
| `node_health_should_cordon` | gauge | node | 1 = cordon recommended |
| `node_health_checks_run` | gauge | node | Total checks executed |
| `node_health_passed` | gauge | node | Checks passing |
| `node_health_failed` | gauge | node | Checks failing |
| `node_health_warned` | gauge | node | Checks warning |
| `node_health_check_status` | gauge | node, check, component, severity | Per-check: 0=pass, 1=warn, 2=fail |
| `node_health_check_cordon` | gauge | node, check, component | Per-check: 1 if cordon requested |
| `node_health_component_status` | gauge | node, component | Worst status per component |
| `node_health_last_check_timestamp_seconds` | gauge | node | Last check unix timestamp |

---

## Extension Guide — Adding New Checks

### Step 1: Create Check File

```python
# src/checks/storage/nfs_health.py
from ..base import HealthCheck, Severity

class NFSMountHealth(HealthCheck):
    name = "nfs_mount_health"
    description = "NFS mount point responsiveness"
    component = "storage"
    default_severity = Severity.P1_HIGH
    node_types = None  # all nodes

    def run(self, node_info: dict):
        nfs_mounts = self.config.get("nfs_mounts", ["/mnt/shared"])
        for mount in nfs_mounts:
            if not os.path.ismount(mount):
                return self._fail(f"NFS {mount} not mounted", cordon=True)
        return self._pass(f"All {len(nfs_mounts)} NFS mounts healthy")

ALL_CHECKS = [NFSMountHealth]
```

### Step 2: Register in `check_runner.py`

### Step 3: Configure in YAML

### Step 4: Build team-specific Grafana dashboard filtering `{component="storage"}`

---

## Team Responsibility Model

| Team | Component | Checks | Dashboard |
|:-----|:----------|:-------|:----------|
| **Compute Platform** | gpu, cpu, memory | DCGM, XID, NVLink, NCCL, Day 0/1, fabric | SentinAI (included) |
| Storage | storage | SMART, filesystem, NFS, Ceph | Team builds own |
| Network | network | NIC, IB, BGP, DNS | Team builds own |
| Platform/SRE | kubernetes | Kubelet, runtime, conditions | Team builds own |

---

## Operational Runbook: "The NCCL Timeout"

1. **Check Grafana:** Is it fleet-wide or single-node?
2. **If Single-Node:** Check NPD for XID 74 (NVLink) or IB Link Flapping
3. **If Fleet-Wide:** Check Subnet Manager for routing convergence delays
4. **Pinpoint:** Identify the "Rank 0" node that timed out first
5. **Action:** Drain and isolate the culprit

---

## File Structure

```
k8s-node-health-detector/
├── README.md
├── Dockerfile
├── config/
│   ├── checks-gpu.yaml                         # GPU config (44 checks)
│   └── checks-cpu.yaml                         # CPU config (14 checks)
├── src/
│   ├── agent.py                                # Main agent loop
│   ├── check_runner.py                         # Discovery & execution
│   ├── prometheus_exporter.py                  # Metrics HTTP :9101
│   ├── node_controller.py                      # SRE Bot + cordon/uncordon
│   └── checks/
│       ├── base.py                             # HealthCheck base class
│       ├── gpu/
│       │   ├── dcgm_health.py                  # 10 DCGM checks
│       │   ├── multi_node.py                   # 6 multi-node checks
│       │   ├── day0_provisioning.py            # 5 Day 0 checks
│       │   └── day1_silent_killers.py          # 5 Day 1 checks
│       ├── cpu/cpu_health.py                   # 4 CPU checks
│       ├── memory/mem_health.py                # 2 memory checks
│       ├── storage/disk_health.py              # 3 storage checks
│       ├── network/
│       │   ├── nic_health.py                   # 2 NIC checks
│       │   └── fabric_health.py                # 4 fabric certification
│       └── kubernetes/k8s_health.py            # 3 K8s checks
├── charts/node-health-detector/
│   ├── Chart.yaml
│   ├── values.yaml / values-gpu.yaml / values-cpu.yaml
│   └── templates/
│       ├── daemonset.yaml, rbac.yaml, service.yaml, configmap.yaml
│       └── npd-config.yaml                     # NPD log monitors + scripts
└── dashboards/
    ├── generate_dashboard.py
    └── node-health-dashboard.json              # 55 panels
```
