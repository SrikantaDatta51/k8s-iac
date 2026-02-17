# BMaaS Monitoring Dashboard Suite — AI Compute Platform

> **Production-grade Grafana dashboards for Bare Metal as a Service (BMaaS) running NVIDIA B200 GPUs managed via NVIDIA Base Command Manager 11 (BCM11)**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    00 — EXECUTIVE FLEET OVERVIEW                       │
│  Fleet Health Score │ Node States │ SLA Uptime │ Active Alerts         │
│  GPU Fleet Status  │ NVLink Health │ Power/Cooling │ HW Replace Queue  │
└──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────┘
           │          │          │          │          │          │
     ┌─────▼───┐ ┌────▼────┐ ┌──▼───┐ ┌───▼──┐ ┌────▼───┐ ┌───▼────┐
     │ 01 GPU  │ │ 02 Infra│ │03 Net│ │04 Job│ │05 Burn │ │06 SLA  │
     │ Health &│ │Hardware │ │Fabric│ │Wkload│ │  In &  │ │Comply &│
     │ Diag    │ │ Health  │ │ Mon  │ │ Perf │ │ Cert   │ │ Alert  │
     └─────────┘ └─────────┘ └──────┘ └──────┘ └────────┘ └────────┘
```

### Data Flow

```
BCM11 Head Node (CMDaemon)
  ├── Built-in Data Producers (GPUSampler, CPUSampler, ClusterTotal, etc.)
  ├── Redfish Subscriptions (DGX GB200 hardware telemetry)
  ├── NMX Telemetry (NVLink monitoring via NMX Manager)
  ├── IPMI/BMC Metrics (out-of-band hardware health)
  ├── SMART Disk Metrics
  ├── InfiniBand Metrics
  └── Prometheus Exporters ─── scraped by ──→ Prometheus ──→ Grafana Dashboards
