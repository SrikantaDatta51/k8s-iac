#!/usr/bin/env python3
"""Dashboard 02 — Infrastructure & Hardware Health.
Power, cooling, storage, memory/CPU, network. All real BCM11 metrics.

v4 OVERHAUL:
- All devices_* → nodes_*
- No gauges
- REMOVED: leak detection (not available)
- REMOVED: DPU panels (no DPUs in fleet)
- REMOVED: IB nodes stat panels (not available)
- REMOVED: proc_running (not showing data)
- Power: gpu_power_usage + cpu_power_usage per entity
- Thermal aggregates kept with better descriptions
"""
import json, sys
from panel_builders import *

def build_02():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: Power & Energy
    # ════════════════════════════════════════════════════════
    panels.append(row("Power & Energy", y)); y += 1

    panels.append(ts(
        "GPU Power per Entity",
        "WHY: GPU power draw per DGX node. B200 = 8 × 1000W = 8kW max.\n\n"
        "METRIC: gpu_power_usage — per-entity aggregate GPU power.\n"
        "SIGNIFICANCE: Sustained at TDP = healthy. Below during load = throttling.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_power_usage{' + EC + '}','{{entity}}')],
        axis="GPU Power", unit="watt"))

    panels.append(ts(
        "CPU Power per Entity",
        "WHY: CPU handles job orchestration, data loading, I/O.\n\n"
        "METRIC: cpu_power_usage — per-entity CPU power.\n"
        "NOTE: Typically 300-500W for dual-socket Grace CPUs.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('cpu_power_usage{' + EC + '}','{{entity}}')],
        axis="CPU Power", unit="watt"))

    panels.append(ts(
        "Combined Power (GPU+CPU) per Entity",
        "WHY: Total power envelope per node — capacity planning + billing.\n\n"
        "FORMULA: gpu_power_usage + cpu_power_usage per entity.\n"
        "DGX B200 typical: ~10-12kW. Unexpected spikes = PSU issue.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_power_usage{' + EC + '} + cpu_power_usage{' + EC + '}','{{entity}}')],
        axis="Total Power", unit="watt"))
    y += 6

    panels.append(ts(
        "GPU Enforced Power Limit",
        "WHY: If enforced limit < max TDP, admin or DCGM is power-capping the GPU.\n\n"
        "METRIC: GPU_enforced_power_limit — currently active power cap per GPU.\n"
        "SIGNIFICANCE: Changes during workload = dynamic power management.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('GPU_enforced_power_limit{' + EC + '}','{{entity}}')],
        axis="Watts", unit="watt"))

    panels.append(ts(
        "GPU Power Management Limit",
        "WHY: Configured maximum power limit — set by admin.\n\n"
        "METRIC: gpu_power_management_limit.\n"
        "NOTE: If enforced < management limit, system is actively throttling.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_power_management_limit{' + EC + '}','{{entity}}')],
        axis="Watts", unit="watt"))

    panels.append(ts(
        "Per-GPU Power Draw (All 8)",
        "WHY: Identify which specific GPU is consuming more/less power.\n\n"
        "METRICS: gpu0_power .. gpu7_power.\n"
        "SIGNIFICANCE: Large variance across GPUs on same node = issue.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'gpu{i}_power{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Power", unit="watt"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Cooling & Thermal
    # ════════════════════════════════════════════════════════
    panels.append(row("Cooling & Thermal", y)); y += 1

    panels.append(ts(
        "GPU Die Temperature (All 8)",
        "WHY: Primary thermal indicator — liquid-cooled B200 should stay < 83°C.\n\n"
        "METRICS: gpu0_temperature .. gpu7_temperature.\n"
        "ACTION: > 83°C = throttling starts. > 90°C = CDU cooling issue.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'gpu{i}_temperature{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "Thermal Aggregates (GPU + CPU)",
        "WHY: Fleet-wide aggregated temperature for quick anomaly detection.\n\n"
        "METRICS: total_gpu_temperature (avg across all GPUs on a node) + "
        "total_cpu_temperature (avg across CPUs on a node).\n"
        "SIGNIFICANCE: If multiple nodes show elevated temps simultaneously, "
        "it indicates a facility-level cooling issue (CRAC/CRAH failure, CDU problem).\n"
        "ACTION: Compare with per-GPU temps to confirm.",
        {"h":6,"w":4,"x":8,"y":y},
        [tgt('total_gpu_temperature{' + EC + '}','{{entity}} GPU'),
         tgt('total_cpu_temperature{' + EC + '}','{{entity}} CPU')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "GPU Shutdown Temperature",
        "WHY: Emergency thermal shutdown threshold — last line of defense.\n\n"
        "METRIC: GPU_shutdown_temperature.\n"
        "NOTE: If die temp approaches this, GPU will hard-shutdown to prevent damage.",
        {"h":6,"w":4,"x":12,"y":y},
        [tgt('GPU_shutdown_temperature{' + EC + '}','{{entity}}')],
        axis="Threshold", unit="celsius"))

    panels.append(ts(
        "Alert Level per Entity",
        "WHY: BCM alert level per node — identifies which nodes have active alerts.\n\n"
        "METRIC: alert_level — BCM's internal severity scoring.\n"
        "MEANING: This is a cumulative integer — higher = more/worse alerts.\n"
        "For example, 145 could mean multiple warning+critical alerts summed.\n"
        "ACTION: Sort by highest value to find most problematic nodes. "
        "Check BCM console for specific alert messages.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('alert_level{' + EC + '}','{{entity}}')],
        axis="Alert Level"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Storage / NVMe Health
    # ════════════════════════════════════════════════════════
    panels.append(row("Storage / NVMe Health", y)); y += 1

    panels.append(ts(
        "Disk Free Space",
        "WHY: OS/scratch disk — if full, jobs fail to write checkpoints.\n\n"
        "METRIC: free_space — available filesystem space.\n"
        "ACTION: < 10% free = urgent cleanup needed.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('free_space{' + EC + '}','{{entity}}')],
        axis="Space", unit="decbytes"))

    panels.append(ts(
        "Disk Usage",
        "WHY: Track disk consumption trends.\n\n"
        "METRIC: diskspace — used filesystem space.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('diskspace{' + EC + '}','{{entity}}')],
        axis="Usage"))

    panels.append(ts(
        "NVMe Drive Critical Status",
        "WHY: NVMe SSDs have limited write endurance and can fail.\n\n"
        "METRICS: nvme*_critical — 0 = healthy, > 0 = drive failing.\n"
        "nvme*_spare — remaining spare capacity (100 = full, 0 = exhausted).\n"
        "ACTION: Critical > 0 or Spare < 10 = REPLACE DRIVE.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('nvme3_critical{' + EC + '}','{{entity}} nvme3 crit'),
         tgt('nvme3_spare{' + EC + '}','{{entity}} nvme3 spare'),
         tgt('nvme4_critical{' + EC + '}','{{entity}} nvme4 crit'),
         tgt('nvme4_spare{' + EC + '}','{{entity}} nvme4 spare'),
         tgt('nvme5_critical{' + EC + '}','{{entity}} nvme5 crit')],
        axis="Health"))

    panels.append(ts(
        "NVMe PCIe Errors",
        "WHY: NVMe drives connect via PCIe — errors = bus instability.\n\n"
        "METRICS: nvme*_pci_errors — PCIe error counters.\n"
        "SIGNIFICANCE: Rising = drive or slot degrading. May need reseat.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('nvme2_pci_errors{' + EC + '}','{{entity}} nvme2'),
         tgt('nvme5_pci_errors{' + EC + '}','{{entity}} nvme5'),
         tgt('nvme5_pci_link_errors{' + EC + '}','{{entity}} nvme5 link')],
        axis="Errors"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Network & Connectivity
    # ════════════════════════════════════════════════════════
    panels.append(row("Network & Connectivity", y)); y += 1

    panels.append(stat(
        "FPGA UP",
        "WHY: FPGA accelerators for specialized workloads.\n\n"
        "METRIC: fpga_as_up.",
        {"h":5,"w":4,"x":0,"y":y},
        [tgt('sum(fpga_as_up{' + CL + '}) or vector(0)','UP',instant=True)],
        color_mode="value", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))

    panels.append(stat(
        "FPGA DOWN",
        "WHY: FPGA failure detection.\n\n"
        "METRIC: fpga_as_down.",
        {"h":5,"w":4,"x":4,"y":y},
        [tgt('sum(fpga_as_down{' + CL + '}) or vector(0)','DOWN',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Network Connectivity",
        "WHY: BCM composite network connectivity check.\n\n"
        "METRIC: network_connectivity — 1 = connected, 0 = isolated.",
        {"h":5,"w":4,"x":8,"y":y},
        [tgt('min(network_connectivity{' + EC + '}) or vector(1)','',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_OK,"value":1}]}))

    panels.append(ts(
        "Overall Health Score",
        "WHY: BCM composite health score per node.\n\n"
        "METRIC: overall_health — BCM-calculated health value.\n"
        "SIGNIFICANCE: Track trends — declining = hardware degradation.",
        {"h":5,"w":12,"x":12,"y":y},
        [tgt('overall_health{' + EC + '}','{{entity}}')],
        axis="Health"))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: Memory & CPU
    # ════════════════════════════════════════════════════════
    panels.append(row("Memory & CPU", y)); y += 1

    panels.append(ts(
        "Memory Utilization (%)",
        "WHY: System RAM for DGX host processes, CUDA memory management.\n\n"
        "METRIC: memory_utilization — percentage of RAM used.\n"
        "ACTION: > 90% = risk of OOM kills. Check for memory leaks.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('memory_utilization{' + EC + '}','{{entity}}')],
        axis="Utilization %", unit="percent"))

    panels.append(ts(
        "Memory Used vs Free",
        "WHY: Absolute memory values for capacity planning.\n\n"
        "METRICS: total_memory_used + total_memory_free.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('total_memory_used{' + EC + '}','{{entity}} Used'),
         tgt('total_memory_free{' + EC + '}','{{entity}} Free')],
        axis="Memory", unit="decbytes"))

    panels.append(ts(
        "CPU Utilization (%)",
        "WHY: CPU handles job scheduling, data loading, I/O — critical for throughput.\n\n"
        "METRIC: total_cpu_utilization.\n"
        "NOTE: High CPU with low GPU util = CPU bottleneck.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('total_cpu_utilization{' + EC + '}','{{entity}}')],
        axis="Utilization %", unit="percent"))

    panels.append(ts(
        "Hardware Corrupted Memory",
        "WHY: Physical RAM failure — uncorrectable DRAM bit error.\n\n"
        "METRIC: hardware_corrupted_memory — pages of corrupted memory.\n"
        "ACTION: > 0 = REPLACE DIMM. System memory is unreliable.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('hardware_corrupted_memory{' + EC + '}','{{entity}}')],
        axis="Pages",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Network I/O
    # ════════════════════════════════════════════════════════
    panels.append(row("Network I/O", y)); y += 1

    panels.append(ts(
        "Bytes Recv / Sent",
        "WHY: System-level network throughput for data ingestion and results.\n\n"
        "METRICS: bytes_recv + bytes_sent.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('bytes_recv{' + EC + '}','{{entity}} Recv'),
         tgt('bytes_sent{' + EC + '}','{{entity}} Sent')],
        axis="Bytes/s", unit="Bps"))

    panels.append(ts(
        "Frame Errors & Drops",
        "WHY: NIC-level errors indicate hardware or driver issues.\n\n"
        "METRICS: frame_errors + error_sent + drop_recv.\n"
        "ACTION: Rising errors = check NIC firmware, cable, switch port.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('frame_errors{' + EC + '}','{{entity}} Frames'),
         tgt('error_sent{' + EC + '}','{{entity}} Errors'),
         tgt('drop_recv{' + EC + '}','{{entity}} Drops')],
        axis="Errors"))

    panels.append(ts(
        "NFS Server Activity",
        "WHY: Shared storage I/O — NFS for datasets, checkpoints, logs.\n\n"
        "METRICS: nfs_server_packets_tcp + nfs_server_packets_udp.\n"
        "SIGNIFICANCE: High drops or latency = storage bottleneck.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('nfs_server_packets_tcp{' + EC + '}','{{entity}} TCP'),
         tgt('nfs_server_packets_udp{' + EC + '}','{{entity}} UDP')],
        axis="Packets"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: System Health
    # ════════════════════════════════════════════════════════
    panels.append(row("System Health", y)); y += 1

    panels.append(ts(
        "Swap Usage",
        "WHY: Swap activity = severe memory pressure. Bad for GPU workloads.\n\n"
        "METRICS: swap_used + swap_total.\n"
        "ACTION: swap_used > 0 during GPU job = investigate OOM.",
        {"h":5,"w":8,"x":0,"y":y},
        [tgt('swap_used{' + EC + '}','{{entity}} Used'),
         tgt('swap_total{' + EC + '}','{{entity}} Total')],
        axis="Swap", unit="decbytes"))

    panels.append(ts(
        "System Load (1m)",
        "WHY: Load average vs core count — oversubscription indicator.\n\n"
        "METRIC: load_one — 1-minute load average.\n"
        "RULE: load > cores_total = oversubscribed.",
        {"h":5,"w":8,"x":8,"y":y},
        [tgt('load_one{' + EC + '}','{{entity}}')],
        axis="Load"))

    panels.append(ts(
        "Threads Used",
        "WHY: Active thread count — helps detect runaway processes.\n\n"
        "METRIC: threads_used — total active threads.\n"
        "SIGNIFICANCE: Unusually high = potential process leak.",
        {"h":5,"w":8,"x":16,"y":y},
        [tgt('threads_used{' + EC + '}','{{entity}}')],
        axis="Threads"))
    y += 5

    return wrap_dashboard(
        uid=UIDS["02"],
        title="BMaaS — 02 Infrastructure & Hardware Health",
        description="Power/energy per entity, cooling/thermal, NVMe storage, "
                    "memory/CPU, network I/O, system health.",
        tags=["bmaas","infrastructure","hardware","power","cooling","storage","bcm11"],
        panels=panels,
        templating=standard_templating(),
        links=sub_dashboard_links()
    )

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/02-infrastructure-hardware-health.json"
    d = build_02()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
