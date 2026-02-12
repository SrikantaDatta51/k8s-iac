---
title: "SOP to Certify Node is Healthy"
subtitle: "NVIDIA B200 GPU Nodes — Bare Metal as a Service via NVIDIA Base Command Manager"
date: "2026-02-12"
version: "1.1"
---

\newpage

# 1. Purpose & Scope

This SOP defines the certification process for **NVIDIA B200 GPU nodes** in a BMaaS environment managed by **NVIDIA Base Command Manager (BCM)**. It covers Day Zero commissioning, Day Two continuous monitoring, and RMA recertification.

**Target Platform:** NVIDIA DGX/HGX B200 (Blackwell) — 8× B200 SXM, 192 GB HBM3e per GPU, NVLink5 (1.8 TB/s per GPU), 1000W TDP per GPU (liquid-cooled).

| Phase | Purpose | Trigger |
|:---|:---|:---|
| Day Zero | Full qualification before fleet admission | New node |
| Day Two | Continuous BCM health monitoring | Ongoing |
| RMA Recert | Post-repair recertification → fleet re-admission | Component failure |

# 2. Day Zero — Initial Commissioning

## 2.1 Pre-Flight Checks

| Check | Command | Pass |
|:---|:---|:---|
| GPU Discovery (8× B200) | `nvidia-smi -L` | 8 GPUs detected |
| Driver / CUDA version | `nvidia-smi` | BCM baseline |
| DCGM Agent | `systemctl status nvidia-dcgm` | Running |
| NVSwitch Discovery | `dcgmi discovery -l` | All NVSwitches detected |
| GPU Topology | `nvidia-smi topo -m` | All GPUs via NVSwitch (SYS) |
| ECC Enabled | `nvidia-smi -q -d ECC` | ON — all GPUs |
| Firmware (SBIOS, BMC, VBIOS) | `nvfwupd show_version` | Matches fleet baseline |
| System Health | `sudo nvsm show health` | Healthy |
| InfiniBand (NDR 400G) | `ibstat` | All ports Active |
| PCIe Link | `lspci -vvv` | Gen5 x16, no downgrade |
| Persistent Mode | `nvidia-smi -pm 1` | Enabled |

## 2.2 GPU Burn-In Test

BCM supports node burn-in via its node provisioning pipeline. Additionally, `gpu_burn` is used for sustained GPU stress.

| Attribute | B200 Specification |
|:---|:---|
| Tool | `gpu_burn` + BCM burn-in (node provisioning) |
| Duration | **6 hrs minimum** (12–24 hrs recommended) |
| Workload | Dense matrix multiply (FP64/FP32/TF32/FP8) — 100% util |
| Command | `gpu_burn -tc 21600` |
| Monitor | `nvidia-smi dmon -s pucvmet -d 10` |
| Temp limit | ≤ 70°C sustained (liquid-cooled B200) |
| Power limit | ≤ 1000W TDP per GPU |
| ECC DBE | **0** — any DBE = immediate RMA |
| XID errors | **0** |

## 2.3 DCGM Level 4 Stress

`dcgmi diag -r 4` — ~90 min, all GPUs idle, DCGM agent active.

| Plugin | Validates | Pass |
|:---|:---|:---|
| Deployment | Driver, libraries, DCGM agent | All pass |
| Hardware | PCIe, NVLink, InfoROM, ECC, row remap | Zero errors |
| Integration | PCIe + NVLink5 bandwidth | BW ≥ 90% of 1.8 TB/s |
| SM Stress | CUDA core throughput at max load | Target GFLOPS, zero errors |
| Targeted Stress | Specific SM units | Zero errors |
| Targeted Power | Power delivery at 1000W TDP | Stable, zero throttle |
| Memtest | HBM3e pattern test (192 GB per GPU) | Zero memory errors |
| Pulse Test | PSU transient response | No instability |
| EUD | Numerical engines, data integrity, full HBM3e | All pass |

**Gate:** ALL plugins must report PASS.

## 2.4 NCCL Collective Performance

