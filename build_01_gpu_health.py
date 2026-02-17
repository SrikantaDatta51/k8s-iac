#!/usr/bin/env python3
"""Dashboard 01 — GPU Health & Diagnostics.
Per-GPU deep-dive using indexed metrics (gpu0-gpu7).

v4 OVERHAUL:
- Fixed all imbalanced braces in queries
- Use gpu_nvlink_* for NVLink (not nv_link_switches_*)
- Use gpu_utilization (not total_gpu_utilization)
- No gauges — stat + timeseries only
- No DPU or IB node panels (not available)
- Reverse sorted legends
- Per-entity bar gauge for GPU count
"""
import json, sys
from panel_builders import *

def build_01():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: GPU Health Overview
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Health Overview", y)); y += 1

    panels.append(heatmap(
        "GPU Health Matrix (per Node)",
        "WHY: Instantly visualize which nodes have GPU health issues.\n\n"
        "METRIC: gpu_health_overall — DCGM aggregate health check.\n"
        "0 = PASS (green), > 0 = FAIL (red). Each row = one DGX node.\n"
        "SIGNIFICANCE: Failed nodes should NOT receive new workloads.\n"
        "ACTION: Filter by specific node using the dropdown to drill down.",
        {"h":8,"w":12,"x":0,"y":y},
        [tgt('gpu_health_overall{' + EC + '}','{{entity}}')]))

    panels.append(bargauge(
        "GPUs per Entity",
        "WHY: Validate hardware config — B200 DGX should have 8 GPUs.\n\n"
        "METRIC: gpu_count — GPUs detected by DCGM per entity.\n"
        "SIGNIFICANCE: < 8 = GPU not detected = hardware failure.\n"
        "ACTION: Check GPU seating, PCIe link, DCGM logs.",
        {"h":8,"w":6,"x":12,"y":y},
        [tgt('gpu_count{' + EC + '}','{{entity}}',instant=True)],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":7},
            {"color":C_OK,"value":8}]}))

    panels.append(stat(
        "Nodes Needing GPU RMA",
        "WHY: Proactive RMA tracking to minimize downtime.\n\n"
        "CRITERIA: gpu_ecc_dbe_agg > 0 (uncorrectable memory) OR "
        "gpu_row_remap_failure == 1 (HBM repair exhausted) OR "
        "gpu_uncorrectable_remapped_rows > 0.\n\n"
        "ACTION: Any > 0 = open RMA ticket with NVIDIA.",
        {"h":4,"w":6,"x":18,"y":y},
        [tgt('count('
             '(gpu_ecc_dbe_agg{' + EC + '} > 0) or '
             '(gpu_row_remap_failure{' + EC + '} == 1) or '
             '(gpu_uncorrectable_remapped_rows{' + EC + '} > 0)'
             ') or vector(0)','RMA Candidates',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    # Sub-component health flags
    comps = [
        ("gpu_health_mem","Memory",
         "WHY: Detects HBM memory faults — ECC errors, row remapping issues.\n0 = OK, > 0 = memory degrading."),
        ("gpu_health_nvlink","NVLink",
         "WHY: NVLink enables 900GB/s GPU-to-GPU communication.\n0 = OK, > 0 = link errors detected."),
        ("gpu_health_pcie","PCIe",
         "WHY: PCIe connects GPU to CPU for data transfer.\n0 = OK, > 0 = bus errors."),
        ("gpu_health_sm","SM",
         "WHY: Streaming Multiprocessors are the GPU compute units.\n0 = OK, > 0 = compute errors."),
        ("gpu_health_thermal","Thermal",
         "WHY: GPU operating within thermal limits.\n0 = OK, > 0 = overheating."),
        ("gpu_health_overall","Overall",
         "WHY: DCGM composite health — OR of all sub-checks.\n0 = ALL healthy, > 0 = investigate."),
    ]
    for i,(metric,label,desc) in enumerate(comps):
        panels.append(stat(label, desc,
            {"h":4,"w":2,"x":12+i*2,"y":y+4},
            [tgt(f'max({metric}{{{EC}}}) or vector(-1)','',instant=True)],
            color_mode="background", text_mode="value",
            mappings=[
                {"type":"value","options":{"-1":{"text":"N/A","color":C_UK}}},
                {"type":"value","options":{"0":{"text":"OK","color":C_OK}}},
                {"type":"range","options":{"from":1,"to":999,"result":{"text":"FAIL","color":C_FL}}}],
            thresholds={"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW: ECC Error Tracking
    # ════════════════════════════════════════════════════════
    panels.append(row("ECC Error Tracking", y)); y += 1

    panels.append(ts(
        "ECC Single-Bit Errors (Aggregate)",
        "WHY: SBE are correctable — the GPU auto-corrects them.\n"
        "Rising trend = HBM memory slowly degrading.\n\n"
        "METRIC: gpu_ecc_sbe_agg — lifetime correctable error count.\n"
        "ACTION: Monitor rate. Rapid increase → schedule maintenance window.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_ecc_sbe_agg{' + EC + '}','{{entity}}')],
        axis="SBE Count",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]}]))

    panels.append(ts(
        "ECC Double-Bit Errors (Aggregate)",
        "WHY: DBE are UNCORRECTABLE — data corruption occurred.\n\n"
        "METRIC: gpu_ecc_dbe_agg — lifetime uncorrectable error count.\n"
        "ACTION: > 0 = IMMEDIATE GPU REPLACEMENT. Workload results unreliable.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_ecc_dbe_agg{' + EC + '}','{{entity}}')],
        axis="DBE Count",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "ECC Volatile (Since Last Reset)",
        "WHY: Volatile counters reset on GPU reset — shows RECENT errors.\n\n"
        "METRICS: gpu_ecc_sbe_vol + gpu_ecc_dbe_vol.\n"
        "SIGNIFICANCE: Helps determine if errors are ongoing or historical.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_ecc_sbe_vol{' + EC + '}','{{entity}} SBE'),
         tgt('gpu_ecc_dbe_vol{' + EC + '}','{{entity}} DBE')],
        axis="Errors"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Row Remapping Status
    # ════════════════════════════════════════════════════════
    panels.append(row("Row Remapping Status", y)); y += 1

    panels.append(ts(
        "Correctable Remapped Rows",
        "WHY: HBM memory auto-repairs bad rows by remapping to spares.\n\n"
        "METRIC: gpu_correctable_remapped_rows — how many rows were repaired.\n"
        "SIGNIFICANCE: Limited spare rows (~512). Approaching limit = replacement.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_correctable_remapped_rows{' + EC + '}','{{entity}}')],
        axis="Remapped Rows"))

    panels.append(ts(
        "Uncorrectable Remapped Rows",
        "WHY: Remapping could NOT fix the row — data at risk.\n\n"
        "METRIC: gpu_uncorrectable_remapped_rows.\n"
        "ACTION: > 0 = SCHEDULE GPU REPLACEMENT. Unreliable compute.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_uncorrectable_remapped_rows{' + EC + '}','{{entity}}')],
        axis="Rows",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "Row Remap Failure Flag",
        "WHY: Spare rows EXHAUSTED — no more auto-repair possible.\n\n"
        "METRIC: gpu_row_remap_failure — 0/1 flag.\n"
        "ACTION: == 1 → IMMEDIATE GPU REPLACEMENT. Cannot self-heal.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_row_remap_failure{' + EC + '}','{{entity}}')],
        axis="Failure (0/1)",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: GPU Temperature (Per-GPU)
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Temperature (per-GPU)", y)); y += 1

    panels.append(ts(
        "GPU Core Temp (gpu0-gpu3)",
        "WHY: Monitor GPU die temperature under load.\n\n"
        "METRICS: gpu0_temperature .. gpu3_temperature.\n"
        "THRESHOLDS: < 75°C = normal (liquid-cooled), > 83°C = throttle risk.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'gpu{i}_temperature{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(4)],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "GPU Core Temp (gpu4-gpu7)",
        "WHY: All 8 GPUs must stay within thermal envelope.\n\n"
        "METRICS: gpu4_temperature .. gpu7_temperature.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'gpu{i}_temperature{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(4,8)],
        axis="Temperature", unit="celsius"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: HBM Memory Temperature
    # ════════════════════════════════════════════════════════
    panels.append(row("HBM Memory Temperature", y)); y += 1

    panels.append(ts(
        "HBM Temp (gpu0-gpu3)",
        "WHY: HBM (High Bandwidth Memory) is thermally sensitive.\n\n"
        "METRICS: gpu0_mem_temp .. gpu3_mem_temp.\n"
        "THRESHOLDS: > 95°C = warning, > 105°C = CRITICAL (data corruption risk).",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'gpu{i}_mem_temp{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(4)],
        axis="HBM Temp", unit="celsius"))

    panels.append(ts(
        "HBM Temp (gpu4-gpu7)",
        "WHY: All 8 GPUs' HBM temperature must be monitored equally.\n\n"
        "METRICS: gpu4_mem_temp .. gpu7_mem_temp.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'gpu{i}_mem_temp{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(4,8)],
        axis="HBM Temp", unit="celsius"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: GPU Power & Throttle
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Power & Throttle", y)); y += 1

    panels.append(ts(
        "Per-GPU Power Draw",
        "WHY: Each B200 GPU has 1000W TDP. Track actual vs budget.\n\n"
        "METRICS: gpu0_power .. gpu7_power — individual GPU wattage.\n"
        "SIGNIFICANCE: Under-TDP during load = throttling. Near-TDP = healthy.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'gpu{i}_power{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Power", unit="watt"))

    panels.append(ts(
        "GPU Throttle Events",
        "WHY: Throttling = GPU forced to reduce clock speed. Performance loss.\n\n"
        "METRICS: gpu0_throttle .. gpu7_throttle — 0 = no throttle.\n"
        "ACTION: Sustained > 0 = check cooling (CDU flow), power supply.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'gpu{i}_throttle{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Throttle"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: GPU Clock & Performance State
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Clock & Performance State", y)); y += 1

    panels.append(ts(
        "GPU SM Clock Speed",
        "WHY: SM clock determines GPU compute throughput.\n\n"
        "METRICS: gpu0_clock .. gpu7_clock.\n"
        "SIGNIFICANCE: Lower-than-expected during load = power/thermal throttling.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'gpu{i}_clock{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Clock (MHz)"))

    panels.append(ts(
        "GPU Performance State",
        "WHY: P-state shows GPU power mode: P0 = max, P8 = idle.\n\n"
        "METRICS: gpu0_perfstate .. gpu7_perfstate.\n"
        "SIGNIFICANCE: P0 during workload = healthy. Higher P-state = underperforming.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'gpu{i}_perfstate{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="PerfState"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NVLink Health & Utilization (gpu_nvlink_* metrics)
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink Health & Utilization", y)); y += 1

    panels.append(ts(
        "GPU NVLink CRC Data Errors",
        "WHY: CRC errors = data corruption on NVLink cables.\n\n"
        "METRIC: gpu_nvlink_crc_data_errors.\n"
        "ACTION: Rising = cable/connector degrading. Reseat or replace NVLink cable.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_nvlink_crc_data_errors{' + EC + '}','{{entity}}')],
        axis="CRC Errors"))

    panels.append(ts(
        "GPU NVLink CRC Flit Errors",
        "WHY: Flit = smallest NVLink transfer unit. Flit errors = link noise.\n\n"
        "METRIC: gpu_nvlink_crc_flit_errors.\n"
        "SIGNIFICANCE: Usually lower severity than data errors, but monitor trend.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_nvlink_crc_flit_errors{' + EC + '}','{{entity}}')],
        axis="Flit Errors"))

    panels.append(ts(
        "GPU Utilization",
        "WHY: Track compute usage per entity.\n\n"
        "METRIC: gpu_utilization — SM activity %.\n"
        "TARGET: > 70% during active jobs.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_utilization{' + EC + '}','{{entity}}')],
        axis="Utilization %", unit="percent"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Advanced GPU Diagnostics
    # ════════════════════════════════════════════════════════
    panels.append(row("Advanced GPU Diagnostics", y)); y += 1

    panels.append(ts(
        "GPU Fabric Status",
        "WHY: Fabric status shows if GPU is included in NVLink domain.\n\n"
        "METRIC: GPU_fabric_status — 0 = in domain, > 0 = excluded.\n"
        "ACTION: Excluded GPU = reduced multi-GPU performance. Check NVSwitch.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('GPU_fabric_status{' + EC + '}','{{entity}}')],
        axis="Status"))

    panels.append(ts(
        "Thermal Violation",
        "WHY: GPU exceeded thermal limit — clock throttled to cool down.\n\n"
        "METRIC: GPU_thermal_violation — counter of thermal throttle events.\n"
        "ACTION: Frequent = check CDU/cooling flow, ambient temperature.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('GPU_thermal_violation{' + EC + '}','{{entity}}')],
        axis="Violations",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "Board Limit Violation",
        "WHY: Board-level power or thermal limit exceeded — entire baseboard issue.\n\n"
        "METRIC: gpu_board_limit_violation.\n"
        "SIGNIFICANCE: May indicate PSU degradation or chassis thermal issue.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('gpu_board_limit_violation{' + EC + '}','{{entity}}')],
        axis="Violations"))

    panels.append(ts(
        "Sync Boost & Reliability Violations",
        "WHY: Sync boost ensures all GPUs run at same clock. Violations = asymmetry.\n\n"
        "METRICS: GPU_sync_boost_violation + gpu_reliability_violation.\n"
        "SIGNIFICANCE: Reliability violations = approaching hardware limit.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('GPU_sync_boost_violation{' + EC + '}','{{entity}} SyncBoost'),
         tgt('gpu_reliability_violation{' + EC + '}','{{entity}} Reliability')],
        axis="Violations"))
    y += 6

    return wrap_dashboard(
        uid=UIDS["01"],
        title="BMaaS — 01 GPU Health & Diagnostics",
        description="Per-GPU deep-dive: DCGM health matrix, ECC SBE/DBE, row remapping, "
                    "temperature (core+HBM), power/throttle, clock/perfstate, NVLink errors.",
        tags=["bmaas","gpu","health","diagnostics","ecc","nvlink","b200","bcm11"],
        panels=panels,
        templating=standard_templating(),
        links=sub_dashboard_links()
    )

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/01-gpu-health-diagnostics.json"
    d = build_01()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
