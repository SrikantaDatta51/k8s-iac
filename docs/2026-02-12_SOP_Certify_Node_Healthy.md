---
title: "SOP to Certify Node is Healthy"
subtitle: "Bare Metal as a Service — NVIDIA Base Command Manager"
date: "2026-02-12"
version: "1.0"
classification: "Customer-Facing / SLA Reference"
---

# SOP to Certify Node is Healthy

| Field | Value |
|---|---|
| **Document ID** | SOP-GPU-CERT-001 |
| **Version** | 1.0 |
| **Date** | 2026-02-12 |
| **Scope** | NVIDIA DGX / HGX GPU Nodes — NVIDIA BCM |
| **Classification** | Customer-Facing / SLA Reference |

---

## 1. Certification Lifecycle

| Phase | Purpose | Trigger |
|---|---|---|
| **Day Zero** | Full node qualification before fleet admission | New node received |
| **Day Two — Monitoring** | Continuous health via BCM metrics + periodic re-validation | Ongoing |
| **Day Two — RMA** | Fault → RMA → Recertification → Fleet re-admission | Component failure |

```
  Day Zero ──▶ Fleet (Healthy) ──▶ Day Two Monitoring
                    ▲                      │
                    │            Fault Detected
                    │                      ▼
                    └── Recertify ◀── RMA / Repair
```

---

## 2. Day Zero — Initial Commissioning

### 2.1 Pre-Flight Checks

| # | Check | Command | Pass Criteria |
|---|---|---|---|
| 1 | GPU Discovery | `nvidia-smi -L` | All GPUs detected (e.g., 8× H100) |
| 2 | Driver / CUDA | `nvidia-smi`, `nvcc --version` | Matches BCM-approved baseline |
| 3 | DCGM Agent | `systemctl status nvidia-dcgm` | Active (running) |
| 4 | NVSwitch Discovery | `dcgmi discovery -l` | All NVSwitches detected |
| 5 | GPU Topology | `nvidia-smi topo -m` | All GPUs via NVSwitch (SYS) |
| 6 | ECC Enabled | `nvidia-smi -q -d ECC` | ECC ON — all GPUs |
| 7 | Firmware | `nvfwupd show_version` | SBIOS, BMC, VBIOS match baseline |
| 8 | System Health | `sudo nvsm show health` | All healthy, no alerts |
| 9 | InfiniBand | `ibstat` | All HCA ports Active, correct link rate |
| 10 | PCIe Link | `lspci -vvv` | Correct Gen/Width (no downgrade) |
| 11 | Persistent Mode | `nvidia-smi -pm 1` | Enabled |

---

### 2.2 Burn-In Test

| Attribute | Detail |
|---|---|
| **Tool** | `gpu_burn` |
| **Duration** | **6 hours minimum** (12–24 hrs recommended) |
| **Workload** | Dense matrix multiplication (FP64/FP32/TF32) — 100% GPU util |
| **Command** | `gpu_burn -tc 21600` |
| **Monitor** | `nvidia-smi dmon -s pucvmet -d 10` |

**Pass/Fail:**

| Metric | Pass | Fail |
|---|---|---|
| Compute correctness | Zero miscompares | ≥ 1 → RMA GPU |
| Temperature | ≤ 83°C air / ≤ 70°C liquid | Exceeds → check cooling |
| Throttle events | Zero (thermal + power) | ≥ 1 → investigate |
| ECC SBE | 0 | ≥ 1 → investigate |
| ECC DBE | 0 | ≥ 1 → **immediate RMA** |
| XID errors | 0 | ≥ 1 → triage |

---

### 2.3 DCGM Level 4 Stress Diagnostics

**Command:** `dcgmi diag -r 4`  
**Duration:** ~90 minutes  
**Prerequisite:** GPUs idle, DCGM agent active

| Test Plugin | Validates | Duration | Pass Criteria |
|---|---|---|---|
| Deployment | Driver, libraries, agent | ~1 min | All pass |
| Hardware | PCIe, NVLink, InfoROM, ECC | ~2 min | Zero errors |
| Integration | PCIe + NVLink bandwidth | ~5 min | BW ≥ 90% theoretical |
| SM Stress | CUDA core throughput at max | ~15 min | Target GFLOPS, zero errors |
| Targeted Stress | Specific SM units | ~10 min | Zero errors |
| Targeted Power | Power delivery at TDP | ~10 min | Stable, zero throttle |
| Memtest | HBM pattern test (walking 1s, address) | ~15 min | Zero memory errors |
| Pulse Test | PSU transient response | ~5 min | No instability |
| EUD | Numerical engines, data integrity, full HBM | ~20 min | All subsystems pass |