```

---

## Dashboard Inventory

### 00 — Executive Fleet Overview ⭐ (Top-Level)

**Purpose**: Single-pane-of-glass for fleet ops. Answer in 5 seconds: *"Is my fleet healthy? Any SLA risk?"*

| Panel | What It Answers |
|-------|----------------|
| **Fleet Health Score** | Overall health 0–100% across all nodes and components |
| **Node State Distribution** | How many nodes are UP / DOWN / CLOSED / BURNING? |
| **GPU Fleet Status** | How many GPUs are healthy / degraded / unhealthy? |
| **SLA Uptime Gauge** | Are we meeting our SLA target (e.g., 99.9%)? |
| **Active Alerts** | How many critical / warning / info alerts right now? |
| **Nodes Requiring Action** | Which nodes need immediate attention and why? |
| **NVLink Domain Health** | Are NVLink domains healthy for multi-node jobs? |
| **Power & Cooling Summary** | PSU health, CDU temperature delta, leak status |
| **Hardware Replacement Queue** | Which nodes are flagged for RMA / replacement? |
| **Job Success Rate** | What % of jobs completed successfully in last 24h? |

---

### 01 — GPU Health & Diagnostics 🔬

**Purpose**: Per-GPU deep-dive. Answer: *"Which GPUs need replacement? Is a GPU about to fail?"*

**Hardware Replacement Decision Signals** (in priority order):

| Signal | Threshold | Action |
|--------|-----------|--------|
| `gpu_ecc_dbe_agg` (Double-Bit ECC) | > 0 | **Immediate replacement** — uncorrectable memory error |
| `gpu_row_remap_failure` | = 1 | **Immediate replacement** — row remapping exhausted |
| `gpu_uncorrectable_remapped_rows` | > 0 | **Schedule replacement** — uncorrectable row remaps |
| `gpu_xid_error` = 48, 63, 64, 74, 79, 92, 94, 95 | Any occurrence | **Investigate immediately** — critical XID errors |
| `gpu_health_overall` | != PASS | **Investigate** — DCGM overall health degraded |
| `gpu_correctable_remapped_rows` | > 512 | **Schedule replacement** — approaching row remap limit |
| `gpu_ecc_sbe_agg` (Single-Bit ECC) | Rising trend | **Monitor closely** — early memory degradation |
| `gpu_thermal_violation` | Sustained > 0 | **Investigate cooling** — thermal throttling |
| `gpu_nvlink_crc_data_errors` | Rising trend | **Investigate NVLink** — interconnect degradation |
| `gpu_health_nvswitch_fatal` | != PASS | **Immediate escalation** — NVSwitch failure |

---

### 02 — Infrastructure & Hardware Health 🏗️

**Purpose**: Physical infrastructure monitoring. Answer: *"Is the data center environment healthy?"*

| Layer | Key Metrics | Alert Triggers |
|-------|-------------|----------------|
| **Power Supply** | PSU active count, input/output power, rail voltage, rail current | PSU count < expected, voltage out of range |
| **Cooling (CDU)** | Liquid flow rate, supply/return temp, differential pressure | Flow < minimum, ΔT > threshold, pressure anomaly |
| **Leak Detection** | Devices with leaks, leak sensor state, isolation status | Any leak detected → immediate alert |
| **CPU Thermal** | CPU1/CPU2 temperature, VRM temperatures | Temp > warning/critical thresholds |
| **Disk Health** | SMART metrics (reallocated sectors, pending sectors, temperature) | SMART pre-fail attributes triggered |
| **BMC/IPMI** | BMC connectivity, firmware status | BMC unreachable |
| **DPU/NIC** | BlueField DPU temperature, port status | DPU temp exceeded, port down |
| **Hardware Profile** | `hardware-profile` data producer match | Profile mismatch detected |

---

### 03 — Network Fabric Monitoring 🌐

**Purpose**: NVLink + InfiniBand fabric health. Answer: *"Can multi-node jobs run reliably?"*

| Component | Metrics | Health Signal |
|-----------|---------|---------------|
| **NVLink Switches** | Up/Down/Closed/Total counts | Any switch DOWN = degraded fabric |
| **NVLink Ports** | Bit error rate, link state, TX/RX bandwidth, link downed count | Error rate > 0, link state != Active |
| **NMX Compute** | Healthy/Degraded/Unhealthy/Unknown node counts | Any node unhealthy |
| **NMX GPU** | Per-GPU NVLink health via NMX telemetry | Degraded bandwidth, non-NVLink GPUs |
| **NMX Domain** | Domain health aggregation | Domain unhealthy = multi-node jobs at risk |
| **NMX Switches** | Switch health, missing NVLink ports | Missing NVLink = reduced bandwidth |
| **InfiniBand** | HCA throughput, error counters | Errors rising, throughput below baseline |
| **GPU Fabric** | `gpu_fabric_status` per GPU | GPU excluded from NVLink domain |

---

### 04 — Workload & Job Performance 📊

**Purpose**: Job-level monitoring. Answer: *"Will this job fail? Are GPUs being used efficiently?"*

**Single-Node Job Failure Prediction**:
- GPU health checks failing on the allocated node
- ECC errors accumulating during job execution
- Memory pressure (`job_memory_failcnt` > 0)
- Thermal throttling (`job_gpu_thermal_violation` > 0)

**Multi-Node Job Failure Prediction**:
- All single-node signals PLUS:
- NVLink errors between nodes (`gpu_nvlink_crc_data_errors` rising)
- InfiniBand errors on any participating node
- NMX domain health degraded for the job's NVLink domain
- GPU fabric status showing excluded GPUs

---

### 05 — Burn-in & Certification ✅

**Purpose**: Node validation before production. Answer: *"Is this node ready for customer workloads?"*

| Phase | What We Monitor | Pass Criteria |
|-------|----------------|---------------|
| **Provisioning** | Node state transitions (`installer_callinginit` → `installer_burning`) | Node reaches `burning` state |
| **GPU Stress** | Temperature, power, ECC errors during stress test | No ECC DBE, temp within spec, no throttling |
| **Memory Stress** | ECC SBE/DBE accumulation during memtest | Zero DBE, SBE below threshold |
| **NVLink Stress** | CRC errors, bandwidth during all-to-all traffic | Zero CRC errors, bandwidth ≥ 95% of spec |
| **Network Stress** | InfiniBand MPI benchmark results | Bandwidth ≥ 95% of spec, latency within spec |
| **Storage** | SMART metrics before/after burn-in | No new reallocated sectors |
| **Hardware Profile** | `node-hardware-profile` comparison | Exact match with reference profile |
| **Certification** | All above checks composite | All PASS → node enters production |

---

### 06 — SLA Compliance & Alerting 📋

**Purpose**: SLA tracking and breach prevention. Answer: *"Are we meeting SLA? What triggered a breach?"*

| Metric | Definition | Target |
|--------|-----------|--------|
| **Node Availability** | `(total_minutes - downtime_minutes) / total_minutes × 100` | ≥ 99.9% |
| **GPU Availability** | `(total_gpu_minutes - degraded_gpu_minutes) / total_gpu_minutes × 100` | ≥ 99.5% |
| **Mean Time to Recovery** | Average duration from node `DOWN` to node `UP` | < 4 hours |
| **Planned Maintenance** | Scheduled maintenance windows (excluded from SLA) | < 8 hours/month |
| **Job Success Rate** | `completed_jobs / (completed_jobs + failed_jobs) × 100` | ≥ 95% |
| **Network Availability** | NVLink + InfiniBand uptime | ≥ 99.9% |

---

## Metrics Reference (BCM11 Sources)

### BCM11 Admin Manual — Appendix G

| Category | Source | Key Metrics |
|----------|--------|-------------|
| **Regular** (G.1.1) | CPUSampler | `LoadOne`, `LoadFive`, `LoadFifteen`, `MemFree`, `MemUsed`, `SwapFree`, `Uptime`, `DiskUsage`, `CPUUser`, `CPUIdle` |
| **NFS** (G.1.2) | nfs-sampler | NFS operation counters |
| **InfiniBand** (G.1.3) | ib-sampler | `ib_rcv_data`, `ib_xmit_data`, `ib_rcv_err`, `ib_xmit_err` |
| **GPU** (G.1.6) | GPUSampler | `gpu_utilization`, `gpu_mem_utilization`, `gpu_temperature`, `gpu_power_usage`, `gpu_ecc_sbe_agg`, `gpu_ecc_dbe_agg` |
| **GPU Profiling** (G.1.7) | GPUProfiler | `gpu_nvlink_total_bandwidth`, `gpu_nvlink_crc_data_errors`, `gpu_nvlink_crc_flit_errors` |
| **Job** (G.1.8) | JobSampler | `job_gpu_utilization`, `job_gpu_mem_utilization`, `job_gpu_wasted`, `job_gpu_xid_error` |
| **IPMI** (G.1.9) | ipmi-sampler | `ipmi_fan_speed`, `ipmi_temperature`, `ipmi_voltage`, `ipmi_power` |
| **Redfish** (G.1.10) | redfish-sampler | `RF_*` metrics (temperatures, power, voltages, fan speeds) |
| **SMART** (G.1.11) | smart-sampler | `smart_reallocated_sector_ct`, `smart_temperature`, `smart_current_pending_sector` |
| **Prometheus** (G.1.12) | Prometheus exporter | Custom PromQL queries |
| **Kubernetes** (G.1.14) | k8s-sampler | Pod/node/container metrics |

### NVIDIA Mission Control Manual — Chapter 10

| Category | Source | Key Metrics |
|----------|--------|-------------|
| **Circuit** (10.1) | redfish_circuit | `CircuitPower`, `CircuitCurrent`, `CircuitPhaseCurrent` |
| **Leak Detection** (10.2) | redfish_leak | `DevicesWithLeaks`, `RF_LD_LeakDetection`, `LeakSensorFaultRack` |
| **NVLink** (10.3) | ClusterTotal, Redfish | `NVLinkSwitchesUp/Down/Total`, `RF_NVLink_Port_*` |
| **Power Shelf** (10.4) | redfish_power_shelf | `RF_Power_Supply_*`, `TotalPowerShelf*` |
| **CDU** (10.5) | MonitoringSystem, AggregateCDU | `CDULiquidFlow`, `CDULiquidReturnTemperature` |
| **GPU** (10.6) | GPUSampler | `gpu_health_*`, `gpu_ecc_*`, `gpu_c2c_*`, `gpu_correctable_remapped_rows` |
| **NMX** (2.2) | sample_nmxm | `nmxm_compute_health_count`, `nmxm_gpu_health_count`, `nmxm_switch_health_count` |

### BCM11 Health Checks

| Category | Key Checks |
|----------|------------|
| **Regular** (G.2.1) | `DeviceIsUp`, `ManagedServicesOk`, `dmesg`, `ssh`, `ntp` |
| **GPU** (G.2.2) | `gpu_health_overall`, `gpu_health_driver`, `gpu_health_mem`, `gpu_health_nvlink`, `gpu_health_pcie`, `gpu_health_sm`, `gpu_health_thermal`, `gpu_health_power` |
| **DGX GB200** (10.10) | All GPU health + `nvsm_pci_health`, `gpu_health_nvswitch_fatal`, `gpu_health_nvswitch_non_fatal`, `gpu_health_mcu`, `gpu_health_inforom`, `gpu_health_hostengine` |
| **Redfish** (G.2.3) | Hardware component health via Redfish API |
| **Hardware Profile** (14.6) | `node-hardware-profile` match check |

---

## Hardware Replacement Decision Tree

```
                    ┌─────────────────────┐
                    │  BCM Health Alert    │
                    │  or Metric Anomaly   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ gpu_ecc_dbe_agg > 0 │──── YES ──→ ⛔ IMMEDIATE REPLACEMENT
                    │ (Double-bit ECC)    │              (Uncorrectable memory error)
                    └──────────┬──────────┘
                               │ NO
                    ┌──────────▼──────────┐
                    │ gpu_row_remap_      │──── YES ──→ ⛔ IMMEDIATE REPLACEMENT
                    │ failure = 1         │              (Row remapping exhausted)
                    └──────────┬──────────┘
                               │ NO
                    ┌──────────▼──────────┐
                    │ gpu_uncorrectable_  │──── YES ──→ ⚠️ SCHEDULE REPLACEMENT
                    │ remapped_rows > 0   │              (within maintenance window)
                    └──────────┬──────────┘
                               │ NO
                    ┌──────────▼──────────────────┐
                    │ XID 48/63/64/74/79/92/94/95 │── YES ──→ ⚠️ INVESTIGATE + DRAIN
                    │ (Critical XID errors)       │           (Run diagnostics, likely RMA)
                    └──────────┬──────────────────┘
                               │ NO
                    ┌──────────▼──────────┐
                    │ gpu_health_overall  │──── FAIL ──→ 🔍 RUN DCGM DIAG LEVEL 3
                    │ != PASS             │              (Determine root cause)
                    └──────────┬──────────┘
                               │ PASS
                    ┌──────────▼──────────┐
                    │ NVSwitch fatal      │──── YES ──→ ⛔ ESCALATE TO NVIDIA
                    │ errors              │              (Fabric-level failure)
                    └──────────┬──────────┘
                               │ NO
                    ┌──────────▼──────────┐
                    │ CDU leak detected / │──── YES ──→ ⛔ EMERGENCY SHUTDOWN
                    │ PSU failure         │              (Facility safety issue)
                    └──────────┬──────────┘
                               │ NO
                    ┌──────────▼──────────┐
                    │ SMART pre-fail or   │──── YES ──→ ⚠️ SCHEDULE DISK REPLACEMENT
                    │ reallocated sectors │
                    └──────────┬──────────┘
                               │ NO
                    ┌──────────▼──────────┐
                    │ Continue Monitoring  │
                    └─────────────────────┘
