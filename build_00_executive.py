#!/usr/bin/env python3
"""Dashboard 00 — Executive Fleet Overview.
Single-pane-of-glass showing fleet-wide health, GPU status, power, SLA targets.

v4 OVERHAUL:
- Multi-component health score (5 sub-scores instead of single gauge)
- All devices_* → nodes_* (devices metrics not working)
- No gauges — stat + bargauge only
- Leak detection REMOVED (not available)
- gpu_nvlink_* instead of nv_link_switches_* (those showed 0)
- SLA + license panels merged from deleted Dashboard 06
- gpu_power_usage + cpu_power_usage per entity (aggregated)
- XID/DCGM error summary
- Per-entity GPU power (entity names like DGX0102)
"""
import json, sys
from panel_builders import *

def build_00():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: Fleet Health Score — Multi-Component Breakdown
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet Health Score — Multi-Component", y)); y += 1

    panels.append(stat(
        "🏥 Composite Fleet Score",
        "WHY: Single number to assess fleet readiness at a glance.\n\n"
        "FORMULA: Weighted average of 5 sub-scores:\n"
        "  • Node Availability (30%): nodes_up / nodes_total\n"
        "  • GPU Health (25%): nodes with gpu_health_overall == 0 / total\n"
        "  • NVLink Health (15%): nodes with gpu_health_nvlink == 0 / total\n"
        "  • GPU Utilization (15%): avg(gpu_utilization) / 100\n"
        "  • ECC Clean Rate (15%): nodes with no DBE / total\n\n"
        "Green ≥ 95% = fleet operational. Yellow 90-95% = degraded. Red < 90% = critical.\n"
        "ACTION: Score < 90% → escalate to hardware team immediately.",
        {"h":6,"w":4,"x":0,"y":y},
        [tgt(
            '('
            '(sum(nodes_up{' + CL + '}) / clamp_min(sum(nodes_total{' + CL + '}), 1)) * 0.30 + '
            '(count(gpu_health_overall{' + CL + '} == 0) / clamp_min(count(gpu_health_overall{' + CL + '}), 1)) * 0.25 + '
            '(count(gpu_health_nvlink{' + CL + '} == 0) / clamp_min(count(gpu_health_nvlink{' + CL + '}), 1)) * 0.15 + '
            '(avg(gpu_utilization{' + CL + '}) / 100) * 0.15 + '
            '(count(gpu_ecc_dbe_agg{' + CL + '} == 0) / clamp_min(count(gpu_ecc_dbe_agg{' + CL + '}), 1)) * 0.15'
            ') * 100',
            'Fleet Score', instant=True
        )],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":90},
            {"color":C_OK,"value":95}]}))

    # Sub-scores as individual stat panels
    panels.append(stat(
        "Node Availability",
        "WHY: What % of nodes are UP and serving workloads.\n"
        "FORMULA: nodes_up / nodes_total × 100.\n"
        "SLA TARGET: ≥ 99.5%.\n"
        "ACTION: < 99% → immediate investigation.",
        {"h":6,"w":4,"x":4,"y":y},
        [tgt('(sum(nodes_up{' + CL + '}) / clamp_min(sum(nodes_total{' + CL + '}), 1)) * 100',
             'Availability', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":95},
            {"color":C_OK,"value":99}]}))

    panels.append(stat(
        "GPU Health Score",
        "WHY: % of nodes with ALL GPUs healthy (DCGM overall check = 0).\n"
        "FORMULA: count(gpu_health_overall == 0) / count(gpu_health_overall) × 100.\n"
        "SLA TARGET: ≥ 99.5%.\n"
        "ACTION: < 95% → multiple nodes have GPU issues.",
        {"h":6,"w":4,"x":8,"y":y},
        [tgt('(count(gpu_health_overall{' + CL + '} == 0) / clamp_min(count(gpu_health_overall{' + CL + '}), 1)) * 100',
             'GPU Health', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":95},
            {"color":C_OK,"value":99}]}))

    panels.append(stat(
        "NVLink Health Score",
        "WHY: % of nodes with healthy NVLink (gpu_health_nvlink == 0).\n"
        "NVLink enables 900GB/s GPU-to-GPU communication — critical for multi-GPU.\n"
        "FORMULA: count(gpu_health_nvlink == 0) / count(gpu_health_nvlink) × 100.\n"
        "ACTION: < 95% → NVLink cables or NVSwitch degradation.",
        {"h":6,"w":4,"x":12,"y":y},
        [tgt('(count(gpu_health_nvlink{' + CL + '} == 0) / clamp_min(count(gpu_health_nvlink{' + CL + '}), 1)) * 100',
             'NVLink', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":90},
            {"color":C_OK,"value":99}]}))

    panels.append(stat(
        "Fleet GPU Utilization",
        "WHY: Revenue indicator — low util = wasted GPU capacity = lost revenue.\n"
        "FORMULA: avg(gpu_utilization) across all nodes.\n"
        "TARGET: > 70% healthy. < 40% = investigate scheduling.",
        {"h":6,"w":4,"x":16,"y":y},
        [tgt('avg(gpu_utilization{' + CL + '})', 'Avg Util', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":40},
            {"color":C_OK,"value":70}]}))

    panels.append(stat(
        "ECC Clean Rate",
        "WHY: % of nodes with zero uncorrectable GPU memory errors (DBE).\n"
        "FORMULA: count(gpu_ecc_dbe_agg == 0) / count(gpu_ecc_dbe_agg) × 100.\n"
        "ACTION: < 100% → some nodes have uncorrectable errors → GPU replacement.",
        {"h":6,"w":4,"x":20,"y":y},
        [tgt('(count(gpu_ecc_dbe_agg{' + CL + '} == 0) / clamp_min(count(gpu_ecc_dbe_agg{' + CL + '}), 1)) * 100',
             'ECC Clean', instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":95},
            {"color":C_OK,"value":100}]}))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Node Status
    # ════════════════════════════════════════════════════════
    panels.append(row("Node Status", y)); y += 1

    panels.append(stat(
        "Nodes UP",
        "WHY: Nodes actively serving workloads = your available capacity.\n\n"
        "METRIC: nodes_up — BCM nodes in operational UP state.\n"
        "SIGNIFICANCE: This is the count of nodes that can accept jobs.",
        {"h":5,"w":6,"x":0,"y":y},
        [tgt('sum(nodes_up{' + CL + '})','Nodes UP',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None}]}))

    panels.append(stat(
        "Nodes DOWN",
        "WHY: DOWN nodes = lost revenue + SLA risk. Needs immediate investigation.\n\n"
        "METRIC: nodes_down — BCM nodes in DOWN state (not operational).\n"
        "ACTION: > 0 = investigate hardware, cooling, network connectivity.",
        {"h":5,"w":6,"x":6,"y":y},
        [tgt('sum(nodes_down{' + CL + '}) or vector(0)','Nodes DOWN',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Nodes Closed",
        "WHY: CLOSED = intentionally taken offline by admin/BCM.\n\n"
        "METRIC: nodes_closed — nodes in CLOSED state.\n"
        "MEANING: 'Closed' in BCM means the node is reachable and managed but NOT "
        "accepting workloads. Typically used during maintenance, burn-in testing, or "
        "hardware validation. The node is between UP and DOWN — it's healthy enough to "
        "be managed but intentionally excluded from the scheduling pool.\n"
        "NOTE: High count during burn-in cycles is normal. Sustained outside burn-in = investigate.",
        {"h":5,"w":6,"x":12,"y":y},
        [tgt('sum(nodes_closed{' + CL + '}) or vector(0)','Closed',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":1}]}))

    panels.append(stat(
        "Fleet Size (Total)",
        "WHY: Total nodes in fleet — baseline for capacity calculations.\n\n"
        "METRIC: nodes_total — total nodes managed by BCM.\n"
        "CHECK: UP + DOWN + CLOSED should equal TOTAL.",
        {"h":5,"w":6,"x":18,"y":y},
        [tgt('sum(nodes_total{' + CL + '})','Total',instant=True)],
        color_mode="value", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: GPU-Focused Status (DGX Nodes Only)
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU-Focused Status (DGX Nodes)", y)); y += 1

    panels.append(bargauge(
        "GPU Count per Entity",
        "WHY: Validate hardware config — B200 DGX should have 8 GPUs per node.\n\n"
        "METRIC: gpu_count — number of GPUs detected by DCGM per entity.\n"
        "SIGNIFICANCE: < 8 = GPU not detected = hardware failure on that node.\n"
        "ACTION: Any entity showing < 8 → check GPU seating, PCIe, DCGM logs.",
        {"h":8,"w":8,"x":0,"y":y},
        [tgt('gpu_count{' + EC + '}','{{entity}}',instant=True)],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":7},
            {"color":C_OK,"value":8}]}))

    panels.append(heatmap(
        "GPU Health Matrix (per Node)",
        "WHY: Instantly see which DGX nodes have GPU health issues.\n\n"
        "METRIC: gpu_health_overall — DCGM aggregate health check per entity.\n"
        "0 = ALL PASS (green), > 0 = FAIL (red). Each row = one DGX node.\n"
        "SIGNIFICANCE: Failed nodes should NOT receive new workloads.",
        {"h":8,"w":8,"x":8,"y":y},
        [tgt('gpu_health_overall{' + EC + '}','{{entity}}')]))

    panels.append(stat(
        "GPU Switches UP / DOWN",
        "WHY: GPU switches (gp_us) are the NVSwitch ASICs on the DGX baseboard.\n\n"
        "WHAT ARE THEY: Each DGX B200 has 4 NVSwitch chips that form the internal "
        "GPU-to-GPU NVLink mesh. They enable all-to-all GPU communication at 900GB/s. "
        "Without functional NVSwitches, GPUs cannot do multi-GPU collective operations "
        "(AllReduce, AllGather) which are essential for distributed training.\n\n"
        "METRIC: gp_us_up / gp_us_down — GPU switches in UP vs DOWN state.\n"
        "ACTION: gp_us_down > 0 → affected node's GPUs cannot communicate properly. "
        "Check NVSwitch, may need baseboard replacement.",
        {"h":4,"w":8,"x":16,"y":y},
        [tgt('sum(gp_us_up{' + CL + '}) or vector(0)','UP',instant=True),
         tgt('sum(gp_us_down{' + CL + '}) or vector(0)','DOWN',instant=True)],
        color_mode="value", text_mode="value_and_name",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))

    panels.append(stat(
        "Managed Switches",
        "WHY: Managed network switches connect DGX nodes to data center network fabric.\n\n"
        "METRIC: managed_switches_up / managed_switches_down.\n"
        "SIGNIFICANCE: DOWN switch = node(s) isolated from network → jobs fail.",
        {"h":4,"w":8,"x":16,"y":y+4},
        [tgt('sum(managed_switches_up{' + CL + '}) or vector(0)','UP',instant=True),
         tgt('sum(managed_switches_down{' + CL + '}) or vector(0)','DOWN',instant=True)],
        color_mode="value", text_mode="value_and_name",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW: Power — GPU + CPU per Entity
    # ════════════════════════════════════════════════════════
    panels.append(row("Power Consumption (per Entity)", y)); y += 1

    panels.append(ts(
        "GPU Power per Entity",
        "WHY: Track GPU power draw per DGX node. B200 = 8 × 1000W = 8kW max.\n\n"
        "METRIC: gpu_power_usage — per-entity aggregate GPU power.\n"
        "NOTE: Each entity name (e.g., skt-dgx0102) is shown individually.\n"
        "SIGNIFICANCE: Sustained at TDP = healthy. Well below during load = throttling.",
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
        "WHY: Total power envelope per node — for capacity planning and billing.\n\n"
        "FORMULA: gpu_power_usage + cpu_power_usage by entity.\n"
        "SIGNIFICANCE: Each bar = one DGX node's total power draw.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_power_usage{' + EC + '} + cpu_power_usage{' + EC + '}','{{entity}}')],
        axis="Total Power", unit="watt"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NVLink & Fabric Health (using gpu_nvlink_* metrics)
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink & Fabric Health", y)); y += 1

    panels.append(ts(
        "GPU NVLink Health (per Entity)",
        "WHY: NVLink health per entity — 0 = all links healthy, > 0 = degraded.\n\n"
        "METRIC: gpu_health_nvlink — DCGM NVLink health check.\n"
        "SIGNIFICANCE: Unhealthy NVLink = reduced multi-GPU bandwidth.\n"
        "ACTION: > 0 → check NVLink cables, NVSwitch on affected node.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_health_nvlink{' + EC + '}','{{entity}}')],
        axis="Health (0=OK)"))

    panels.append(ts(
        "GPU NVLink CRC Data Errors",
        "WHY: CRC errors = data integrity failures on NVLink interconnect.\n\n"
        "METRIC: gpu_nvlink_crc_data_errors — cumulative CRC error count.\n"
        "ACTION: Rising trend = cable/connector degrading. Reseat or replace NVLink cable.",
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
    # ROW: SLA Targets & Compliance (Merged from Dashboard 06)
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
        "> **NOTE**: These are aspirational targets. Node uptime 99.5% is the primary contractual SLA.\n\n"
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
        [tgt('sum(nodes_up{' + CL + '}) / clamp_min(sum(nodes_total{' + CL + '}), 1)',
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
    # ROW: Fleet GPU Utilization & Trends
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet GPU Utilization", y)); y += 1

    panels.append(ts(
        "GPU Utilization (per Entity)",
        "WHY: Per-node GPU utilization — which nodes are idle vs loaded.\n\n"
        "METRIC: gpu_utilization — percentage of GPU compute used per entity.\n"
        "TARGET: > 70% = healthy. < 40% = wasted GPU capacity.\n"
        "ACTION: Consistently low on specific nodes = scheduling issue.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('gpu_utilization{' + EC + '}','{{entity}}')],
        axis="Utilization %", unit="percent"))

    panels.append(ts(
        "Fleet Avg GPU Utilization (Trend)",
        "WHY: Fleet-wide GPU utilization trend — is capacity being used efficiently?\n\n"
        "FORMULA: avg(gpu_utilization) across all nodes.\n"
        "SIGNIFICANCE: Trending down = workload migration or scheduling problem.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt('avg(gpu_utilization{' + CL + '})','Fleet Avg')],
        axis="Utilization %", unit="percent"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: XID & DCGM Errors
    # ════════════════════════════════════════════════════════
    panels.append(row("XID / DCGM Errors & Alerts", y)); y += 1

    panels.append(ts(
        "Fleet GPU ECC Error Trend",
        "WHY: Rising ECC errors across fleet = aging/degrading HBM memory.\n\n"
        "METRIC: gpu_ecc_sbe_agg (correctable) vs gpu_ecc_dbe_agg (UNCORRECTABLE).\n"
        "SBE rising = early warning of memory degradation.\n"
        "DBE > 0 = IMMEDIATE GPU REPLACEMENT — data corruption occurred.",
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
        "WHY: Count of nodes with GPU health issues trending over time.\n\n"
        "FORMULA: count(gpu_health_overall > 0).\n"
        "SIGNIFICANCE: Rising trend = fleet aging, environmental issue, or batch defect.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('count(gpu_health_overall{' + CL + '} > 0) or vector(0)','Failures')],
        axis="Failing Nodes"))

    panels.append(ts(
        "Alert Level per Entity",
        "WHY: BCM alert level per entity — identifies which specific nodes have alerts.\n\n"
        "METRIC: alert_level — BCM's internal severity scoring per entity.\n"
        "NOTE: This is a BCM-internal aggregate. Higher values = more/worse alerts on that node.\n"
        "ACTION: Sort by highest to find the most problematic nodes.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('alert_level{' + EC + '}','{{entity}}')],
        axis="Alert Level"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Nodes Requiring Attention (RMA Matrix)
    # ════════════════════════════════════════════════════════
    panels.append(row("Nodes Requiring Attention", y)); y += 1

    panels.append(tbl(
        "GPU RMA Priority Table",
        "WHY: Proactively identify nodes needing hardware replacement.\n\n"
        "SCORING:\n"
        "  • gpu_ecc_dbe_agg > 0 = +100 (uncorrectable memory → IMMEDIATE)\n"
        "  • hardware_corrupted_memory > 0 = +75 (bad DIMM)\n"
        "  • gpu_row_remap_failure == 1 = +50 (HBM repair exhausted)\n"
        "  • gpu_uncorrectable_remapped_rows > 0 = +25 (schedule swap)\n\n"
        "Score ≥ 100 = emergency RMA. Score ≥ 50 = escalate. Score > 0 = schedule.",
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
        "USE: Quick reference for fleet composition at this moment.",
        {"h":8,"w":12,"x":12,"y":y},
        [tgt('nodes_up{' + CL + '}','', fmt="table"),
         tgt('nodes_down{' + CL + '}','', fmt="table"),
         tgt('nodes_closed{' + CL + '}','', fmt="table")],
        transforms=[
            {"id":"merge","options":{}},
            {"id":"organize","options":{
                "excludeByName":{"Time":True,"__name__":True,"job":True},
                "renameByName":{"entity":"Node"}}}],
        sort=[{"displayName":"Node","desc":False}]))
    y += 8

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["00"],
        title="BMaaS — 00 Executive Fleet Overview",
        description="Multi-component fleet health score, node status, GPU-focused panels, "
                    "power per entity, NVLink health, SLA targets, license tracking, "
                    "GPU utilization, ECC errors, and RMA priority table.",
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
