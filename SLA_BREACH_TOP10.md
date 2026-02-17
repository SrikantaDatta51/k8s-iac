# Top 10 SLA Breach Questions — BMaaS AI Compute Platform

> **Purpose**: Definitive questions that infrastructure operators must answer to identify, diagnose, and prevent SLA breaches in a Bare Metal as a Service environment running NVIDIA B200 GPUs managed via BCM11.

---

## Q1: Is any node DOWN or unreachable, reducing available compute capacity?

**SLA Impact**: Direct availability breach — every minute of node downtime counts against uptime SLA.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `DeviceIsUp` health check | BCM CMDaemon | `FAIL` = node unreachable |
| Node state | BCM device status | State = `DOWN`, `CLOSED`, or `installer_*` |
| BMC/IPMI reachability | BMC ping | No response = total node failure |

**Dashboard**: `00-Executive Fleet Overview` → Node State Distribution panel

**Remediation**:
1. Check BMC connectivity — if BMC is reachable, attempt `power reset` via cmsh
2. Check node console via Serial Over LAN (SOL): `cmsh -c "device consolesol node001"`
3. If hardware failure confirmed → initiate node replacement (BCM Admin Manual §14.9)
4. Document downtime window for SLA credit calculation

---

## Q2: Are any GPUs experiencing uncorrectable (double-bit) ECC memory errors?

**SLA Impact**: Immediate workload impact — jobs running on affected GPUs will produce incorrect results or crash. SLA breach for data integrity guarantee.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `gpu_ecc_dbe_agg` | GPUSampler (DCGM) | > 0 = **critical**, immediate action |
| `gpu_ecc_dbe_vol` | GPUSampler (DCGM) | > 0 = active errors since last reboot |
| `gpu_row_remap_failure` | GPUSampler (DCGM) | = 1 = row remapping exhausted |
| `gpu_uncorrectable_remapped_rows` | GPUSampler (DCGM) | > 0 = uncorrectable remaps |

**Dashboard**: `01-GPU Health & Diagnostics` → ECC Error Tracking + Row Remapping Status

**Remediation**:
1. **Immediately drain the node** from the workload manager (SLURM/Run:ai)
2. Run DCGM diagnostics: `dcgmi diag -r 3 -j` (Level 3 deep diagnostic)
3. If DBE confirmed → initiate GPU/node RMA with NVIDIA
4. Log incident for SLA breach documentation

---

## Q3: Are critical XID errors occurring that indicate GPU hardware failure?

**SLA Impact**: XID errors cause job crashes. Repeated XID errors on allocated nodes = SLA performance breach.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `job_gpu_xid_error` | JobSampler | Any XID in [48, 63, 64, 74, 79, 92, 94, 95] |
| `gpu_xid_errors` (kernel dmesg) | dmesg health check | Critical XID patterns |
| `gpu_health_overall` | GPUSampler (DCGM) | != `PASS` after XID event |

**Critical XID Error Reference**:
| XID | Meaning | Action |
|-----|---------|--------|
| 48 | Double-bit ECC | Immediate GPU replacement |
| 63 | ECC page retirement limit | Schedule GPU replacement |
| 64 | ECC page retirement/row remap | Investigate, likely replacement |
| 74 | NVLink error | Check NVLink cables/switches |
| 79 | GPU access to NVLink failed | NVLink fabric investigation |
| 92 | High single-bit ECC | Monitor, schedule if trending |
| 94 | Contained ECC error | Monitor closely |
| 95 | Uncontained ECC error | Immediate replacement |

**Dashboard**: `01-GPU Health & Diagnostics` → XID Error History

**Remediation**:
1. Cross-reference XID with the error table above
2. If critical XID → drain node, run diagnostics, initiate RMA
3. If NVLink XID → check NVLink switch health and cable integrity
4. Document XID frequency for trend analysis

---

## Q4: Is the NVLink fabric degraded, impacting multi-node job performance?

**SLA Impact**: Degraded NVLink = reduced GPU-to-GPU bandwidth = multi-node training jobs run slower or fail. SLA performance breach for multi-node workloads.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `NVLinkSwitchesDown` | ClusterTotal | > 0 = fabric degraded |
| `nmxm_domain_health_count{state="unhealthy"}` | NMX Manager | > 0 = domain failure |
| `nmxm_gpu_health_count{state="degraded_bw"}` | NMX Manager | > 0 = reduced bandwidth |
| `RF_NVLink_Port_Nvidia_BitErrorRate` | Redfish | Rising = link degradation |
| `RF_NVLink_Port_Nvidia_LinkDowned` | Redfish | > 0 = link failures |
| `gpu_fabric_status` | GPUSampler | != healthy |

