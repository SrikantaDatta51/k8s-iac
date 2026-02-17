#!/usr/bin/env python3
"""Dashboard 04 — Workload & Job Performance.
GPU utilization during workloads, power, throttle, error correlation, memory pressure.

v4 OVERHAUL:
- No gauges — stat panels only
- Use gpu_utilization (not total_gpu_utilization)
- Use gpu_power_usage + cpu_power_usage (not total_* versions)
- Reverse sorted legends
"""
import json, sys
from panel_builders import *

def build_04():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: GPU Compute Utilization
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Compute Utilization", y)); y += 1

    panels.append(stat(
        "Fleet Average GPU Utilization",
        "WHY: Fleet-wide GPU util is the primary revenue/efficiency KPI.\n\n"
        "FORMULA: avg(gpu_utilization) across all nodes in cluster.\n"
        "TARGET: > 70% = healthy. < 40% = wasted GPU capacity = revenue loss.",
        {"h":6,"w":4,"x":0,"y":y},
        [tgt('avg(gpu_utilization{' + CL + '})','Avg Util',instant=True)],
        unit="percent", decimals=1,
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":40},
            {"color":C_OK,"value":70}]}))

    panels.append(ts(
        "GPU Utilization (per Entity)",
        "WHY: Per-node GPU utilization shows which nodes are idle vs loaded.\n\n"
        "METRIC: gpu_utilization — percentage of GPU compute used.\n"
        "ACTION: Consistently low on specific nodes = scheduling issue.",
        {"h":6,"w":10,"x":4,"y":y},
        [tgt('gpu_utilization{' + EC + '}','{{entity}}')],
        axis="Utilization %", unit="percent"))

    panels.append(ts(
        "GPU Memory Utilization",
        "WHY: HBM memory usage — high = workloads actively using GPU memory.\n\n"
        "METRIC: total_gpu_memory_utilization.\n"
        "NOTE: Near 100% = risk of OOM on GPU. May need model optimization.",
        {"h":6,"w":10,"x":14,"y":y},
        [tgt('total_gpu_memory_utilization{' + EC + '}','{{entity}}')],
        axis="Memory Util %", unit="percent"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Per-GPU Performance
    # ════════════════════════════════════════════════════════
    panels.append(row("Per-GPU Performance Under Load", y)); y += 1

    panels.append(ts(
        "GPU Clock Speed (All 8)",
        "WHY: Clock speed directly affects compute throughput.\n\n"
        "METRICS: gpu0_clock .. gpu7_clock.\n"
        "SIGNIFICANCE: Lower-than-expected during load = power/thermal throttling.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'gpu{i}_clock{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Clock (MHz)"))

    panels.append(ts(
        "GPU Performance State",
        "WHY: P-state indicates GPU power mode during workload.\n\n"
        "METRICS: gpu0_perfstate .. gpu7_perfstate.\n"
        "EXPECTED: P0 during active training. P8 = idle GPU (not utilized).",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'gpu{i}_perfstate{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="PerfState"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Power During Workload
    # ════════════════════════════════════════════════════════
    panels.append(row("Power During Workload", y)); y += 1

    panels.append(ts(
        "GPU Power per Entity",
        "WHY: GPU power correlates with compute activity. Low power during job = issue.\n\n"
        "METRIC: gpu_power_usage.\n"
        "EXPECTED: Near 8kW (8×1000W TDP) during full training run.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_power_usage{' + EC + '}','{{entity}}')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "Per-GPU Power (All 8)",
        "WHY: Identify specific GPUs drawing less power = possible throttling.\n\n"
        "METRICS: gpu0_power .. gpu7_power.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'gpu{i}_power{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Power", unit="watt"))

    panels.append(ts(
        "Power Limit vs Actual",
        "WHY: Gap between limit and actual = either idle or throttled.\n\n"
        "METRICS: GPU_enforced_power_limit vs gpu_power_usage.\n"
        "SIGNIFICANCE: If actual << limit during load, investigate throttling.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('GPU_enforced_power_limit{' + EC + '}','{{entity}} Limit'),
         tgt('gpu_power_usage{' + EC + '}','{{entity}} Actual')],
        axis="Watts", unit="watt"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Throttle & Thermal Under Load
    # ════════════════════════════════════════════════════════
    panels.append(row("Throttle & Thermal Under Load", y)); y += 1

    panels.append(ts(
        "GPU Throttle Events",
        "WHY: Throttling = forced clock reduction. Performance loss for running jobs.\n\n"
        "METRICS: gpu0_throttle .. gpu7_throttle — 0 = no throttle.\n"
        "ACTION: Sustained > 0 = check CDU cooling, power supply, ambient temp.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'gpu{i}_throttle{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Throttle"))

    panels.append(ts(
        "GPU Temperature Under Load",
        "WHY: Thermal monitoring during active workload.\n\n"
        "METRICS: gpu0_temperature .. gpu7_temperature.\n"
        "THRESHOLD: > 83°C = throttle risk. > 90°C = cooling failure.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'gpu{i}_temperature{{{EC}}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "Thermal & Board Limit Violations",
        "WHY: Violation events during workload = performance impact.\n\n"
        "METRICS: GPU_thermal_violation, gpu_board_limit_violation, gpu_reliability_violation.\n"
        "SIGNIFICANCE: Frequent = hardware approaching limits.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('GPU_thermal_violation{' + EC + '}','{{entity}} Thermal'),
         tgt('gpu_board_limit_violation{' + EC + '}','{{entity}} Board'),
         tgt('gpu_reliability_violation{' + EC + '}','{{entity}} Reliability')],
        axis="Violations"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: ECC Error Correlation
    # ════════════════════════════════════════════════════════
    panels.append(row("ECC Error Correlation During Workload", y)); y += 1

    panels.append(ts(
        "ECC Errors (Volatile / Since Reset)",
        "WHY: Volatile ECC counters show errors that occurred during current workload.\n\n"
        "METRICS: gpu_ecc_sbe_vol (correctable) + gpu_ecc_dbe_vol (UNCORRECTABLE).\n"
        "ACTION: DBE during workload = job results are UNRELIABLE. Stop and replace GPU.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_ecc_sbe_vol{' + EC + '}','{{entity}} SBE'),
         tgt('gpu_ecc_dbe_vol{' + EC + '}','{{entity}} DBE')],
        axis="ECC Errors"))

    panels.append(ts(
        "GPU Recovery Checks",
        "WHY: Automatic GPU recovery = DCGM detected a problem and tried to fix it.\n\n"
        "METRIC: gpu_recovery_check — counter of recovery attempts.\n"
        "ACTION: Frequent = GPU is unstable, schedule maintenance.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_recovery_check{' + EC + '}','{{entity}}')],
        axis="Recovery Events"))

    panels.append(ts(
        "ECC Clock Violations",
        "WHY: ECC checking overhead impacting GPU clock speed.\n\n"
        "METRIC: gpu_total_ecc_clocks_violation.\n"
        "SIGNIFICANCE: Trade-off between reliability and performance.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_total_ecc_clocks_violation{' + EC + '}','{{entity}}')],
        axis="Violations"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Memory Pressure & System
    # ════════════════════════════════════════════════════════
    panels.append(row("System Memory Pressure", y)); y += 1

    panels.append(ts(
        "System Memory Utilization",
        "WHY: Host memory pressure can cause OOM kills, affecting GPU jobs.\n\n"
        "METRIC: memory_utilization.\n"
        "ACTION: > 90% = risk. > 95% = OOM imminent.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('memory_utilization{' + EC + '}','{{entity}}')],
        axis="Utilization %", unit="percent"))

    panels.append(ts(
        "Swap Activity",
        "WHY: Swap usage = system ran out of RAM. TERRIBLE for GPU workloads.\n\n"
        "METRICS: swap_used + swap_total.\n"
        "ACTION: swap_used > 0 during GPU job = memory leak or overcommit.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('swap_used{' + EC + '}','{{entity}} Used'),
         tgt('swap_total{' + EC + '}','{{entity}} Total')],
        axis="Swap", unit="decbytes"))

    panels.append(ts(
        "System Load vs Cores",
        "WHY: Load > core count = CPU oversubscribed, bottlenecking GPU.\n\n"
        "METRICS: load_one + cores_total.\n"
        "RULE: load_one < cores_total = healthy.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('load_one{' + EC + '}','{{entity}} Load 1m'),
         tgt('cores_total{' + EC + '}','{{entity}} Cores')],
        axis="Count"))

    panels.append(ts(
        "Paging Activity",
        "WHY: High paging = kernel swapping memory pages. Severe GPU workload impact.\n\n"
        "METRICS: paging_in + paging_out.\n"
        "ACTION: Sustained high paging = add RAM or reduce workload count.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('paging_in{' + EC + '}','{{entity}} PageIn'),
         tgt('paging_out{' + EC + '}','{{entity}} PageOut')],
        axis="Pages/s"))
    y += 6

    return wrap_dashboard(
        uid=UIDS["04"],
        title="BMaaS — 04 Workload & Job Performance V6",
        description="GPU utilization during jobs, per-GPU clock/power, throttle/thermal, "
                    "ECC error correlation, recovery checks, memory pressure.",
        tags=["bmaas","workload","job","performance","gpu","utilization","bcm11","v6"],
        panels=panels,
        templating=standard_templating(),
        links=sub_dashboard_links()
    )

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/04-workload-job-performance.json"
    d = build_04()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
