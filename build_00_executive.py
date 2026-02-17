#!/usr/bin/env python3
"""Dashboard 00 — Executive Fleet Overview.
Single-pane-of-glass for fleet operations.
Answer in 5 seconds: 'Is my fleet healthy? Any SLA risk?'
"""
import json, sys
from panel_builders import *

def build_00():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: Fleet Health at a Glance
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet Health at a Glance", y)); y += 1

    # Fleet Health Score gauge
    panels.append(gauge(
        "Fleet Health Score",
        "Overall fleet health 0–100%. Composite of node availability, GPU health, and network fabric status.",
        {"h":6,"w":5,"x":0,"y":y},
        [tgt(
            'avg(bcm_device_is_up{' + CL + '}) * 0.5 + '
            'avg(clamp_max(clamp_min((gpu_health_overall{' + CL + '} == 0) * 1, 0), 1)) * 0.3 + '
            'avg(clamp_max(clamp_min((nmxm_domain_health_count{' + CL + ', state="healthy"} / clamp_min(nmxm_domain_health_count{' + CL + '}, 1)), 0), 1)) * 0.2',
            'Fleet Health', instant=True
        )],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.9},
            {"color":C_OK,"value":0.95}]}))

    # Node State Distribution
    panels.append(piechart(
        "Node State Distribution",
        "How many nodes are UP / DOWN / CLOSED / BURNING? Any non-UP node reduces capacity.",
        {"h":6,"w":5,"x":5,"y":y},
        [tgt('count by (state) (bcm_node_state{' + CL + '})','{{state}}',instant=True)]))

    # SLA Uptime Gauge
    panels.append(gauge(
        "SLA Uptime",
        "Node availability over the SLA measurement window. Target: ≥ 99.9%.",
        {"h":6,"w":4,"x":10,"y":y},
        [tgt(
            'avg_over_time(avg(bcm_device_is_up{' + CL + '})[30d:5m])',
            'Uptime', instant=True
        )],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.995},
            {"color":C_OK,"value":0.999}]}))

    # Active Alerts — Critical / Warning / Info
    for i, (sev, label, color) in enumerate([
        ("critical", "Critical Alerts", C_FL),
        ("warning", "Warning Alerts", C_WR),
        ("info", "Info Alerts", C_TL),
    ]):
        panels.append(stat(label, f"Active {sev} alerts across the fleet.",
            {"h":6,"w":3,"x":14+i*3+i,"y":y},
            [tgt(f'count(ALERTS{{alertstate="firing", severity="{sev}", cluster=~"$cluster"}}) or vector(0)',
                 label, instant=True)],
            color_mode="value",
            thresholds={"mode":"absolute","steps":[{"color":color,"value":None}]}))

    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: GPU Fleet & NVLink Status
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Fleet & NVLink Status", y)); y += 1

    # GPU Fleet — Healthy / Degraded / Unhealthy
    for i, (state, label, color) in enumerate([
        ("healthy", "GPUs Healthy", C_OK),
        ("degraded", "GPUs Degraded", C_WR),
        ("unhealthy", "GPUs Unhealthy", C_FL),
    ]):
        panels.append(stat(label, f"Number of GPUs in {state} state per NMX telemetry.",
            {"h":5,"w":4,"x":i*4,"y":y},
            [tgt(f'sum(nmxm_gpu_health_count{{' + CL + f', state="{state}"}}) or vector(0)',
                 '', instant=True)],
            color_mode="background",
            thresholds={"mode":"absolute","steps":[{"color":color,"value":None}]}))

    # NVLink Domain Health
    panels.append(stat(
        "NVLink Domains Healthy",
        "NVLink domains in healthy state. Unhealthy domains prevent multi-node jobs.",
        {"h":5,"w":4,"x":12,"y":y},
        [tgt('sum(nmxm_domain_health_count{' + CL + ', state="healthy"}) or vector(0)',
             '', instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None}]}))

    # NVLink Switches UP / DOWN
    panels.append(stat(
        "NVLink Switches UP",
        "Active NVLink switches. DOWN switches reduce fabric bandwidth.",
        {"h":5,"w":4,"x":16,"y":y},
        [tgt('sum(NVLinkSwitchesUp{' + CL + '}) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None}]}))
    panels.append(stat(
        "NVLink Switches DOWN",
        "NVLink switches in DOWN state. Any > 0 = degraded fabric.",
        {"h":5,"w":4,"x":20,"y":y},
        [tgt('sum(NVLinkSwitchesDown{' + CL + '}) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: Power, Cooling & Safety
    # ════════════════════════════════════════════════════════
    panels.append(row("Power, Cooling & Safety", y)); y += 1

    panels.append(stat(
        "PSU Health",
        "Healthy PSU ratio. < 1.0 = degraded power redundancy.",
        {"h":5,"w":4,"x":0,"y":y},
        [tgt('avg(TotalPowerShelfHealthyPSU{' + CL + '}) or vector(1)','',instant=True)],
        color_mode="background", unit="percentunit",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.8},
            {"color":C_OK,"value":1}]}))

    panels.append(stat(
        "CDU Avg Return Temp",
        "Average liquid cooling return temperature across CDUs.",
        {"h":5,"w":4,"x":4,"y":y},
        [tgt('avg(CDULiquidReturnTemperature{' + CL + '})','',instant=True)],
        color_mode="background", unit="celsius", decimals=1,
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":40},
            {"color":C_FL,"value":50}]}))

    panels.append(stat(
        "CDU Avg Flow Rate",
        "Average liquid flow rate. Low flow = reduced cooling capacity.",
        {"h":5,"w":4,"x":8,"y":y},
        [tgt('avg(CDULiquidFlow{' + CL + '})','',instant=True)],
        color_mode="background", unit="short", decimals=1,
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":5},
            {"color":C_OK,"value":10}]}))

    panels.append(stat(
        "⚠️ Leak Detection",
        "Number of devices with active leaks. ANY > 0 = EMERGENCY.",
        {"h":5,"w":4,"x":12,"y":y},
        [tgt('sum(DevicesWithLeaks{' + CL + '}) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Total Power Draw",
        "Total power consumption across all circuits.",
        {"h":5,"w":4,"x":16,"y":y},
        [tgt('sum(TotalCircuitPower{' + CL + '}) or vector(0)','',instant=True)],
        color_mode="value", unit="watt", decimals=0,
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))

    panels.append(stat(
        "Job Success Rate (24h)",
        "Percentage of jobs completed successfully in last 24 hours.",
        {"h":5,"w":4,"x":20,"y":y},
        [tgt(
            'sum(bcm_job_completed{' + CL + '}) / clamp_min(sum(bcm_job_completed{' + CL + '}) + sum(bcm_job_failed{' + CL + '}), 1)',
            '', instant=True
        )],
        color_mode="background", unit="percentunit", decimals=1,
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.9},
            {"color":C_OK,"value":0.95}]}))

    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: Nodes Requiring Attention
    # ════════════════════════════════════════════════════════
    panels.append(row("Nodes Requiring Attention", y)); y += 1

    panels.append(tbl(
        "Nodes Requiring Action",
        "Nodes with active issues: ECC DBE, row remap failure, critical XID, health check failures, thermal violations.",
        {"h":8,"w":12,"x":0,"y":y},
        [tgt(
            '('
            '(gpu_ecc_dbe_agg{' + CL + '} > 0) * 100 + '
            '(gpu_row_remap_failure{' + CL + '} == 1) * 50 + '
            '(gpu_thermal_violation{' + CL + '} > 0) * 10'
            ')',
            '', fmt="table"
        )],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"instance":"Node","gpu":"GPU","Value":"Severity Score"}}}],
        overrides=[
            {"matcher":{"id":"byName","options":"Severity Score"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_WR,"value":None},{"color":C_FL,"value":50}]}}]}],
        sort=[{"displayName":"Severity Score","desc":True}]))

    panels.append(tbl(
        "Hardware Replacement Queue",
        "Nodes flagged for RMA based on ECC DBE > 0, row remap failure, or NVSwitch fatal errors.",
        {"h":8,"w":12,"x":12,"y":y},
        [tgt(
            '(gpu_ecc_dbe_agg{' + CL + '} > 0) or '
            '(gpu_row_remap_failure{' + CL + '} == 1) or '
            '(gpu_health_nvswitch_fatal{' + CL + '} != 0)',
            '', fmt="table"
        )],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"instance":"Node","gpu":"GPU","Value":"Error Signal"}}}],
        sort=[{"displayName":"Error Signal","desc":True}]))

    y += 8

    # ════════════════════════════════════════════════════════
    # ROW: Fleet Trends
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet Trends", y)); y += 1

    panels.append(ts(
        "Node Availability Over Time",
        "Fraction of nodes reporting UP over time.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('avg(bcm_device_is_up{' + CL + '})','Availability')],
        axis="Availability", unit="percentunit"))

    panels.append(ts(
        "GPU ECC Error Trend (Fleet)",
        "Fleet-wide SBE vs DBE trends. Rising SBE = early degradation.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt('sum(gpu_ecc_sbe_agg{' + CL + '})','SBE Total'),
         tgt('sum(gpu_ecc_dbe_agg{' + CL + '})','DBE Total')],
        axis="Errors",
        overrides=[
            {"matcher":{"id":"byName","options":"DBE Total"},"properties":[
                {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"SBE Total"},"properties":[
                {"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]}]))
    y += 6

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["00"],
        title="BMaaS — 00 Executive Fleet Overview",
        description="Single-pane-of-glass for BMaaS fleet health. GPU status, NVLink domains, "
                    "power/cooling, SLA uptime, and nodes requiring attention.",
        tags=["bmaas","fleet","executive","overview","sla","gpu","b200","bcm11"],
        panels=panels,
        templating=standard_templating(),
        time_from="now-6h",
        links=sub_dashboard_links()
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/00-executive-fleet-overview.json"
    d = build_00()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
    for p in d["panels"]:
        print(f"  [{p.get('type',''):14s}] {p.get('title','')}")