```

---

## Alert Configuration Best Practices

### Critical Alerts (Page immediately)
- `gpu_ecc_dbe_agg > 0` — Uncorrectable GPU memory error
- `gpu_row_remap_failure == 1` — GPU row remapping failed
- `gpu_health_nvswitch_fatal != PASS` — NVSwitch fatal error
- `DevicesWithLeaks > 0` — Liquid cooling leak detected
- `DeviceIsUp == FAIL` — Node unreachable
- Multiple PSUs failed on same power shelf

### Warning Alerts (Investigate within 4 hours)
- `gpu_correctable_remapped_rows > 256` — Approaching row remap limit
- `gpu_ecc_sbe_agg` rising rapidly — Early memory degradation
- `gpu_thermal_violation > 0` sustained — Cooling issue
- `CDULiquidFlow` below minimum — Reduced cooling capacity
- `NVLinkSwitchesDown > 0` — NVLink fabric degraded

### Info Alerts (Review daily)
- `gpu_ecc_sbe_agg` increasing slowly — Track trend
- `smart_current_pending_sector > 0` — Disk showing pre-fail signs
- Node in `CLOSED` state for > 24 hours — Investigate reason
- Job failure rate > 5% in last hour — Check for infrastructure issues

---

## Burn-in Testing Workflow

### BCM11 Burn-in Integration

BCM11 supports burn-in testing via the node installer. Nodes transition through states:

```
installer_callinginit → installer_burning → burning → UP (success) or FAILED
```

### Burn-in Configuration (via cmsh)

```bash
# Set burn-in configuration for a category
cmsh -c "category use gpu-nodes; set installmode auto; set burnconfig stress-gpu; commit"