**Gate:** ALL plugins must report PASS.

---

### 2.4 NCCL Performance Tests

NCCL tests validate multi-GPU collective communication performance over NVLink/NVSwitch.

| # | Test | Command | Pass Criteria |
|---|---|---|---|
| 1 | All-Reduce | `all_reduce_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 85% theoretical NVLink BW |
| 2 | All-Gather | `all_gather_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 85% theoretical |
| 3 | Reduce-Scatter | `reduce_scatter_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 85% theoretical |
| 4 | Broadcast | `broadcast_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 85% theoretical |
| 5 | Multi-Node All-Reduce | `mpirun` + `all_reduce_perf` (cross-node) | BusBW ≥ 85% per-port line rate |

**Reference Bandwidth Targets:**

| Platform | NVLink BW (Unidirectional) | Expected NCCL BusBW |
|---|---|---|
| H100 SXM (NVLink4) | 900 GB/s | ≥ 765 GB/s |
| A100 SXM (NVLink3) | 600 GB/s | ≥ 510 GB/s |
| H200 SXM (NVLink4) | 900 GB/s | ≥ 765 GB/s |

---

### 2.5 HPL / HPL-MxP Benchmark

High Performance Linpack validates sustained compute and numerical accuracy across all GPUs.

| Attribute | Detail |
|---|---|
| **Tool** | NVIDIA HPL (`hpl.sh` from NGC container) |
| **Container** | `nvcr.io/nvidia/hpc-benchmarks:latest` |
| **Duration** | ~30–60 min depending on problem size |
| **Workload** | Dense linear algebra (LU factorization) — stresses compute + memory + interconnect |

| Test | Purpose | Pass Criteria |
|---|---|---|
| **HPL (FP64)** | Peak FP64 FLOPS validation | ≥ 70% of theoretical peak FP64 |
| **HPL-MxP** | Mixed-precision (FP64 + lower precision) | ≥ 70% of theoretical peak mixed-precision |
| **Residual Check** | Numerical correctness | Passed (built into HPL) |

**Example:**
```bash
docker run --gpus all --ipc=host nvcr.io/nvidia/hpc-benchmarks:latest \
  mpirun --np 8 /workspace/hpl.sh --dat /workspace/hpl-linux-x86_64/sample-dat/HPL-dgx-8GPU.dat
```

---

### 2.6 NVLink / NVSwitch & Network Validation

| # | Test | Command | Pass Criteria |
|---|---|---|---|
| 1 | NVLink Status | `nvidia-smi nvlink --status` | All links active, correct speed |
| 2 | NVLink Errors | `nvidia-smi nvlink -e` | Zero CRC/replay/recovery errors |
| 3 | NVBandwidth | `nvbandwidth` | D2D BW ≥ 90% theoretical |
| 4 | IB Port Status | `ibstat` | All ports Active/LinkUp |
| 5 | IB Link Rate | `ibstatus` | Matches spec (e.g., 400 Gb/s NDR) |
| 6 | RDMA Bandwidth | `ib_write_bw` / `ib_read_bw` | ≥ 90% line rate per port |
| 7 | GPUDirect RDMA | Multi-node NCCL test | Cross-node BW ≥ 85% per-port line rate |

---

### 2.7 Storage & System Peripherals

| # | Check | Command | Pass Criteria |
|---|---|---|---|
| 1 | NVMe SMART | `nvme smart-log /dev/nvme*` | Spare ≥ 80%, zero media errors |
| 2 | NVMe Throughput | `fio` (seq R/W + random 4K) | Meets drive spec |
| 3 | System Memory | `memtester` / BIOS memory test | Zero errors |
| 4 | CPU Stress | `stress-ng --cpu $(nproc) --timeout 1800s` | Zero failures, no MCEs |
| 5 | BMC Sensors | `ipmitool sensor list` | All values in normal range |
| 6 | PSU Status | `ipmitool sdr list` | All PSUs OK |
| 7 | System Event Log | `ipmitool sel list` | No critical events |

---

### 2.8 Day Zero Certification Gate

**Node passes if and only if ALL gates are met:**