| Test | Command | B200 Pass Criteria |
|:---|:---|:---|
| All-Reduce | `all_reduce_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 1530 GB/s (85% of 1.8 TB/s) |
| All-Gather | `all_gather_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 1530 GB/s |
| Reduce-Scatter | `reduce_scatter_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 1530 GB/s |
| Broadcast | `broadcast_perf -b 8 -e 8G -f 2 -g 8` | BusBW ≥ 1530 GB/s |
| Multi-Node | `mpirun` + `all_reduce_perf` (cross-node) | ≥ 85% per-port IB line rate |

## 2.5 HPL / HPL-MxP Benchmark

| Test | Purpose | B200 Pass |
|:---|:---|:---|
| HPL (FP64) | Peak FP64 FLOPS | ≥ 70% theoretical peak |
| HPL-MxP | Mixed-precision | ≥ 70% theoretical peak |
| Residual | Numerical correctness | Passed |

```bash
docker run --gpus all --ipc=host nvcr.io/nvidia/hpc-benchmarks:latest \
  mpirun --np 8 /workspace/hpl.sh --dat /workspace/hpl-linux-x86_64/sample-dat/HPL-dgx-8GPU.dat
```

## 2.6 NVLink5 / NVSwitch & Network

| Test | Command | B200 Pass |
|:---|:---|:---|
| NVLink Status | `nvidia-smi nvlink --status` | All links active, NVLink5 speed |
| NVLink Errors | `nvidia-smi nvlink -e` | Zero CRC/replay/recovery |
| NVBandwidth | `nvbandwidth` | D2D ≥ 90% of 1.8 TB/s |
| IB Ports | `ibstat` | Active, NDR 400 Gb/s |
| RDMA BW | `ib_write_bw` | ≥ 90% line rate |
| GPUDirect RDMA | Multi-node NCCL | ≥ 85% per-port line rate |

## 2.7 Storage & System

| Check | Command | Pass |
|:---|:---|:---|
| NVMe SMART | `nvme smart-log /dev/nvme*` | Spare ≥ 80%, zero media errors |
| NVMe Throughput | `fio` (seq + random) | Meets drive spec |
| System Memory | `memtester` | Zero errors |
| CPU Stress | `stress-ng --cpu $(nproc) --timeout 1800s` | Zero failures, no MCEs |
| BMC Sensors | `ipmitool sensor list` | All in range |
| PSU Status | `ipmitool sdr list` | All OK |
| Event Log | `ipmitool sel list` | No critical events |

## 2.8 Day Zero Gate

Node admitted **only if ALL pass:** Pre-Flight ✓ | Burn-In (≥6h, zero errors) ✓ | DCGM L4 (all PASS) ✓ | NCCL (≥85% BW) ✓ | HPL (≥70% FLOPS) ✓ | NVLink5 (healthy) ✓ | IB (active, ≥90% BW) ✓ | NVMe (healthy) ✓ | System (healthy) ✓

Output: Certification record → node marked `CERTIFIED` in BCM.

# 3. Day Two — BCM Health Monitoring

## 3.1 GPU Metrics (DCGM via BCM)

| Metric | DCGM Field | B200 Healthy |
|:---|:---|:---|
| GPU Temp | `DCGM_FI_DEV_GPU_TEMP` | ≤ 70°C (liquid) |
| HBM Temp | `DCGM_FI_DEV_MEMORY_TEMP` | ≤ 95°C |
| Power Draw | `DCGM_FI_DEV_POWER_USAGE` | ≤ 1000W |
| SM Clock | `DCGM_FI_DEV_SM_CLOCK` | Near boost clock |
| ECC SBE | `DCGM_FI_DEV_ECC_SBE_VOL_TOTAL` | 0 |
| ECC DBE | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` | **Must be 0** |
| Retired Pages (SBE) | `DCGM_FI_DEV_RETIRED_SBE` | < 60 |
| Retired Pages (DBE) | `DCGM_FI_DEV_RETIRED_DBE` | **Must be 0** |
| Row Remap Fail | `DCGM_FI_DEV_ROW_REMAP_FAILURE` | **Must be 0** |
| XID Errors | `DCGM_FI_DEV_XID_ERRORS` | 0 |
| NVLink CRC | `DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL` | 0 |
| Thermal Violation | `DCGM_FI_DEV_THERMAL_VIOLATION` | 0 |
| Power Violation | `DCGM_FI_DEV_POWER_VIOLATION` | 0 |
| PCIe Replay | `DCGM_FI_DEV_PCIE_REPLAY_COUNTER` | 0 /24h |

## 3.2 System Metrics & Alerts

| Metric | Source | Healthy |
|:---|:---|:---|
| Inlet Temp | BMC | ≤ 35°C |
| Coolant Temp | BMC | Per spec |
| Fan / Pump | BMC | Normal |
| PSU | BMC | All OK |
| NVMe Spare | smartctl | ≥ 50% |
| IB Errors | perfquery | 0 /24h |

