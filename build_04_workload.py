#!/usr/bin/env python3
"""Dashboard 04 — Workload & Job Performance.
Job-level monitoring.
Answer: 'Will this job fail? Are GPUs being used efficiently?'
"""
import json, sys
from panel_builders import *

def build_04():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: Job Overview
    # ════════════════════════════════════════════════════════
    panels.append(row("Job Overview", y)); y += 1

    panels.append(stat(
        "Job Completion Rate",
        "Percentage of jobs completed successfully. SLA target: ≥ 95%.",
        {"h":5,"w":6,"x":0,"y":y},
        [tgt(
            'sum(bcm_job_completed{' + CL + '}) / '
            'clamp_min(sum(bcm_job_completed{' + CL + '}) + sum(bcm_job_failed{' + CL + '}), 1)',
            '', instant=True)],
        color_mode="background", unit="percentunit", decimals=1,
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.9},
            {"color":C_OK,"value":0.95}]}))

    panels.append(stat(
        "Jobs Running", "Currently running jobs.",
        {"h":5,"w":4,"x":6,"y":y},
        [tgt('sum(bcm_job_running{' + CL + '}) or vector(0)','',instant=True)],
        color_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))

    panels.append(stat(
        "Jobs Pending", "Jobs waiting for resources.",
        {"h":5,"w":4,"x":10,"y":y},
        [tgt('sum(bcm_job_pending{' + CL + '}) or vector(0)','',instant=True)],
        color_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_WR,"value":None}]}))

    panels.append(stat(
        "Jobs Failed (24h)", "Jobs failed in last 24 hours.",
        {"h":5,"w":5,"x":14,"y":y},
        [tgt('sum(increase(bcm_job_failed{' + CL + '}[24h])) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":5},
            {"color":C_FL,"value":20}]}))

    panels.append(stat(
        "Jobs Completed (24h)", "Jobs completed in last 24 hours.",
        {"h":5,"w":5,"x":19,"y":y},
        [tgt('sum(increase(bcm_job_completed{' + CL + '}[24h])) or vector(0)','',instant=True)],
        color_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_GN,"value":None}]}))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: Job GPU Utilization
    # ════════════════════════════════════════════════════════
    panels.append(row("Job GPU Utilization", y)); y += 1

    panels.append(ts(
        "Job GPU Utilization",
        "job_gpu_utilization — per-job GPU compute utilization. Low = underutilized GPUs.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('job_gpu_utilization{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="Utilization", unit="percent"))

    panels.append(ts(
        "Job GPU Memory Utilization",
        "job_gpu_mem_utilization — per-job GPU memory usage.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('job_gpu_mem_utilization{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="Mem Utilization", unit="percent"))

    panels.append(ts(
        "GPU Wasted per Job",
        "job_gpu_wasted — GPUs allocated but idle. High = resource waste.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('job_gpu_wasted{' + N + '}','Job {{job_id}}')],
        axis="Wasted GPUs",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Job Error Correlation
    # ════════════════════════════════════════════════════════
    panels.append(row("Job Error Correlation", y)); y += 1

    panels.append(ts(
        "Job GPU XID Errors",
        "job_gpu_xid_error — XID errors during job execution. Critical: 48, 63, 64, 74, 79, 92-95.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('job_gpu_xid_error{' + N + '}','Job {{job_id}} GPU{{gpu}} XID={{xid}}')],
        axis="XID Events"))

    panels.append(ts(
        "Job GPU ECC DBE",
        "job_gpu_ecc_dbe_agg — double-bit ECC errors during job. > 0 = data corruption risk.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('job_gpu_ecc_dbe_agg{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="DBE",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "Job Row Remap Failure",
        "job_gpu_row_remap_failure — row remapping exhausted during job.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('job_gpu_row_remap_failure{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="Remap Failure"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Job Throttling & Memory Pressure
    # ════════════════════════════════════════════════════════
    panels.append(row("Job Throttling & Memory Pressure", y)); y += 1

    panels.append(ts(
        "Job Thermal Violations",
        "job_gpu_thermal_violation — GPU clocks throttled due to temperature during job.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('job_gpu_thermal_violation{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="Violation (µs)"))

    panels.append(ts(
        "Job Power Violations",
        "job_gpu_power_violation — GPU clocks throttled due to power cap during job.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('job_gpu_power_violation{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="Violation (µs)"))

    panels.append(ts(
        "Job Reliability Violations",
        "job_gpu_reliability_violation — GPU reliability events during job.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('job_gpu_reliability_violation{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="Violation"))

    panels.append(ts(
        "Job Memory Pressure",
        "job_memory_failcnt — OOM events. > 0 = job may crash.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('job_memory_failcnt{' + N + '}','Job {{job_id}}'),
         tgt('job_memory_cache_bytes{' + N + '}','Job {{job_id}} Cache')],
        axis="Count / Bytes"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Job Power & Chargeback
    # ════════════════════════════════════════════════════════
    panels.append(row("Job Power & Chargeback", y)); y += 1

    panels.append(ts(
        "Job GPU Power Usage",
        "job_gpu_power_usage — per-job GPU power draw.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('job_gpu_power_usage{' + N + '}','Job {{job_id}} GPU{{gpu}}')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "Job CPU Power Usage",
        "job_cpu_power_usage — per-job CPU power draw.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('job_cpu_power_usage{' + N + '}','Job {{job_id}}')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "Job Completion Rate Over Time",
        "Success vs failure rate over sliding window.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(
            'sum(increase(bcm_job_completed{' + CL + '}[1h])) / '
            'clamp_min(sum(increase(bcm_job_completed{' + CL + '}[1h])) + '
            'sum(increase(bcm_job_failed{' + CL + '}[1h])), 1)',
            'Success Rate')],
        axis="Rate", unit="percentunit"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Single-Node vs Multi-Node Failure Prediction
    # ════════════════════════════════════════════════════════
    panels.append(row("Failure Prediction Signals", y)); y += 1

    panels.append(tbl(
        "Single-Node Job Failure Signals",
        "Nodes with active GPU health issues, ECC errors, memory pressure, or thermal violations "
        "that predict single-node job failures.",
        {"h":8,"w":12,"x":0,"y":y},
        [tgt(
            '(gpu_health_overall{' + N + '} != 0) or '
            '(gpu_ecc_dbe_agg{' + N + '} > 0) or '
            '(gpu_thermal_violation{' + N + '} > 0)',
            '', fmt="table")],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"instance":"Node","gpu":"GPU","Value":"Signal"}}}],
        sort=[{"displayName":"Signal","desc":True}]))

    panels.append(tbl(
        "Multi-Node Job Failure Signals",
        "Single-node signals PLUS NVLink errors, InfiniBand errors, NMX domain health, "
        "GPU fabric status. Any signal = multi-node job at risk.",
        {"h":8,"w":12,"x":12,"y":y},
        [tgt(
            '(gpu_nvlink_crc_data_errors{' + N + '} > 0) or '
            '(nmxm_domain_health_count{' + CL + ', state="unhealthy"} > 0) or '
            '(gpu_fabric_status{' + N + '} != 0)',
            '', fmt="table")],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"instance":"Node","gpu":"GPU","state":"State","Value":"Signal"}}}],
        sort=[{"displayName":"Signal","desc":True}]))
    y += 8

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["04"],
        title="BMaaS — 04 Workload & Job Performance",
        description="Job completion rate, GPU utilization per job, wasted GPUs, XID/ECC errors during jobs, "
                    "thermal/power/reliability violations, memory pressure, power consumption, failure prediction.",
        tags=["bmaas","workload","job","performance","gpu","utilization","bcm11"],
        panels=panels,
        templating=standard_templating(extra_vars=[gpu_var()]),
        links=sub_dashboard_links()
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/04-workload-job-performance.json"
    d = build_04()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
    for p in d["panels"]:
        print(f"  [{p.get('type',''):14s}] {p.get('title','')}")