| Gate | Condition |
|---|---|
| G1 | Pre-Flight — ALL PASS |
| G2 | Burn-In (≥ 6 hrs) — zero errors, zero throttle |
| G3 | DCGM Level 4 — ALL plugins PASS |
| G4 | NCCL — BusBW ≥ 85% theoretical on all collectives |
| G5 | HPL — ≥ 70% peak FLOPS, residual passed |
| G6 | NVLink / NVSwitch — healthy, BW ≥ 90% theoretical |
| G7 | InfiniBand — ports active, BW ≥ 90% line rate |
| G8 | Storage / NVMe — SMART healthy, performance meets spec |
| G9 | System — CPU, memory, PSU, thermals healthy |

**Output:** Certification record (serial, firmware manifest, test logs, operator sign-off). Node marked `CERTIFIED` in BCM.

---

## 3. Day Two — Continuous Health Monitoring (BCM Metrics)

### 3.1 GPU Metrics (DCGM via BCM)

| Metric | DCGM Field | Healthy Range |
|---|---|---|
| GPU Temperature | `DCGM_FI_DEV_GPU_TEMP` | ≤ 83°C air / ≤ 70°C liquid |
| HBM Temperature | `DCGM_FI_DEV_MEMORY_TEMP` | ≤ 95°C |
| GPU Utilization | `DCGM_FI_DEV_GPU_UTIL` | Contextual |
| Power Draw | `DCGM_FI_DEV_POWER_USAGE` | ≤ TDP |
| SM Clock | `DCGM_FI_DEV_SM_CLOCK` | Near boost clock under load |
| ECC SBE (volatile) | `DCGM_FI_DEV_ECC_SBE_VOL_TOTAL` | 0 |
| ECC DBE (volatile) | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` | **Must be 0** |
| Retired Pages (SBE) | `DCGM_FI_DEV_RETIRED_SBE` | < 60 per GPU |
| Retired Pages (DBE) | `DCGM_FI_DEV_RETIRED_DBE` | **Must be 0** |
| Row Remap Failure | `DCGM_FI_DEV_ROW_REMAP_FAILURE` | **Must be 0** |
| XID Errors | `DCGM_FI_DEV_XID_ERRORS` | 0 |
| NVLink CRC Errors | `DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL` | 0 |
| Thermal Violation | `DCGM_FI_DEV_THERMAL_VIOLATION` | 0 |
| Power Violation | `DCGM_FI_DEV_POWER_VIOLATION` | 0 |
| PCIe Replay | `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | 0 over 24h |

### 3.2 System Metrics (BCM / IPMI)

| Metric | Source | Healthy Range |
|---|---|---|
| Inlet Temperature | BMC | ≤ 35°C |
| Fan Speed | BMC | Normal range, no failures |
| PSU Status | BMC | All present & OK |
| NVMe Spare | smartctl | ≥ 50% |
| IB Port Errors | perfquery | 0 over 24h |
| System Event Log | IPMI SEL | No critical entries |

### 3.3 Alert Tiers

| Severity | Trigger | Action |
|---|---|---|
| **P1 Critical** | DBE, row remap fail, XID 48/63/64/79/94/95, GPU off bus | Immediate quarantine + incident |
| **P2 Warning** | SBE > 0, retired pages nearing limit, thermal/NVLink errors | Investigate within 4 hrs |
| **P3 Info** | PCIe replay (intermittent), NVMe spare < 80% | Track; review weekly |

### 3.4 Periodic Re-Validation Schedule

| Frequency | Test | Duration |
|---|---|---|
| Weekly | `dcgmi diag -r 1` | ~2 min |
| Monthly | `dcgmi diag -r 3` | ~15 min |
| Quarterly | `dcgmi diag -r 4` + NCCL bandwidth | ~100 min |
| Annually | Full burn-in (≥ 6 hrs) + HPL | ~8 hrs |

---

## 4. Day Two — RMA Lifecycle & Recertification

### 4.1 Fault → RMA Flow

```
Fault Detected (BCM Alert) → Quarantine Node → Triage & Diagnose → RMA Submission
```

**Required RMA Data:**

