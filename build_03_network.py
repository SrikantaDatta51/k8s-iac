#!/usr/bin/env python3
"""Dashboard 03 — Network Fabric Monitoring.
NVLink + InfiniBand fabric health.
Answer: 'Can multi-node jobs run reliably?'
"""
import json, sys
from panel_builders import *

def build_03():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: NVLink Fabric Overview
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink Fabric Overview", y)); y += 1

    for i,(metric,label,color) in enumerate([
        ("NVLinkSwitchesUp","NVLink Switches UP",C_OK),
        ("NVLinkSwitchesDown","NVLink Switches DOWN",C_FL),
        ("NVLinkSwitchesClosed","NVLink Switches CLOSED",C_WR),
        ("NVLinkSwitchesTotal","NVLink Switches Total",C_BL),
    ]):
        thresh = {"mode":"absolute","steps":[{"color":color,"value":None}]}
        if metric == "NVLinkSwitchesDown":
            thresh = {"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}
        panels.append(stat(label, f"{metric} from ClusterTotal data producer.",
            {"h":5,"w":6,"x":i*6,"y":y},
            [tgt(f'sum({metric}{{' + CL + '}}) or vector(0)','',instant=True)],
            color_mode="background", thresholds=thresh))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: NVLink Port Health
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink Port Health", y)); y += 1

    panels.append(ts(
        "NVLink Port Link State",
        "RF_NVLink_Resource_LinkState — per-port link status. Active = healthy.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('RF_NVLink_Resource_LinkState{' + N + '}','{{instance}} Port{{port}}')],
        axis="Link State"))

    panels.append(ts(
        "NVLink Port Bit Error Rate",
        "RF_NVLink_Port_Nvidia_BitErrorRate — rising = NVLink degradation.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('RF_NVLink_Port_Nvidia_BitErrorRate{' + N + '}','{{instance}} Port{{port}}')],
        axis="BER",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "NVLink Port Link Downed",
        "RF_NVLink_Port_Nvidia_LinkDowned — > 0 = link failures occurred.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('RF_NVLink_Port_Nvidia_LinkDowned{' + N + '}','{{instance}} Port{{port}}')],
        axis="Link Downed"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NVLink Bandwidth
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink Bandwidth", y)); y += 1

    panels.append(ts(
        "NVLink Port RX Bandwidth",
        "RF_NVLink_Port_RX — receive throughput per NVLink port.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('RF_NVLink_Port_RX{' + N + '}','{{instance}} Port{{port}}')],
        axis="RX Bandwidth", unit="Bps"))

    panels.append(ts(
        "NVLink Port TX Bandwidth",
        "RF_NVLink_Port_TX — transmit throughput per NVLink port.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('RF_NVLink_Port_TX{' + N + '}','{{instance}} Port{{port}}')],
        axis="TX Bandwidth", unit="Bps"))

    panels.append(ts(
        "NVLink Speed: Current vs Max",
        "RF_NVLink_Resource_CurrentSpeed vs RF_NVLink_Resource_MaxSpeed.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('RF_NVLink_Resource_CurrentSpeed{' + N + '}','{{instance}} Current'),
         tgt('RF_NVLink_Resource_MaxSpeed{' + N + '}','{{instance}} Max')],
        axis="Speed"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NMX Telemetry
    # ════════════════════════════════════════════════════════
    panels.append(row("NMX Telemetry (NVLink Monitoring)", y)); y += 1

    # NMX Compute Health
    for i,(state,label,color) in enumerate([
        ("healthy","NMX Compute Healthy",C_OK),
        ("degraded","NMX Compute Degraded",C_WR),
        ("unhealthy","NMX Compute Unhealthy",C_FL),
        ("unknown","NMX Compute Unknown",C_UK),
    ]):
        panels.append(stat(label, f"nmxm_compute_health_count — nodes in {state} state.",
            {"h":4,"w":6,"x":i*6,"y":y},
            [tgt(f'sum(nmxm_compute_health_count{{' + CL + f', state="{state}"}}) or vector(0)',
                 '',instant=True)],
            color_mode="background",
            thresholds={"mode":"absolute","steps":[{"color":color,"value":None}]}))
    y += 4

    # NMX GPU Health
    for i,(state,label,color) in enumerate([
        ("healthy","NMX GPU Healthy",C_OK),
        ("degraded","NMX GPU Degraded",C_WR),
        ("degraded_bw","NMX GPU Degraded BW",C_OR),
        ("nonvlink","NMX Non-NVLink GPUs",C_UK),
    ]):
        panels.append(stat(label, f"nmxm_gpu_health_count — GPUs in {state} state.",
            {"h":4,"w":6,"x":i*6,"y":y},
            [tgt(f'sum(nmxm_gpu_health_count{{' + CL + f', state="{state}"}}) or vector(0)',
                 '',instant=True)],
            color_mode="background",
            thresholds={"mode":"absolute","steps":[{"color":color,"value":None}]}))
    y += 4

    # NMX Switch & Domain Health
    panels.append(ts(
        "NMX Switch Health",
        "nmxm_switch_health_count — healthy / missing_nvlink / unhealthy / unknown.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'nmxm_switch_health_count{{' + CL + '}}','{{state}}')],
        axis="Count"))

    panels.append(ts(
        "NMX Domain Health",
        "nmxm_domain_health_count — domain health aggregation. Unhealthy = multi-node at risk.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'nmxm_domain_health_count{{' + CL + '}}','{{state}}')],
        axis="Count"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: InfiniBand Fabric
    # ════════════════════════════════════════════════════════
    panels.append(row("InfiniBand Fabric", y)); y += 1

    panels.append(ts(
        "IB Data Received",
        "ib_rcv_data — InfiniBand receive throughput per port.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('rate(ib_rcv_data{' + N + '}[5m])','{{instance}} {{port}}')],
        axis="RX Rate", unit="Bps"))

    panels.append(ts(
        "IB Data Transmitted",
        "ib_xmit_data — InfiniBand transmit throughput per port.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('rate(ib_xmit_data{' + N + '}[5m])','{{instance}} {{port}}')],
        axis="TX Rate", unit="Bps"))

    panels.append(ts(
        "IB Errors",
        "ib_rcv_err / ib_xmit_err — InfiniBand error counters.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('rate(ib_rcv_err{' + N + '}[5m])','{{instance}} RcvErr'),
         tgt('rate(ib_xmit_err{' + N + '}[5m])','{{instance}} XmitErr')],
        axis="Errors/s"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: GPU Fabric Status
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Fabric Status", y)); y += 1

    panels.append(heatmap(
        "GPU Fabric Status per GPU",
        "gpu_fabric_status — shows which GPUs are included/excluded from NVLink domains.",
        {"h":8,"w":24,"x":0,"y":y},
        [tgt('gpu_fabric_status{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')]))
    y += 8

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["03"],
        title="BMaaS — 03 Network Fabric Monitoring",
        description="NVLink switches, port health, bandwidth, NMX compute/GPU/switch/domain health, "
                    "InfiniBand throughput and errors, GPU fabric status.",
        tags=["bmaas","network","nvlink","infiniband","nmx","fabric","bcm11"],
        panels=panels,
        templating=standard_templating(extra_vars=[gpu_var()]),
        links=sub_dashboard_links()
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/03-network-fabric-monitoring.json"
    d = build_03()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
    for p in d["panels"]:
        print(f"  [{p.get('type',''):14s}] {p.get('title','')}")