# Monitor burn-in progress
cmsh -c "device status -t physicalnode"

# Check hardware profile after burn-in
/cm/local/apps/cmd/scripts/healthchecks/node-hardware-profile -n node001 -s production-b200

# Enable hardware-profile monitoring
cmsh -c "monitoring setup use hardware-profile; set interval 600; set disabled no; commit"
```

### Dashboard 05 tracks:
- Nodes currently in `installer_burning` / `burning` states
- GPU metrics during stress (temperature ramp, ECC errors, throttle events)
- NVLink CRC errors during all-to-all communication tests
- Hardware profile conformance against reference

---

## Grafana Provisioning

Copy dashboards and provisioning config to your Grafana instance:

```bash
# Copy dashboards
cp dashboards/*.json /etc/grafana/dashboards/bmaas/

# Copy provisioning
cp provisioning/dashboards.yaml /etc/grafana/provisioning/dashboards/

# Restart Grafana
systemctl restart grafana-server
```

---

## Quick Start

1. **Clone this repo** to your Grafana server
2. **Update datasource** name in each dashboard JSON if needed (default: `BCM-Prometheus`)
3. **Configure provisioning** by copying `provisioning/dashboards.yaml`
4. **Import dashboards** via Grafana UI or provisioning
5. **Set up alerts** following the alert configuration section above

---

## References

- [BCM11 Administrator Manual](https://support.brightcomputing.com/manuals/11/admin-manual.pdf) — Ch 10 (Monitoring), Ch 11 (Job Monitoring), Ch 14 (Diagnostics), Appendix G (Metrics Reference)
- [NVIDIA Mission Control Manual](https://support.brightcomputing.com/manuals/11/nvidia-mission-control-manual.pdf) — Ch 10 (DGX GB200 Measurables)
- [BCM11 Installation Manual](https://support.brightcomputing.com/manuals/11/installation-manual.pdf) — Ch 11 (Burn-in Testing)
- [BCM11 Containerization Manual](https://support.brightcomputing.com/manuals/11/containerization-manual.pdf) — Container workload monitoring