**Dashboard**: `03-Network Fabric Monitoring` → NVLink Fabric Overview + NMX Domain Health

**Remediation**:
1. Identify affected NVLink switches: `cmsh -c "device -t nvlinkswitch status"`
2. Check NVLink port status: `cmsh -c "device use nvswitch001; nvlinkinfo"`
3. If switch hardware failure → engage NVIDIA support for NVLink tray replacement
4. If cable issue → reseat or replace NVLink cables
5. Restrict multi-node jobs to healthy NVLink domains until resolved

---

## Q5: Are GPU temperatures exceeding thresholds, causing thermal throttling?

**SLA Impact**: Thermal throttling reduces GPU clock speeds → workloads run slower → SLA performance breach.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `gpu_temperature` | GPUSampler | > 83°C warning, > 90°C critical |
| `gpu_hbm_memory_temperature` | GPUSampler | > 95°C warning, > 105°C critical |
| `gpu_thermal_violation` | GPUSampler | > 0 = active throttling |
| `gpu_slowdown_temp` | GPUSampler | Approaching slowdown threshold |
| `CDULiquidReturnTemperature` | CDU metrics | > spec = insufficient cooling |
| `CDULiquidFlow` | CDU metrics | < minimum = reduced cooling |

**Dashboard**: `01-GPU Health & Diagnostics` → GPU Temperature & Throttling + `02-Infrastructure` → CDU Cooling

**Remediation**:
1. Check CDU liquid cooling system — flow rate, supply/return temperatures
2. Verify CDU differential pressure is within operating range
3. If CDU failure → escalate to facility management
4. If isolated to one node → check thermal paste, heatsink contact, airflow
5. If widespread → check data center ambient temperature and CRAC/CRAH units

---

## Q6: Has a liquid cooling leak been detected?

**SLA Impact**: Leak detection triggers automatic rack isolation. If nodes are powered down for safety, this causes immediate availability breach and potentially damages hardware.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `DevicesWithLeaks` | Redfish (leak detector) | > 0 = **EMERGENCY** |
| `RF_LD_LeakDetection` | Redfish enum | Leak detected state |
| `LeakSensorFaultRack` | Redfish | Sensor fault (may mask leak) |
| `LeakResponseRackElectricalIsolationStatus` | Redfish | Isolation triggered |
| `LeakResponseRackLiquidIsolationStatus` | Redfish | Liquid isolation triggered |

**Dashboard**: `02-Infrastructure & Hardware Health` → Leak Detection panel

**Remediation**:
1. **SAFETY FIRST** — Follow facility emergency leak response procedures
2. BCM autonomous hardware recovery may auto-isolate the affected rack
3. Identify leak location — manifold vs cold plate (check leak detector 0/1)
4. Coordinate with facility team for cleanup and repair
5. After repair → run burn-in validation before returning nodes to production

---

## Q7: Are power supply units failing or operating in degraded mode?

**SLA Impact**: PSU failure reduces power redundancy. If enough PSUs fail, nodes lose power → availability breach.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `RF_Health_PSU` | Redfish | Not all PSUs healthy |
| `TotalPowerShelfHealthyPSU` | AggregatePowerShelf | != 1 (not all active) |
| `TotalPowerShelfDegradedPSU` | AggregatePowerShelf | = 1 (threshold exceeded) |
| `TotalPowerShelfCriticalPSU` | AggregatePowerShelf | = 1 (critical threshold) |
| `RF_Power_Supply_InputVoltage` | Redfish | Out of nominal range |
| `RF_Power_Supply_code_error` | Redfish | Error code present |

**Dashboard**: `02-Infrastructure & Hardware Health` → Power Supply Unit Health

**Remediation**:
1. Identify failed PSU by rack and slot: check `RF_Power_Supply_Id` parameter
2. Verify remaining PSUs can handle the load (N+1 redundancy check)
3. Schedule PSU hot-swap replacement during next maintenance window
4. If N+1 redundancy lost → escalate to immediate replacement
5. Monitor `RF_Power_Supply_InputPower` totals to ensure within circuit capacity

