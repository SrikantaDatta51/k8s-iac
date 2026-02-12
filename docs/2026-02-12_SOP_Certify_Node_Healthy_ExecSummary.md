---
title: "SOP to Certify Node is Healthy"
subtitle: "Executive Summary — NVIDIA B200 GPU Nodes"
date: "2026-02-12"
version: "1.1"
---

# Executive Summary — GPU Node Health Certification

## Overview

This SOP defines the certification process for **NVIDIA B200 GPU nodes** (Blackwell architecture, 8× B200 SXM, 192 GB HBM3e, NVLink5) in a Bare Metal as a Service environment managed by **NVIDIA Base Command Manager (BCM)**. Certification ensures every GPU node meets compute, memory, interconnect, thermal, and reliability standards before customer workload admission.

## Certification Phases

| Phase | When | Duration | Purpose |
|:---|:---|:---|:---|
| **Day Zero** | New node commissioning | ~10–30 hrs | Full qualification before fleet admission |
| **Day Two** | Ongoing operations | Continuous | BCM-driven health monitoring & periodic re-validation |
| **RMA Recert** | Post-component replacement | ~26 hrs | Recertification + 24h soak before fleet re-admission |

## Day Zero — Test Suite

| Test | Tool | Stress Level | Key B200 Criteria |
|:---|:---|:---|:---|
| Pre-Flight Checks | nvidia-smi, dcgmi, nvsm, ibstat | — | 8× B200 detected, ECC on, FW baseline, NVSwitch, IB NDR active |
| **GPU Burn-In** | gpu_burn / BCM burn-in | **Maximum** | 6–24h @ 100% GPU util, ≤ 70°C, ≤ 1000W, zero ECC/XID errors |
| **DCGM Level 4** | dcgmi diag -r 4 | **Maximum** | 9 plugins: SM stress, memtest (192 GB HBM3e), pulse, EUD — ALL PASS |
| **NCCL Collectives** | nccl-tests | **High** | all-reduce/all-gather/reduce-scatter BusBW ≥ 1530 GB/s (NVLink5) |
| **HPL / HPL-MxP** | NVIDIA HPL (NGC) | **Maximum** | ≥ 70% peak FP64 FLOPS, residual check passed |
| NVLink5 / NVSwitch | nvbandwidth, nvidia-smi | **High** | D2D BW ≥ 90% of 1.8 TB/s, zero CRC/replay errors |
| InfiniBand (NDR) | ibstat, ib_write_bw | **High** | All ports active @ 400 Gb/s, RDMA BW ≥ 90% line rate |
| Storage / System | nvme, fio, stress-ng, ipmitool | **High** | NVMe healthy, CPU/memory zero errors, PSU OK |

**Admission Gate:** Node enters fleet **only** when all tests pass with zero errors.

## Day Two — Continuous Monitoring (BCM)

BCM collects **14 GPU metrics** (via DCGM) and **6 system metrics** (via IPMI/BMC) at 30-second intervals:

- **Critical (P1):** ECC DBE, row remap failure, XID 48/63/64/79/94/95 → immediate quarantine
- **Warning (P2):** ECC SBE, NVLink CRC errors, thermal violations → investigate within 4h
- **Info (P3):** PCIe replay, NVMe spare declining → weekly review

**Periodic re-validation:** Weekly (DCGM L1), monthly (DCGM L3), quarterly (DCGM L4 + NCCL), annually (full burn-in + HPL).

## RMA Recertification

When a component fails, the node is **quarantined**, diagnostics collected, and an RMA submitted to NVIDIA. After component replacement:

1. Full Day Zero test suite re-executed (burn-in extended to 12h minimum)
2. **24-hour soak period** under synthetic load with BCM monitoring — zero alerts required
3. Firmware verified against fleet baseline
4. Node returned to `CERTIFIED` status in BCM

## Component Coverage Matrix

| Component | Day Zero Tests | Day Two Metrics |
|:---|:---|:---|
| GPU Compute (CUDA/Tensor) | Burn-in, DCGM L4 SM stress, HPL | GPU util, SM clock, power |
| GPU Memory (HBM3e 192GB) | DCGM L4 memtest, EUD, burn-in | ECC SBE/DBE, retired pages, row remap |
| NVLink5 (1.8 TB/s) | NCCL, nvbandwidth, DCGM L4 | NVLink CRC errors |
| NVSwitch | NCCL all-reduce, topology check | NVLink CRC, DCGM L4 |
| PCIe Gen5 | DCGM L4 integration, lspci | PCIe replay counter |
| InfiniBand NDR (400G) | ibstat, ib_write_bw, GPUDirect | IB port errors |
| Power (1000W/GPU) | Burn-in, DCGM L4 pulse test | Power draw, thermal/power violations |
| Thermal (liquid-cooled) | Burn-in (sustained), DCGM L4 | GPU temp, HBM temp, inlet/coolant temp |
| NVMe Storage | SMART log, fio | NVMe spare, media errors |
| CPU / System Memory | stress-ng, memtester | MCEs, BMC sensors |
| Firmware | nvfwupd version check | — (validated at commissioning/RMA) |

## References

Full NVIDIA documentation references available in the detailed SOP (Appendix A), including: DCGM Diagnostics Guide, BCM Administrator Manual, NCCL Tests, HPL Benchmarks, and NVIDIA RMA Process documentation.

---

*SOP-GPU-CERT-001 v1.1 | 2026-02-12 | Confidential — SLA Reference*
