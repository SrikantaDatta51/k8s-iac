#!/usr/bin/env python3
"""Dashboard 00 — Executive Fleet Overview V6.
Single-pane-of-glass: SLA → Node Status → GPU → Power → NVLink → Util → Errors → RMA → Score.

V6 CHANGES:
- All UIDs suffixed with -v6
- nodes_* metrics now use EC filter (entity + cluster), not just CL
- GPU health matrix shows ONLY problematic nodes with reasons
- Fleet avg GPU utilization prominent stat
- Dashboard title includes V6
"""
import json, sys
from panel_builders import *

def build_00():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW 1: SLA Targets & Compliance (FIRST)
    # ════════════════════════════════════════════════════════
    panels.append(row("SLA Targets & Compliance", y)); y += 1

    panels.append(text_panel(
        "SLA Definitions & Targets",
        "## SLA Targets (Aspirational)\n\n"
        "| Metric | Target | Breach |\n"
        "|--------|--------|--------|\n"
        "| **Node Uptime** | ≥ 99.5% | < 99% |\n"
        "| **GPU Healthy** | ≥ 99.5% | < 95% |\n"
        "| **NVLink Fabric** | ≥ 99% | < 95% |\n"
        "| **Network Switches** | ≥ 99% | < 95% |\n\n"
        "> **NOTE**: Node uptime 99.5% is the primary contractual SLA.\n\n"
        "## RMA Priority Scoring\n\n"
        "| Signal | Score | Action |\n"
        "|--------|-------|--------|\n"
        "| `gpu_ecc_dbe_agg > 0` | **+100** | Immediate GPU replacement |\n"
        "| `hardware_corrupted_memory > 0` | **+75** | DIMM replacement |\n"
        "| `gpu_row_remap_failure == 1` | **+50** | GPU exchange |\n"
        "| `gpu_uncorrectable_remapped_rows > 0` | **+25** | Schedule GPU swap |\n\n"
        "## Escalation\n\n"
        "- **P0** (DBE): → Eng Lead + Customer (immediate)\n"
        "- **P1** (Row Remap/Thermal): → Hardware Team (4h SLA)\n"
        "- **P2** (SBE trend/Throttle): → Monitoring Review (24h)\n",
        {"h":8,"w":8,"x":0,"y":y}))

    panels.append(ts(
        "Node Availability Trend",
        "WHY: Track availability trend over time against SLA target.\n\n"
        "FORMULA: nodes_up / nodes_total — fraction of fleet online.\n"
        "SLA TARGET: ≥ 99.5%. Red line = breach threshold.\n"
        "SIGNIFICANCE: Dips below 99.5% = SLA breach risk.",
        {"h":8,"w":8,"x":8,"y":y},
        [tgt('sum(nodes_up{' + EC + '}) / clamp_min(sum(nodes_total{' + EC + '}), 1)',
             'Availability')],
        axis="Availability", unit="percentunit",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"custom.thresholdsStyle","value":{"mode":"line"}},
            {"id":"thresholds","value":{"mode":"absolute","steps":[
                {"color":"transparent","value":None},
                {"color":C_FL,"value":0.995}]}}]}]))

    panels.append(ts(
        "NVIDIA License: Licensed vs Used",
        "WHY: Track GPU license utilization — unused licenses = wasted spending.\n\n"
        "METRICS:\n"
        "  • nvidia_licensed_compute_resources — total licensed GPU resources\n"
        "  • nvidia_used_gpu_resources — actually consumed GPU resources\n"
        "SIGNIFICANCE: Gap = room for growth or waste.",
        {"h":8,"w":8,"x":16,"y":y},
        [tgt('nvidia_licensed_compute_resources{' + CL + '}','Licensed'),
         tgt('nvidia_used_gpu_resources{' + CL + '}','Used')],
        axis="GPU Resources"))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW 2: Node Status
    # ════════════════════════════════════════════════════════
    panels.append(row("Node Status", y)); y += 1

    panels.append(stat(
        "Nodes UP",
        "WHY: Nodes actively serving workloads = your available capacity.\n\n"
        "METRIC: nodes_up — BCM nodes in operational UP state.\n"
        "FILTERED: entity=~skt-dgx (DGX GPU nodes only).",
        {"h":5,"w":6,"x":0,"y":y},
        [tgt('sum(nodes_up{' + EC + '})','Nodes UP',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None}]}))

    panels.append(stat(
        "Nodes DOWN",
        "WHY: DOWN nodes = lost revenue + SLA risk. Needs immediate investigation.\n\n"
        "METRIC: nodes_down — BCM nodes in DOWN state.\n"
        "FILTERED: entity=~skt-dgx (DGX GPU nodes only).\n"
        "ACTION: > 0 = investigate hardware, cooling, network connectivity.",
        {"h":5,"w":6,"x":6,"y":y},
        [tgt('sum(nodes_down{' + EC + '}) or vector(0)','Nodes DOWN',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Nodes Closed",
        "WHY: CLOSED = intentionally taken offline by admin/BCM.\n\n"
        "METRIC: nodes_closed — nodes in CLOSED state.\n"
        "FILTERED: entity=~skt-dgx (DGX GPU nodes only).\n"
        "MEANING: Node is reachable + managed but NOT accepting workloads. "
        "Used during maintenance, burn-in, or hardware validation.",
        {"h":5,"w":6,"x":12,"y":y},
        [tgt('sum(nodes_closed{' + EC + '}) or vector(0)','Closed',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":1}]}))

    panels.append(stat(
        "Fleet Size (Total)",
        "WHY: Total nodes in fleet — baseline for capacity calculations.\n\n"
        "METRIC: nodes_total — total DGX nodes managed by BCM.\n"
        "FILTERED: entity=~skt-dgx.\n"
        "CHECK: UP + DOWN + CLOSED should equal TOTAL.",
        {"h":5,"w":6,"x":18,"y":y},
        [tgt('sum(nodes_total{' + EC + '})','Total',instant=True)],
        color_mode="value", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW 3: GPU-Focused Status (DGX Nodes Only)
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU-Focused Status (DGX Nodes)", y)); y += 1

    # Show ONLY problematic nodes WITH REASONS
    panels.append(tbl(
        "🔴 Problematic GPU Nodes — Failure Details",
        "WHY: Instantly see which DGX nodes have GPU issues and WHY.\n\n"
        "Shows nodes where gpu_health_overall > 0 with breakdown of reasons:\n"
        "  • Health Overall — DCGM composite (0=pass, >0=fail)\n"
        "  • Health Mem — HBM memory health\n"
        "  • Health NVLink — NVLink fabric health\n"
        "  • Health Thermal — Thermal status\n"
        "  • Health PCIe — PCIe bus health\n"
        "  • ECC DBE — Uncorrectable errors (>0 = RMA)\n"
        "  • Row Remap Fail — HBM repair exhausted (1 = RMA)\n\n"
        "ACTION: Any node here should NOT receive new workloads.\n"
        "If this table is EMPTY = ALL nodes healthy ✅.",
        {"h":8,"w":14,"x":0,"y":y},
        [tgt('gpu_health_overall{' + EC + '} > 0','', fmt="table"),
         tgt('gpu_health_mem{' + EC + '}','', fmt="table"),
         tgt('gpu_health_nvlink{' + EC + '}','', fmt="table"),
         tgt('gpu_health_thermal{' + EC + '}','', fmt="table"),
         tgt('gpu_health_pcie{' + EC + '}','', fmt="table"),
         tgt('gpu_ecc_dbe_agg{' + EC + '}','', fmt="table"),
         tgt('gpu_row_remap_failure{' + EC + '}','', fmt="table")],
        transforms=[
            {"id":"merge","options":{}},
            {"id":"organize","options":{
                "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
                "renameByName":{
                    "entity":"Node",
                    "Value #A":"Health Overall",
                    "Value #B":"Health Mem",
                    "Value #C":"Health NVLink",
                    "Value #D":"Health Thermal",
                    "Value #E":"Health PCIe",
                    "Value #F":"ECC DBE",
                    "Value #G":"Row Remap Fail"}}}],
        overrides=[
            {"matcher":{"id":"byName","options":"Health Overall"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}}]},
            {"matcher":{"id":"byName","options":"ECC DBE"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}}]},
            {"matcher":{"id":"byName","options":"Row Remap Fail"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}}]}],
        sort=[{"displayName":"Health Overall","desc":True}]))

    # Fleet Avg GPU Utilization (prominent stat)
    panels.append(stat(
        "Fleet Avg GPU Utilization",
        "WHY: Fleet-wide GPU util = PRIMARY revenue/efficiency KPI.\n\n"
        "FORMULA: avg(gpu_utilization) across all DGX nodes.\n"
        "TARGET: > 70% = healthy. < 40% = wasted GPU capacity = revenue loss.",
        {"h":4,"w":5,"x":14,"y":y},
        [tgt('avg(gpu_utilization{' + EC + '})','Avg Util',instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":40},
            {"color":C_OK,"value":70}]}))

    panels.append(stat(
        "GPU Switches UP / DOWN",
        "WHY: NVSwitch ASICs on DGX baseboard — enable all-to-all GPU communication at 900GB/s.\n\n"
        "METRIC: gp_us_up / gp_us_down.\n"
        "ACTION: gp_us_down > 0 → affected node GPUs cannot communicate.",
        {"h":4,"w":5,"x":19,"y":y},
        [tgt('sum(gp_us_up{' + EC + '}) or vector(0)','UP',instant=True),
         tgt('sum(gp_us_down{' + EC + '}) or vector(0)','DOWN',instant=True)],
        color_mode="value", text_mode="value_and_name",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))

    # GPU count table
    panels.append(tbl(
        "GPU Count per Entity",
        "WHY: B200 DGX should have 8 GPUs per node.\n\n"
        "METRIC: gpu_count — GPUs detected by DCGM per entity.\n"
        "< 8 = GPU not detected = hardware failure.\n"
        "ACTION: Check GPU seating, PCIe, DCGM logs.",
        {"h":4,"w":5,"x":14,"y":y+4},
        [tgt('gpu_count{' + EC + '}','', fmt="table")],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"entity":"Node","Value":"GPUs"}}}],
        overrides=[
            {"matcher":{"id":"byName","options":"GPUs"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_FL,"value":None},{"color":C_WR,"value":7},
                    {"color":C_OK,"value":8}]}}]}],
        sort=[{"displayName":"GPUs","desc":False}]))

    panels.append(stat(
        "Managed Switches",
        "WHY: Managed network switches connect DGX nodes to data center fabric.\n\n"
        "METRIC: managed_switches_up / managed_switches_down.\n"
        "DOWN switch = node(s) isolated from network → jobs fail.",
        {"h":4,"w":5,"x":19,"y":y+4},
        [tgt('sum(managed_switches_up{' + EC + '}) or vector(0)','UP',instant=True),
         tgt('sum(managed_switches_down{' + EC + '}) or vector(0)','DOWN',instant=True)],
        color_mode="value", text_mode="value_and_name",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW 4: Power — GPU + CPU per Entity
    # ════════════════════════════════════════════════════════
    panels.append(row("Power Consumption (per Entity)", y)); y += 1

    panels.append(ts(
        "GPU Power per Entity",
        "WHY: Track GPU power draw per DGX node. B200 = 8 × 1000W = 8kW max.\n\n"
        "METRIC: gpu_power_usage — per-entity aggregate GPU power.\n"
        "SIGNIFICANCE: Sustained at TDP = healthy. Below during load = throttling.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_power_usage{' + EC + '}','{{entity}}')],
        axis="GPU Power", unit="watt"))

    panels.append(ts(
        "CPU Power per Entity",
        "WHY: CPU handles job orchestration, data loading, I/O.\n\n"
        "METRIC: cpu_power_usage — per-entity CPU power.\n"
        "Typically 300-500W for dual-socket Grace CPUs.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('cpu_power_usage{' + EC + '}','{{entity}}')],
        axis="CPU Power", unit="watt"))

    panels.append(ts(
        "Combined Power (GPU+CPU) per Entity",
        "WHY: Total power envelope per node — capacity planning and billing.\n\n"
        "FORMULA: gpu_power_usage + cpu_power_usage by entity.\n"
        "Each line = one DGX node's total power draw.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_power_usage{' + EC + '} + cpu_power_usage{' + EC + '}','{{entity}}')],
        axis="Total Power", unit="watt"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW 5: NVLink & Fabric Health
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink & Fabric Health", y)); y += 1

    panels.append(ts(
        "GPU NVLink Health (per Entity)",
        "WHY: NVLink health per entity — 0 = all links healthy, > 0 = degraded.\n\n"
        "METRIC: gpu_health_nvlink — DCGM NVLink health check.\n"
        "ACTION: > 0 → check NVLink cables, NVSwitch on affected node.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_health_nvlink{' + EC + '}','{{entity}}')],
        axis="Health (0=OK)"))

    panels.append(ts(
        "GPU NVLink CRC Data Errors",
        "WHY: CRC errors = data integrity failures on NVLink interconnect.\n\n"
        "METRIC: gpu_nvlink_crc_data_errors — cumulative CRC error count.\n"
        "ACTION: Rising = cable/connector degrading. Reseat or replace.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_nvlink_crc_data_errors{' + EC + '}','{{entity}}')],
        axis="CRC Errors"))

    panels.append(ts(
        "GPU NVLink Total Bandwidth",
        "WHY: Verify NVLink fabric delivering expected throughput.\n\n"
        "METRIC: gpu_nvlink_total_bandwidth — aggregate NVLink BW per entity.\n"
        "EXPECTED: B200 NVLink ~900GB/s per GPU pair.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_nvlink_total_bandwidth{' + EC + '}','{{entity}}')],
        axis="Bandwidth"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW 6: Fleet GPU Utilization
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet GPU Utilization", y)); y += 1

    panels.append(ts(
        "GPU Utilization (per Entity)",
        "WHY: Per-node GPU utilization — which nodes are idle vs loaded.\n\n"
        "METRIC: gpu_utilization per entity.\n"
        "TARGET: > 70% = healthy. < 40% = wasted GPU capacity.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('gpu_utilization{' + EC + '}','{{entity}}')],
        axis="Utilization %", unit="percent"))

    panels.append(ts(
        "Fleet Avg GPU Utilization (Trend)",
        "WHY: Fleet-wide GPU utilization trend.\n\n"
        "FORMULA: avg(gpu_utilization) across all DGX nodes.\n"
        "SIGNIFICANCE: Trending down = workload migration or scheduling problem.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt('avg(gpu_utilization{' + EC + '})','Fleet Avg')],
        axis="Utilization %", unit="percent"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW 7: XID / DCGM Errors & Alerts
    # ════════════════════════════════════════════════════════
    panels.append(row("XID / DCGM Errors & Alerts", y)); y += 1

    panels.append(ts(
        "Fleet GPU ECC Error Trend",
        "WHY: Rising ECC errors across fleet = aging/degrading HBM memory.\n\n"
        "METRIC: gpu_ecc_sbe_agg (correctable) vs gpu_ecc_dbe_agg (UNCORRECTABLE).\n"
        "DBE > 0 = IMMEDIATE GPU REPLACEMENT.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('sum(gpu_ecc_sbe_agg{' + EC + '})','SBE (Correctable)'),
         tgt('sum(gpu_ecc_dbe_agg{' + EC + '})','DBE (Uncorrectable)')],
        axis="Errors",
        overrides=[
            {"matcher":{"id":"byName","options":"DBE (Uncorrectable)"},"properties":[
                {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"SBE (Correctable)"},"properties":[
                {"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]}]))

    panels.append(ts(
        "GPU Health Failures Over Time",
        "WHY: Count of nodes with GPU health issues trending.\n\n"
        "FORMULA: count(gpu_health_overall > 0).\n"
        "Rising trend = fleet aging, environmental issue, or batch defect.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('count(gpu_health_overall{' + EC + '} > 0) or vector(0)','Failures')],
        axis="Failing Nodes"))

    panels.append(ts(
        "Alert Level per Entity",
        "WHY: BCM alert level per entity — which nodes have active alerts.\n\n"
        "METRIC: alert_level — BCM internal severity scoring.\n"
        "Higher = more/worse alerts. Sort by highest to find worst nodes.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('alert_level{' + EC + '}','{{entity}}')],
        axis="Alert Level"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW 8: RMA Priority
    # ════════════════════════════════════════════════════════
    panels.append(row("Nodes Requiring Attention", y)); y += 1

    panels.append(tbl(
        "GPU RMA Priority Table",
        "WHY: Proactively identify nodes needing hardware replacement.\n\n"
        "SCORING:\n"
        "  • gpu_ecc_dbe_agg > 0 = +100 (uncorrectable → IMMEDIATE)\n"
        "  • hardware_corrupted_memory > 0 = +75 (bad DIMM)\n"
        "  • gpu_row_remap_failure == 1 = +50 (HBM repair exhausted)\n"
        "  • gpu_uncorrectable_remapped_rows > 0 = +25 (schedule swap)\n\n"
        "Score ≥ 100 = emergency RMA. Score ≥ 50 = escalate.",
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

    panels.append(tbl(
        "Node State Distribution",
        "WHY: Snapshot of all nodes and their current state.\n\n"
        "METRICS: nodes_up, nodes_down, nodes_closed, nodes_total.\n"
        "FILTERED: entity=~skt-dgx (DGX GPU nodes only).",
        {"h":8,"w":12,"x":12,"y":y},
        [tgt('nodes_up{' + EC + '}','', fmt="table"),
         tgt('nodes_down{' + EC + '}','', fmt="table"),
         tgt('nodes_closed{' + EC + '}','', fmt="table")],
        transforms=[
            {"id":"merge","options":{}},
            {"id":"organize","options":{
                "excludeByName":{"Time":True,"__name__":True,"job":True},
                "renameByName":{"entity":"Node"}}}],
        sort=[{"displayName":"Node","desc":False}]))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW 9: Composite Fleet Health Score (LAST)
    # ════════════════════════════════════════════════════════
    panels.append(row("Composite Fleet Health Score", y)); y += 1

    panels.append(stat(
        "Node Availability",
        "FORMULA: nodes_up / nodes_total × 100.\nSLA TARGET: ≥ 99.5%.",
        {"h":6,"w":4,"x":0,"y":y},
        [tgt('(sum(nodes_up{' + EC + '}) / clamp_min(sum(nodes_total{' + EC + '}), 1)) * 100',
             'Availability', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":95},
            {"color":C_OK,"value":99}]}))

    panels.append(stat(
        "GPU Health Score",
        "FORMULA: count(gpu_health_overall == 0) / count(gpu_health_overall) × 100.\nSLA TARGET: ≥ 99.5%.",
        {"h":6,"w":4,"x":4,"y":y},
        [tgt('(count(gpu_health_overall{' + EC + '} == 0) / clamp_min(count(gpu_health_overall{' + EC + '}), 1)) * 100',
             'GPU Health', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":95},
            {"color":C_OK,"value":99}]}))

    panels.append(stat(
        "NVLink Health",
        "FORMULA: count(gpu_health_nvlink == 0) / count(gpu_health_nvlink) × 100.",
        {"h":6,"w":4,"x":8,"y":y},
        [tgt('(count(gpu_health_nvlink{' + EC + '} == 0) / clamp_min(count(gpu_health_nvlink{' + EC + '}), 1)) * 100',
             'NVLink', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":90},
            {"color":C_OK,"value":99}]}))

    panels.append(stat(
        "Fleet GPU Utilization",
        "FORMULA: avg(gpu_utilization) across all DGX nodes.",
        {"h":6,"w":4,"x":12,"y":y},
        [tgt('avg(gpu_utilization{' + EC + '})', 'Avg Util', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":40},
            {"color":C_OK,"value":70}]}))

    panels.append(stat(
        "ECC Clean Rate",
        "FORMULA: count(gpu_ecc_dbe_agg == 0) / count(gpu_ecc_dbe_agg) × 100.",
        {"h":6,"w":4,"x":16,"y":y},
        [tgt('(count(gpu_ecc_dbe_agg{' + EC + '} == 0) / clamp_min(count(gpu_ecc_dbe_agg{' + EC + '}), 1)) * 100',
             'ECC Clean', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":95},
            {"color":C_OK,"value":100}]}))

    panels.append(stat(
        "🏥 Composite Score",
        "Weighted: Node Avail (30%) + GPU Health (25%) + NVLink (15%) + Util (15%) + ECC (15%).\n"
        "Green ≥ 95% = fleet operational. Yellow 90-95% = degraded. Red < 90% = critical.",
        {"h":6,"w":4,"x":20,"y":y},
        [tgt(
            '('
            '(sum(nodes_up{' + EC + '}) / clamp_min(sum(nodes_total{' + EC + '}), 1)) * 0.30 + '
            '(count(gpu_health_overall{' + EC + '} == 0) / clamp_min(count(gpu_health_overall{' + EC + '}), 1)) * 0.25 + '
            '(count(gpu_health_nvlink{' + EC + '} == 0) / clamp_min(count(gpu_health_nvlink{' + EC + '}), 1)) * 0.15 + '
            '(avg(gpu_utilization{' + EC + '}) / 100) * 0.15 + '
            '(count(gpu_ecc_dbe_agg{' + EC + '} == 0) / clamp_min(count(gpu_ecc_dbe_agg{' + EC + '}), 1)) * 0.15'
            ') * 100',
            'Fleet Score', instant=True
        )],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":90},
            {"color":C_OK,"value":95}]}))
    y += 6

    return wrap_dashboard(
        uid=UIDS["00"],
        title="BMaaS — 00 Executive Fleet Overview V6",
        description="SLA targets, node status, GPU-focused panels, power, NVLink, utilization, "
                    "ECC errors, RMA table, composite health score.",
        tags=["bmaas","fleet","executive","overview","sla","gpu","b200","bcm11","v6"],
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