| # | Data | Command |
|---|---|---|
| 1 | Bug report | `nvidia-bug-report.sh` |
| 2 | DCGM Level 4 | `dcgmi diag -r 4` |
| 3 | System health | `sudo nvsm show health` |
| 4 | Event log | `ipmitool sel elist` |
| 5 | Kernel log (XIDs) | `dmesg` |
| 6 | Field diagnostics | NVIDIA Field Diagnostic → `fieldiag.log` |
| 7 | Full GPU query | `nvidia-smi -q` |
| 8 | Serial / Part # | GPU serial, board ID |
| 9 | Firmware versions | `nvfwupd show_version` |

### 4.2 Post-RMA Recertification

Recertification follows **the same test suite as Day Zero** with additional rigor.

| Phase | Test | Scope | Duration |
|---|---|---|---|
| R1 | Pre-Flight (§2.1) | Full node | ~10 min |
| R2 | Burn-In — **12 hrs minimum** | All GPUs | 12 hrs |
| R3 | DCGM Level 4 (§2.3) | Full node | ~90 min |
| R4 | NCCL Tests (§2.4) | Full node | ~20 min |
| R5 | HPL / HPL-MxP (§2.5) | Full node | ~45 min |
| R6 | NVLink + Network (§2.6) | Full node | ~20 min |
| R7 | Storage + System (§2.7) | Full node | ~30 min |
| R8 | **24-Hour Soak** — BCM monitoring under synthetic load | Full node | 24 hrs |

**Fleet Re-Admission Gate:**

| Gate | Condition |
|---|---|
| R-G1 | All recertification phases (R1–R8) PASS |
| R-G2 | Firmware matches fleet baseline |
| R-G3 | 24-hour soak — zero BCM alerts |
| R-G4 | Certification record updated with RMA details |

Node returned to `CERTIFIED` / `AVAILABLE` in BCM.

---

## 5. Certification Summary Matrix

| Phase | Test | Tool | Duration | Stress Level | Components |
|---|---|---|---|---|---|
| Day 0 | Pre-Flight | nvidia-smi, dcgmi, nvsm | ~10 min | None | Full system |
| Day 0 | Burn-In | gpu_burn | 6–24 hrs | **Maximum** | All GPUs |
| Day 0 | DCGM Level 4 | dcgmi diag -r 4 | ~90 min | **Maximum** | GPUs, NVLink, PCIe, HBM |
| Day 0 | NCCL Collectives | nccl-tests | ~20 min | **High** | NVLink, NVSwitch |
| Day 0 | HPL / HPL-MxP | HPL (NGC) | ~45 min | **Maximum** | GPU compute + memory |
| Day 0 | NVLink / Network | nvbandwidth, ibtools | ~20 min | **High** | Interconnect, IB |
| Day 0 | Storage / System | fio, stress-ng, ipmitool | ~30 min | **High** | NVMe, CPU, PSU |
| Day 2 | Continuous | BCM (DCGM + IPMI) | Ongoing | Passive | Full system |
| Day 2 | Periodic Diag | dcgmi diag -r 1/3/4 | 2–90 min | Low → Max | All GPUs |
| RMA | Full Recert + Soak | All Day 0 + 24h soak | ~26 hrs | **Maximum** | Full system |

---

## 6. Pass / Fail Quick Reference

| Category | Metric | Pass | Fail Action |
|---|---|---|---|
| ECC DBE | Double-bit errors | 0 | **Immediate RMA** |
| ECC SBE | Single-bit errors | 0 during test | Investigate |
| Retired Pages (DBE) | DBE retirements | 0 | **Immediate RMA** |
| Row Remap | Remap failure | 0 | **Immediate RMA** |
| Temperature | GPU die | ≤ 83°C / 70°C | Check cooling |
| Throttle | Thermal + Power | 0 | Investigate |
| XID | Kernel GPU errors | 0 | Triage by code |
| NVLink CRC | CRC errors | 0 | Reseat/replace |
| NCCL BusBW | Collective bandwidth | ≥ 85% theoretical | Investigate NVSwitch/NVLink |
| HPL FLOPS | Peak FP64 | ≥ 70% theoretical | Investigate |
| IB BW | RDMA throughput | ≥ 90% line rate | Cable/switch check |
| PCIe | Link width/speed | Spec (no downgrade) | Reseat/replace |
| NVMe | Media errors | 0 | Replace drive |
| DCGM L4 | All plugins | PASS | Block admission |
| Burn-In | Miscompares | 0 | RMA GPU |

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-02-12 | Initial release |

---

*Confidentiality: This document is intended as an SLA reference between service provider and customer.*
