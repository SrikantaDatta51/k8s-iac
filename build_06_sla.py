#!/usr/bin/env python3
"""Dashboard 06 — SLA Compliance & Alerting.
SLA tracking, uptime, MTTR, replacement triggers, capacity impact.
"""
import json, sys
from panel_builders import *

def build_06():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: SLA Uptime Gauges
    # ════════════════════════════════════════════════════════
    panels.append(row("SLA Uptime Gauges", y)); y += 1

    panels.append(gauge(
        "Node Uptime SLA",
        "WHY: Primary SLA metric — node availability over measurement window.\n\n"
        "FORMULA: avg_over_time(devices_up / devices_total)[30d].\n"
        "TARGET: ≥ 99.9%. BREACH: < 99.5% → customer notification required.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt(
            'avg_over_time((sum(devices_up{' + CL + '}) / sum(devices_total{' + CL + '}))[30d:5m])',
            '', instant=True
        )],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.995},
            {"color":C_OK,"value":0.999}]}))

    panels.append(gauge(
        "GPU Subsystem SLA",
        "WHY: GPU health directly impacts customer workloads.\n\n"
        "FORMULA: Fraction of nodes with gpu_health_overall == 0.\n"
        "TARGET: ≥ 99%. BREACH: < 95%.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt(
            'count(gpu_health_overall{' + CL + '} == 0) / count(gpu_health_overall{' + CL + '})',
            '', instant=True
        )],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.95},
            {"color":C_OK,"value":0.99}]}))

    panels.append(gauge(
        "NVLink Fabric SLA",
        "WHY: NVLink fabric availability affects multi-GPU job performance.\n\n"
        "FORMULA: nv_link_switches_up / nv_link_switches_total.\n"
        "TARGET: ≥ 99%.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt(
            'sum(nv_link_switches_up{' + CL + '}) / clamp_min(sum(nv_link_switches_total{' + CL + '}), 1)',
            '', instant=True
        )],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.95},
            {"color":C_OK,"value":0.99}]}))

    panels.append(gauge(
        "Network Switch SLA",
        "WHY: Managed switch availability = network connectivity for all nodes.\n\n"
        "FORMULA: managed_switches_up / managed_switches_total.\n"
        "TARGET: ≥ 99%.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt(
            'sum(managed_switches_up{' + CL + '}) / clamp_min(sum(managed_switches_total{' + CL + '}), 1)',
            '', instant=True
        )],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.95},
            {"color":C_OK,"value":0.99}]}))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Breach Risk Trends
    # ════════════════════════════════════════════════════════
    panels.append(row("Breach Risk Trends", y)); y += 1

    panels.append(ts(
        "Node Availability Trend (24h Rolling)",
        "WHY: Track availability trend against SLA line.\n\n"
        "FORMULA: devices_up / devices_total — 24h rolling average.\n"
        "RED LINE: 99.9% SLA threshold.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(
            'avg_over_time((sum(devices_up{' + CL + '}) / sum(devices_total{' + CL + '}))[24h:5m])',
            'Availability 24h'
        )],
        axis="Availability", unit="percentunit",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"custom.thresholdsStyle","value":{"mode":"line"}},
            {"id":"thresholds","value":{"mode":"absolute","steps":[
                {"color":"transparent","value":None},
                {"color":C_FL,"value":0.999}]}}]}]))

    panels.append(ts(
        "Nodes DOWN Over Time",
        "WHY: Sustained DOWN nodes = active SLA breach.\n\n"
        "METRIC: devices_down.\n"
        "ACTION: Persistent > 0 = escalate to hardware team.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('sum(devices_down{' + CL + '}) or vector(0)','Nodes DOWN')],
        axis="Count",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "GPU Health Failures Over Time",
        "WHY: Count of nodes with GPU health issues over time.\n\n"
        "FORMULA: count(gpu_health_overall > 0).\n"
        "SIGNIFICANCE: Rising trend = fleet aging or environmental issue.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('count(gpu_health_overall{' + CL + '} > 0) or vector(0)','Failures')],
        axis="Count"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Downtime & State Distribution
    # ════════════════════════════════════════════════════════
    panels.append(row("Downtime & State Distribution", y)); y += 1

    panels.append(ts(
        "Device State Distribution (Stacked)",
        "WHY: Visualize fleet state transitions over time.\n\n"
        "METRICS: devices_up + devices_down + devices_closed.\n"
        "SIGNIFICANCE: Shows maintenance windows, outages, recovery.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('sum(devices_up{' + CL + '})','UP'),
         tgt('sum(devices_down{' + CL + '}) or vector(0)','DOWN'),
         tgt('sum(devices_closed{' + CL + '}) or vector(0)','CLOSED')],
        axis="Nodes", stacking="normal"))

    panels.append(ts(
        "Alert Level Trend",
        "WHY: BCM alert level over time — spikes = incidents.\n\n"
        "METRIC: alert_level — 0=none, 1=warning, ≥2=critical.\n"
        "CORRELATION: Compare with downtime periods.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('max(alert_level{' + CL + '}) or vector(0)','Alert Level')],
        axis="Level"))

    panels.append(stat(
        "⚠️ Leak Detection",
        "WHY: Coolant leaks = P0 safety emergency.\n\n"
        "METRIC: devices_with_leaks.\n"
        "ACTION: > 0 = ALL-STOP, power off, physical inspection.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('sum(devices_with_leaks{' + CL + '}) or vector(0)','Leaks',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: RMA Decision Matrix
    # ════════════════════════════════════════════════════════
    panels.append(row("Hardware Replacement (RMA) Decision Matrix", y)); y += 1

    panels.append(tbl(
        "GPU RMA Priority Table",
        "WHY: Proactive identification of nodes needing hardware replacement.\n\n"
        "SCORING:\n"
        "  • gpu_ecc_dbe_agg > 0 = +100 (uncorrectable memory → immediate)\n"
        "  • hardware_corrupted_memory > 0 = +75 (bad DIMM)\n"
        "  • gpu_row_remap_failure == 1 = +50 (HBM repair exhausted)\n"
        "  • gpu_uncorrectable_remapped_rows > 0 = +25 (schedule swap)\n\n"
        "Score ≥ 50 = escalate. Score ≥ 100 = emergency RMA.",
        {"h":8,"w":12,"x":0,"y":y},
        [tgt(
            '(gpu_ecc_dbe_agg{' + EC + '} > 0) * 100 + '
            '(hardware_corrupted_memory{' + EC + '} > 0) * 75 + '
            '(gpu_row_remap_failure{' + EC + '} == 1) * 50 + '
            '(gpu_uncorrectable_remapped_rows{' + EC + '} > 0) * 25',
            '', fmt="table"
        )],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"entity":"Node","Value":"RMA Score"}}}],
        overrides=[
            {"matcher":{"id":"byName","options":"RMA Score"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_OK,"value":None},{"color":C_WR,"value":25},
                    {"color":C_FL,"value":50}]}}]}],
        sort=[{"displayName":"RMA Score","desc":True}]))

    panels.append(text_panel(
        "SLA Definitions & Escalation",
        "## SLA Targets\n\n"
        "| Metric | Target | Breach |\n"
        "|--------|--------|---------|\n"
        "| Node Uptime | ≥ 99.9% | < 99.5% |\n"
        "| GPU Health | ≥ 99% healthy | < 95% |\n"
        "| NVLink Fabric | ≥ 99% up | < 95% |\n"
        "| Network Switches | ≥ 99% up | < 95% |\n\n"
        "## RMA Priority Scoring\n\n"
        "| Signal | Score | Action |\n"
        "|--------|-------|---------|\n"
        "| `gpu_ecc_dbe_agg > 0` | **+100** | Immediate GPU replacement |\n"
        "| `hardware_corrupted_memory > 0` | **+75** | DIMM replacement |\n"
        "| `gpu_row_remap_failure == 1` | **+50** | GPU exchange |\n"
        "| `gpu_uncorrectable_remapped_rows > 0` | **+25** | Schedule GPU swap |\n\n"
        "## Escalation Contacts\n\n"
        "- **P0** (DBE/Leak): → Eng Lead + Customer (immediate)\n"
        "- **P1** (Row Remap/Thermal): → Hardware Team (4h SLA)\n"
        "- **P2** (SBE trend/Throttle): → Monitoring Review (24h)\n",
        {"h":8,"w":12,"x":12,"y":y}))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW: Capacity Impact
    # ════════════════════════════════════════════════════════
    panels.append(row("Capacity Impact", y)); y += 1

    panels.append(ts(
        "Active vs Total Devices",
        "WHY: Lost capacity = lost revenue. Track capacity utilization.\n\n"
        "FORMULA: devices_up vs devices_total.\n"
        "SIGNIFICANCE: Gap = maintenance + failures.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('sum(devices_up{' + CL + '})','UP'),
         tgt('sum(devices_total{' + CL + '})','Total')],
        axis="Nodes"))

    panels.append(ts(
        "GPU Capacity (Licensed vs Used)",
        "WHY: Track NVIDIA GPU license utilization.\n\n"
        "METRICS: nvidia_licensed_compute_resources + nvidia_used_gpu_resources.\n"
        "SIGNIFICANCE: Unused licenses = wasted spending.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('nvidia_licensed_compute_resources{' + CL + '}','Licensed'),
         tgt('nvidia_used_gpu_resources{' + CL + '}','Used')],
        axis="GPU Resources"))

    panels.append(ts(
        "Fleet GPU Utilization",
        "WHY: Low utilization + DOWN nodes = compounding revenue loss.\n\n"
        "METRIC: avg(total_gpu_utilization) — fleet-wide compute usage.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('avg(total_gpu_utilization{' + CL + '})','Fleet Avg')],
        axis="Utilization %", unit="percent"))
    y += 6

    return wrap_dashboard(
        uid=UIDS["06"],
        title="BMaaS — 06 SLA Compliance & Alerting",
        description="SLA gauges (node/GPU/NVLink/network), breach trends, state distribution, "
                    "RMA decision matrix, capacity impact, definitions & escalation.",
        tags=["bmaas","sla","compliance","alerting","rma","uptime","bcm11"],
        panels=panels,
        templating=standard_templating(),
        time_from="now-30d",
        links=sub_dashboard_links()
    )

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/06-sla-compliance-alerting.json"
    d = build_06()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
