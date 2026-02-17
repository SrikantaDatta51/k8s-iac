#!/usr/bin/env python3
"""Dashboard 03 — Network Fabric Monitoring.
NVLink (gpu_nvlink_* metrics), InfiniBand per-port, managed switches, system network I/O.

v4 OVERHAUL:
- All nv_link_switches_* REMOVED (showing 0) — use gpu_nvlink_* instead
- Fixed IB query brace syntax
- No gauges
- Reverse sorted legends
"""
import json, sys
from panel_builders import *

IB_PORTS = [4, 7, 8, 9, 10, 13, 14, 15]

def build_03():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: NVLink Health Overview (gpu_nvlink_* metrics)
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink Health Overview", y)); y += 1

    panels.append(ts(
        "GPU NVLink Health per Entity",
        "WHY: NVLink health per DGX node — 0 = all links healthy, > 0 = degraded.\n\n"
        "METRIC: gpu_health_nvlink — DCGM NVLink health check.\n"
        "SIGNIFICANCE: Unhealthy NVLink = reduced multi-GPU bandwidth → training slowdown.\n"
        "ACTION: > 0 → check NVLink cables, NVSwitch on affected node.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_health_nvlink{' + EC + '}','{{entity}}')],
        axis="Health (0=OK)"))

    panels.append(stat(
        "Managed Switches UP",
        "WHY: External ToR/spine switches connect DGX nodes to data center network.\n\n"
        "METRIC: managed_switches_up.\n"
        "SIGNIFICANCE: DOWN = node(s) isolated from network.",
        {"h":6,"w":4,"x":8,"y":y},
        [tgt('sum(managed_switches_up{' + CL + '}) or vector(0)','UP',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None}]}))

    panels.append(stat(
        "Managed Switches DOWN",
        "WHY: Network switch failure = node isolation.\n\n"
        "METRIC: managed_switches_down.\n"
        "ACTION: > 0 = check switch, cables, config.",
        {"h":6,"w":4,"x":12,"y":y},
        [tgt('sum(managed_switches_down{' + CL + '}) or vector(0)','DOWN',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Managed Switches Closed",
        "WHY: CLOSED = intentionally taken offline for maintenance.\n\n"
        "METRIC: managed_switches_closed.\n"
        "NOTE: Normal during infrastructure changes.",
        {"h":6,"w":4,"x":16,"y":y},
        [tgt('sum(managed_switches_closed{' + CL + '}) or vector(0)','Closed',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":1}]}))

    panels.append(stat(
        "Managed Switches Total",
        "WHY: Baseline count for network fabric.\n\n"
        "METRIC: managed_switches_total.",
        {"h":6,"w":4,"x":20,"y":y},
        [tgt('sum(managed_switches_total{' + CL + '}) or vector(0)','Total',instant=True)],
        color_mode="value", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NVLink Errors & Bandwidth (gpu_nvlink_* metrics)
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU NVLink Errors & Bandwidth", y)); y += 1

    panels.append(ts(
        "GPU NVLink CRC Data Errors",
        "WHY: CRC errors = data integrity failures on NVLink interconnect.\n\n"
        "METRIC: gpu_nvlink_crc_data_errors — cumulative CRC error count.\n"
        "ACTION: Rising = cable or connector degrading. Reseat or replace.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_nvlink_crc_data_errors{' + EC + '}','{{entity}}')],
        axis="CRC Errors",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "GPU NVLink CRC Flit Errors",
        "WHY: Flit = smallest NVLink transfer unit. Flit CRC = link-level noise.\n\n"
        "METRIC: gpu_nvlink_crc_flit_errors.\n"
        "SIGNIFICANCE: Lower severity than data errors but indicates link quality.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_nvlink_crc_flit_errors{' + EC + '}','{{entity}}')],
        axis="Flit Errors"))

    panels.append(ts(
        "GPU NVLink Total Bandwidth",
        "WHY: Verify NVLink fabric is delivering expected throughput.\n\n"
        "METRIC: gpu_nvlink_total_bandwidth — aggregate NVLink BW.\n"
        "SIGNIFICANCE: B200 NVLink expected ~900GB/s per GPU pair.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_nvlink_total_bandwidth{' + EC + '}','{{entity}}')],
        axis="Bandwidth"))
    y += 6

    panels.append(ts(
        "GPU Fabric Status",
        "WHY: Shows if each GPU is part of the NVLink domain.\n\n"
        "METRIC: GPU_fabric_status — 0 = included, > 0 = excluded.\n"
        "ACTION: Excluded GPU loses multi-GPU capability.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('GPU_fabric_status{' + EC + '}','{{entity}}')],
        axis="Status"))

    panels.append(ts(
        "GPU NVLink Health Trend",
        "WHY: Track NVLink health over time — detect degradation patterns.\n\n"
        "METRIC: gpu_health_nvlink.\n"
        "SIGNIFICANCE: Periodic spikes = intermittent cable issue.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt('gpu_health_nvlink{' + EC + '}','{{entity}}')],
        axis="Health (0=OK)"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: InfiniBand Port Health (MLX5)
    # ════════════════════════════════════════════════════════
    panels.append(row("InfiniBand Port Health (MLX5)", y)); y += 1

    panels.append(ts(
        "IB Link State (All Ports)",
        "WHY: InfiniBand link state shows port connectivity.\n\n"
        "METRIC: infiniband_mlx5_*_link_state — 5=LinkUp, 1=Down.\n"
        "SIGNIFICANCE: All ports should be 5 (LinkUp) for full IB bandwidth.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'infiniband_mlx5_{p}_link_state{{{EC}}}', f'{{{{entity}}}} mlx5_{p}')
         for p in IB_PORTS],
        axis="Link State"))

    panels.append(ts(
        "IB Link Downed Count",
        "WHY: Each link-down event = network disruption for running jobs.\n\n"
        "METRIC: infiniband_mlx5_*_link_downed — cumulative flap counter.\n"
        "ACTION: Rising = cable/HCA issue. Reseat or replace.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'infiniband_mlx5_{p}_link_downed{{{EC}}}', f'{{{{entity}}}} mlx5_{p}')
         for p in IB_PORTS],
        axis="Link Downed"))
    y += 6

    panels.append(ts(
        "IB Port Rate",
        "WHY: Verify negotiated link speed matches expected (400Gbps ConnectX-7).\n\n"
        "METRIC: infiniband_mlx5_*_rate.\n"
        "ACTION: Lower-than-expected = cable quality issue or port config.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'infiniband_mlx5_{p}_rate{{{EC}}}', f'{{{{entity}}}} mlx5_{p}')
         for p in IB_PORTS],
        axis="Rate (Gbps)"))

    panels.append(ts(
        "IB Physical State",
        "WHY: Physical layer state — 5=LinkUp, 2=Polling (trying to connect).\n\n"
        "METRIC: infiniband_mlx5_*_phys_state.\n"
        "SIGNIFICANCE: Stuck in Polling = cable/port mismatch.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'infiniband_mlx5_{p}_phys_state{{{EC}}}', f'{{{{entity}}}} mlx5_{p}')
         for p in IB_PORTS],
        axis="PhysState"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: System Network I/O
    # ════════════════════════════════════════════════════════
    panels.append(row("System Network I/O", y)); y += 1

    panels.append(ts(
        "System Bytes Recv / Sent",
        "WHY: System-level network throughput for data plane.\n\n"
        "METRICS: bytes_recv + bytes_sent.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('bytes_recv{' + EC + '}','{{entity}} Recv'),
         tgt('bytes_sent{' + EC + '}','{{entity}} Sent')],
        axis="Bytes/s", unit="Bps"))

    panels.append(ts(
        "IP Traffic",
        "WHY: IP-level traffic volume — overall network usage.\n\n"
        "METRICS: ip_in_receives + ip_out_requests.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('ip_in_receives{' + EC + '}','{{entity}} In'),
         tgt('ip_out_requests{' + EC + '}','{{entity}} Out')],
        axis="Packets/s"))

    panels.append(ts(
        "TCP Retransmissions",
        "WHY: TCP retransmits indicate network congestion or packet loss.\n\n"
        "METRIC: tcp_retrans_segs.\n"
        "ACTION: Sustained high = check switch buffering, cable quality.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('tcp_retrans_segs{' + EC + '}','{{entity}}')],
        axis="Retransmits"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NIC Interface Details
    # ════════════════════════════════════════════════════════
    panels.append(row("NIC Interface Details", y)); y += 1

    panels.append(ts(
        "NIC Speed",
        "WHY: Verify link speed negotiation.\n\n"
        "METRIC: sys_class_net_speed — per-interface link speed (Mbps).\n"
        "EXPECTED: 400000 for 400GbE, 100000 for 100GbE.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('sys_class_net_speed{' + EC + '}','{{entity}} {{device}}')],
        axis="Speed (Mbps)"))

    panels.append(ts(
        "NIC MTU",
        "WHY: Jumbo frames (MTU 9000) required for IB and high-perf networking.\n\n"
        "METRIC: sys_class_net_mtu.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('sys_class_net_mtu{' + EC + '}','{{entity}} {{device}}')],
        axis="MTU"))

    panels.append(ts(
        "NIC Carrier Changes",
        "WHY: Each carrier change = link flap = disruption.\n\n"
        "METRIC: sys_class_net_carrier_changes — per-NIC flap counter.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('sys_class_net_carrier_changes{' + EC + '}','{{entity}} {{device}}')],
        axis="Changes"))

    panels.append(ts(
        "Frame Errors",
        "WHY: NIC hardware errors — bad cables, driver issues.\n\n"
        "METRIC: frame_errors.\n"
        "ACTION: > 0 = investigate NIC, cable, firmware.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('frame_errors{' + EC + '}','{{entity}}')],
        axis="Errors"))
    y += 6

    return wrap_dashboard(
        uid=UIDS["03"],
        title="BMaaS — 03 Network Fabric Monitoring V6",
        description="GPU NVLink health (gpu_nvlink_* metrics), managed switches, "
                    "InfiniBand per-port MLX5, system network I/O, NIC details.",
        tags=["bmaas","network","nvlink","infiniband","fabric","switches","bcm11","v6"],
        panels=panels,
        templating=standard_templating(),
        links=sub_dashboard_links()
    )

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/03-network-fabric-monitoring.json"
    d = build_03()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