| Severity | Trigger | Action |
|:---|:---|:---|
| **P1** | DBE, row remap fail, XID 48/63/64/79/94/95, GPU off bus | Immediate quarantine |
| **P2** | SBE > 0, retired pages nearing limit, NVLink CRC | Investigate within 4h |
| **P3** | PCIe replay, NVMe spare < 80% | Track; weekly review |

## 3.3 Periodic Re-Validation

| Frequency | Test | Duration |
|:---|:---|:---|
| Weekly | `dcgmi diag -r 1` | ~2 min |
| Monthly | `dcgmi diag -r 3` | ~15 min |
| Quarterly | `dcgmi diag -r 4` + NCCL | ~100 min |
| Annually | Full burn-in + HPL | ~8 hrs |

# 4. RMA Lifecycle & Recertification

## 4.1 RMA Flow

Fault (BCM Alert) → **Quarantine** node → Triage & collect diagnostics → **RMA submission** to NVIDIA.

**Required RMA data:** `nvidia-bug-report.sh`, `dcgmi diag -r 4`, `nvsm show health`, `ipmitool sel elist`, `dmesg` (XIDs), `fieldiag.log`, `nvidia-smi -q`, GPU serial/part#, `nvfwupd show_version`.

## 4.2 Post-RMA Recertification

Same test suite as Day Zero, plus extended soak:

| Phase | Test | Duration |
|:---|:---|:---|
| R1 | Pre-Flight (§2.1) | ~10 min |
| R2 | Burn-In — **12 hrs minimum** | 12 hrs |
| R3 | DCGM Level 4 (§2.3) | ~90 min |
| R4 | NCCL (§2.4) + HPL (§2.5) | ~60 min |
| R5 | NVLink + Network (§2.6) | ~20 min |
| R6 | Storage + System (§2.7) | ~30 min |
| R7 | **24-Hour Soak** under synthetic load | 24 hrs |

**Fleet Re-Admission:** All R1–R7 PASS + firmware matches fleet baseline + 24h soak with zero BCM alerts → node returned to `CERTIFIED` in BCM.

# 5. Certification Summary

| Phase | Test | Tool | Duration | Stress | Components |
|:---|:---|:---|:---|:---|:---|
| D0 | Pre-Flight | nvidia-smi, dcgmi, nvsm | 10 min | — | Full system |
| D0 | Burn-In | gpu_burn / BCM | 6–24h | Max | 8× B200 GPU |
| D0 | DCGM L4 | dcgmi -r 4 | 90 min | Max | GPU, NVLink5, PCIe, HBM3e |
| D0 | NCCL | nccl-tests | 20 min | High | NVLink5, NVSwitch |
| D0 | HPL | HPL (NGC) | 45 min | Max | GPU compute + HBM3e |
| D0 | Network | nvbandwidth, ibtools | 20 min | High | NVLink5, NDR IB |
| D0 | Storage/Sys | fio, stress-ng | 30 min | High | NVMe, CPU, PSU |
| D2 | Monitoring | BCM (DCGM+IPMI) | Ongoing | Passive | Full system |
| RMA | Full Recert | All D0 + 24h soak | ~26h | Max | Full system |

# Appendix A — NVIDIA References

| # | Resource | URL |
|:---|:---|:---|
| 1 | DCGM Documentation | https://docs.nvidia.com/datacenter/dcgm/latest/ |
| 2 | DCGM Diagnostics Guide | https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-diagnostics/ |
| 3 | BCM Administrator Manual | https://docs.nvidia.com/base-command-manager/ |
| 4 | BCM Installation Manual | https://docs.nvidia.com/base-command-manager-installation-guide/ |
| 5 | NVIDIA DGX B200 Datasheet | https://www.nvidia.com/en-us/data-center/dgx-b200/ |
| 6 | NCCL Tests (GitHub) | https://github.com/NVIDIA/nccl-tests |
| 7 | NVBandwidth (GitHub) | https://github.com/NVIDIA/nvbandwidth |
| 8 | HPL Benchmark (NGC) | https://catalog.ngc.nvidia.com/orgs/nvidia/containers/hpc-benchmarks |
| 9 | NVIDIA GPU Burn (GitHub) | https://github.com/wilicc/gpu-burn |
| 10 | NVIDIA Tesla RMA Process | https://docs.nvidia.com/deploy/tesla-rma-process/ |
| 11 | NVSM Documentation | https://docs.nvidia.com/nvsm/ |
| 12 | NVIDIA Firmware Update (nvfwupd) | https://docs.nvidia.com/dgx/nvfwupd-user-guide/ |

---

*SOP-GPU-CERT-001 v1.1 | 2026-02-12 | Confidential — SLA Reference*
