#!/usr/bin/env python3
"""Dashboard 06 — SLA Compliance & Alerting.
SLA tracking and breach prevention.
Answer: 'Are we meeting SLA? What triggered a breach?'
"""
import json, sys
from panel_builders import *

def build_06():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: SLA Uptime Metrics
    # ════════════════════════════════════════════════════════
    panels.append(row("SLA Uptime Metrics", y)); y += 1

    panels.append(gauge(
        "Node Availability (SLA)",
        "(total_minutes - downtime_minutes) / total_minutes × 100. Target: ≥ 99.9%.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt(
            'avg_over_time(avg(bcm_device_is_up{' + CL + '})[30d:5m])',
            'Node Availability', instant=True)],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.995},
            {"color":C_OK,"value":0.999}]}))

    panels.append(gauge(
        "GPU Availability",
        "(total_gpu_min - degraded_gpu_min) / total_gpu_min × 100. Target: ≥ 99.5%.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt(
            'avg_over_time(avg(clamp_max(clamp_min('
            '(nmxm_gpu_health_count{' + CL + ', state="healthy"} / '
            'clamp_min(nmxm_gpu_health_count{' + CL + '}, 1)), 0), 1))[30d:5m])',
            'GPU Availability', instant=True)],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.99},
            {"color":C_OK,"value":0.995}]}))

    panels.append(gauge(
        "Network Availability",
        "NVLink + InfiniBand uptime. Target: ≥ 99.9%.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt(
            'avg_over_time(avg(clamp_max(clamp_min('
            'NVLinkSwitchesUp{' + CL + '} / '
            'clamp_min(NVLinkSwitchesTotal{' + CL + '}, 1), 0), 1))[30d:5m])',
            'Network Availability', instant=True)],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.995},
            {"color":C_OK,"value":0.999}]}))

    panels.append(gauge(
        "Job Success Rate",
        "completed_jobs / (completed + failed) × 100. Target: ≥ 95%.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt(
            'sum(bcm_job_completed{' + CL + '}) / '
            'clamp_min(sum(bcm_job_completed{' + CL + '}) + sum(bcm_job_failed{' + CL + '}), 1)',
            'Job Success', instant=True)],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.9},
            {"color":C_OK,"value":0.95}]}))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: SLA Breach Risk
    # ════════════════════════════════════════════════════════
    panels.append(row("SLA Breach Risk", y)); y += 1

    panels.append(ts(
        "Node Availability Over SLA Window",
        "Rolling node availability over the SLA measurement period.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(
            'avg_over_time(avg(bcm_device_is_up{' + CL + '})[7d:5m])',
            'Availability (7d)')],
        axis="Availability", unit="percentunit",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"custom.thresholdsStyle","value":{"mode":"line"}},
            {"id":"thresholds","value":{"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_FL,"value":0.999}]}}]}]))

    panels.append(ts(
        "GPU Availability Over SLA Window",
        "Rolling GPU health ratio.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(
            'avg_over_time(avg(clamp_max(clamp_min('
            'nmxm_gpu_health_count{' + CL + ', state="healthy"} / '
            'clamp_min(nmxm_gpu_health_count{' + CL + '}, 1), 0), 1))[7d:5m])',
            'GPU Avail (7d)')],
        axis="Availability", unit="percentunit"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Mean Time to Recovery
    # ════════════════════════════════════════════════════════
    panels.append(row("Mean Time to Recovery (MTTR)", y)); y += 1

    panels.append(stat(
        "Average MTTR",
        "Average duration from node DOWN to node UP. SLA target: < 4 hours.",
        {"h":5,"w":8,"x":0,"y":y},
        [tgt(
            'avg(bcm_node_recovery_duration_seconds{' + CL + '}) or vector(0)',
            '', instant=True)],
        color_mode="background", unit="s",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":7200},
            {"color":C_FL,"value":14400}]}))

    panels.append(stat(
        "Max MTTR (Worst Node)",
        "Longest recovery time in the current window.",
        {"h":5,"w":8,"x":8,"y":y},
        [tgt(
            'max(bcm_node_recovery_duration_seconds{' + CL + '}) or vector(0)',
            '', instant=True)],
        color_mode="background", unit="s",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":7200},
            {"color":C_FL,"value":14400}]}))

    panels.append(stat(
        "Nodes Currently DOWN",
        "Number of nodes in DOWN state right now.",
        {"h":5,"w":8,"x":16,"y":y},
        [tgt('count(bcm_node_state{' + CL + ', state="DOWN"}) or vector(0)',
             '',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: Hardware Replacement Triggers
    # ════════════════════════════════════════════════════════
    panels.append(row("Hardware Replacement Triggers", y)); y += 1

    panels.append(tbl(
        "Hardware Replacement Decision Matrix",
        "Decision matrix: ECC DBE > 0, row remap failure, critical XID, NVSwitch fatal, "
        "PSU failure, CDU anomaly. Priority: Immediate → Schedule → Monitor.",
        {"h":8,"w":24,"x":0,"y":y},
        [tgt(
            '('
            '(gpu_ecc_dbe_agg{' + CL + '} > 0) * 1000 + '
            '(gpu_row_remap_failure{' + CL + '} == 1) * 500 + '
            '(gpu_uncorrectable_remapped_rows{' + CL + '} > 0) * 200 + '
            '(gpu_health_nvswitch_fatal{' + CL + '} != 0) * 800 + '
            '(gpu_thermal_violation{' + CL + '} > 0) * 50 + '
            '(gpu_correctable_remapped_rows{' + CL + '} > 256) * 100'
            ')',
            '', fmt="table")],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"instance":"Node","gpu":"GPU","Value":"Priority Score"}}}],
        overrides=[
            {"matcher":{"id":"byName","options":"Priority Score"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_WR,"value":None},{"color":C_OR,"value":200},
                    {"color":C_FL,"value":500}]}}]}],
        sort=[{"displayName":"Priority Score","desc":True}]))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW: Alert Distribution & History
    # ════════════════════════════════════════════════════════
    panels.append(row("Alert Distribution & History", y)); y += 1

    panels.append(piechart(
        "Active Alert Distribution",
        "Distribution of currently firing alerts by severity.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('count by (severity) (ALERTS{alertstate="firing", cluster=~"$cluster"})','{{severity}}',instant=True)]))

    panels.append(ts(
        "Alert History Timeline",
        "Count of firing alerts over time by severity. Spikes = incident correlation.",
        {"h":6,"w":16,"x":8,"y":y},
        [tgt('count by (severity) (ALERTS{alertstate="firing", cluster=~"$cluster"})','{{severity}}')],
        axis="Active Alerts",stacking="normal"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Maintenance & Capacity
    # ════════════════════════════════════════════════════════
    panels.append(row("Maintenance & Capacity Impact", y)); y += 1

    panels.append(ts(
        "Nodes Unavailable Over Time",
        "Nodes in DOWN, CLOSED, BURNING states — capacity impact tracking.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('count(bcm_node_state{' + CL + ', state="DOWN"}) or vector(0)','DOWN'),
         tgt('count(bcm_node_state{' + CL + ', state="CLOSED"}) or vector(0)','CLOSED'),
         tgt('count(bcm_node_state{' + CL + ', state=~".*burning.*"}) or vector(0)','BURNING')],
        axis="Nodes",stacking="normal",
        overrides=[
            {"matcher":{"id":"byName","options":"DOWN"},"properties":[
                {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"CLOSED"},"properties":[
                {"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"BURNING"},"properties":[
                {"id":"color","value":{"fixedColor":C_OR,"mode":"fixed"}}]}]))

    panels.append(ts(
        "Capacity Impact (%)",
        "Unavailable nodes as percentage of total fleet.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(
            '1 - (count(bcm_node_state{' + CL + ', state="UP"}) / '
            'count(bcm_node_state{' + CL + '}))',
            'Unavailable %')],
        axis="Impact", unit="percentunit",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}},
            {"id":"custom.fillOpacity","value":30}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Incident Response SLA
    # ════════════════════════════════════════════════════════
    panels.append(row("Incident Response SLA", y)); y += 1

    panels.append(text_panel(
        "SLA Definitions Reference",
        "| Metric | Definition | Target |\n"
        "|--------|-----------|--------|\n"
        "| **Node Availability** | (total - downtime) / total × 100 | ≥ 99.9% |\n"
        "| **GPU Availability** | (total_gpu - degraded_gpu) / total_gpu × 100 | ≥ 99.5% |\n"
        "| **MTTR** | Avg duration DOWN → UP | < 4 hours |\n"
        "| **Planned Maintenance** | Scheduled windows (excluded from SLA) | < 8 hrs/month |\n"
        "| **Job Success Rate** | completed / (completed + failed) × 100 | ≥ 95% |\n"
        "| **Network Availability** | NVLink + InfiniBand uptime | ≥ 99.9% |\n",
        {"h":6,"w":12,"x":0,"y":y}))

    panels.append(text_panel(
        "Escalation Contacts",
        "### Priority Levels\n\n"
        "| Priority | Response Time | Examples |\n"
        "|----------|--------------|----------|\n"
        "| **P0 Critical** | 15 minutes | Node down, leak detected, NVSwitch fatal |\n"
        "| **P1 High** | 1 hour | GPU DBE, PSU failure, NVLink degraded |\n"
        "| **P2 Medium** | 4 hours | Job failure rate > 5%, thermal throttling |\n"
        "| **P3 Low** | Next business day | SBE trend, HW profile drift |\n\n"
        "### Contacts\n"
        "- **NVIDIA Support**: BCM/NVLink/GPU RMA\n"
        "- **Facility Team**: CDU, power, leak response\n"
        "- **Platform Team**: Workload, scheduling, capacity\n",
        {"h":6,"w":12,"x":12,"y":y}))
    y += 6

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["06"],
        title="BMaaS — 06 SLA Compliance & Alerting",
        description="SLA tracking: node/GPU/network availability, MTTR, job success rate, "
                    "hardware replacement triggers, alert distribution, capacity impact, incident response.",
        tags=["bmaas","sla","compliance","alerting","mttr","availability","bcm11"],
        panels=panels,
        templating=standard_templating(),
        links=sub_dashboard_links()
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/06-sla-compliance-alerting.json"
    d = build_06()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
    for p in d["panels"]:
        print(f"  [{p.get('type',''):14s}] {p.get('title','')}")