---

## Q8: Are jobs failing at a rate that exceeds the SLA target?

**SLA Impact**: Job failure rate > SLA threshold (typically > 5%) = direct SLA breach for workload performance.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| Job completion rate | Job accounting (BCM Ch 12) | < 95% over SLA window |
| `job_gpu_xid_error` | JobSampler | XID errors during job execution |
| `job_memory_failcnt` | JobSampler | > 0 = OOM events |
| `job_gpu_thermal_violation` | JobSampler | > 0 = throttling during job |
| `job_gpu_ecc_dbe_agg` | JobSampler | > 0 = memory errors during job |
| `job_gpu_row_remap_failure` | JobSampler | = 1 during job |

**Dashboard**: `04-Workload & Job Performance` → Job Completion Rate + Job GPU Error Correlation

**Remediation**:
1. Correlate failed jobs with node IDs — identify if failures cluster on specific nodes
2. Check GPU health on implicated nodes
3. If infrastructure-caused → drain affected nodes, run diagnostics
4. If user-caused (OOM, bad config) → exclude from SLA calculation per agreement
5. Distinguish between single-node and multi-node failures for root cause

---

## Q9: Is there a hardware configuration drift from the certified baseline?

**SLA Impact**: Hardware drift (wrong firmware, missing components, configuration changes) can cause subtle performance degradation or unexpected failures.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| `hardware-profile` health check | hardware-profile data producer | FAIL = drift detected |
| Node hardware inventory | `hardwareinventoryinfo` | Mismatch with baseline |
| Firmware version | `cm-diagnose` | Version != certified baseline |
| GPU count per node | GPUSampler | < expected GPU count |

**Dashboard**: `05-Burn-in & Certification` → Hardware Profile Validation

**Remediation**:
1. Run `node-hardware-profile -n <node> -s production-b200` to compare with reference
2. Identify mismatched components (memory, disk, NIC, GPU)
3. If firmware drift → schedule firmware update during maintenance
4. If hardware component missing → investigate and replace
5. After correction → re-run burn-in validation

---

## Q10: Has mean time to recovery (MTTR) exceeded the SLA target?

**SLA Impact**: Slow recovery directly extends downtime and may push total unavailability past SLA limits.

**Monitoring Signals**:
| Signal | Source | Threshold |
|--------|--------|-----------|
| Time in DOWN state | BCM node state history | > 4 hours = SLA risk |
| Time from alert to acknowledgment | Alert system | > 15 minutes = slow response |
| Time from diagnosis to resolution | Incident tracking | > 2 hours = slow remediation |
| Spare node availability | Inventory | 0 spares = extended MTTR |
| Parts availability | RMA tracking | Parts on backorder = extended MTTR |

**Dashboard**: `06-SLA Compliance & Alerting` → Mean Time to Recovery + Incident Response SLA

**Remediation**:
1. Review incident response procedures — is the runbook current?
2. Ensure adequate spare parts inventory (GPUs, PSUs, NVLink cables, disks)
3. Implement automated node replacement workflow via BCM (§14.9)
4. Pre-provision spare nodes so they can be swapped in quickly
5. Track MTTR by component type to identify systemic bottlenecks

---

## Summary Matrix

| # | Question | SLA Type | Severity | Dashboard |
|---|----------|----------|----------|-----------|
| 1 | Node DOWN/unreachable | Availability | 🔴 Critical | 00 Executive |
| 2 | GPU DBE ECC errors | Availability + Integrity | 🔴 Critical | 01 GPU Health |
| 3 | Critical XID errors | Performance + Availability | 🔴 Critical | 01 GPU Health |
| 4 | NVLink fabric degraded | Performance | 🟠 High | 03 Network |
| 5 | GPU thermal throttling | Performance | 🟠 High | 01 GPU + 02 Infra |
| 6 | Liquid cooling leak | Availability + Safety | 🔴 Critical | 02 Infrastructure |
| 7 | PSU failure/degraded | Availability | 🟠 High | 02 Infrastructure |
| 8 | Job failure rate high | Performance | 🟡 Medium | 04 Workload |
| 9 | Hardware config drift | Performance | 🟡 Medium | 05 Burn-in |
| 10 | MTTR exceeded target | Availability | 🟠 High | 06 SLA |
