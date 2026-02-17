#!/usr/bin/env python3
"""Dashboard 01 — GPU Health & Diagnostics.
Per-GPU deep-dive. Answer: 'Which GPUs need replacement? Is a GPU about to fail?'
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

    # GPU Health Matrix — state-timeline heatmap
    panels.append(heatmap(
        "GPU Health Matrix",
        "Per-node/GPU overall DCGM health status. Red = FAIL, Yellow = WARN, Green = PASS.",
        {"h":8,"w":12,"x":0,"y":y},
        [tgt('gpu_health_overall{' + N + ', ' + GPU + '}',
             '{{instance}} GPU{{gpu}}')]))

    # Hardware Replacement Decision
    panels.append(stat(
        "⛔ GPUs Needing Replacement",
        "GPUs with DBE > 0, row remap failure, or uncorrectable remapped rows > 0. "
        "Any value > 0 = initiate RMA.",
        {"h":4,"w":6,"x":12,"y":y},
        [tgt('count('
             '(gpu_ecc_dbe_agg{' + N + '} > 0) or '
             '(gpu_row_remap_failure{' + N + '} == 1) or '
             '(gpu_uncorrectable_remapped_rows{' + N + '} > 0)'
             ') or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "⚠️ GPUs Approaching Limit",
        "GPUs with correctable remapped rows > 256 (approaching 512 limit).",
        {"h":4,"w":6,"x":18,"y":y},
        [tgt('count(gpu_correctable_remapped_rows{' + N + '} > 256) or vector(0)',
             '',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":1}]}))

    # Sub-component health stats
    comps = [
        ("gpu_health_driver","Driver",C_OK),("gpu_health_mem","Memory",C_OK),
        ("gpu_health_nvlink","NVLink",C_OK),("gpu_health_pcie","PCIe",C_OK),
        ("gpu_health_sm","SM",C_OK),("gpu_health_thermal","Thermal",C_OK),
    ]
    for i,(metric,label,_) in enumerate(comps):
        panels.append(stat(label, f"DCGM {label} health check.",
            {"h":4,"w":2,"x":12+i*2,"y":y+4},
            [tgt(f'max({metric}{{' + N + ', ' + GPU + '}}) or vector(-1)','',instant=True)],
            color_mode="background",
            mappings=[
                {"type":"value","options":{"-1":{"text":"N/A","color":C_UK}}},
                {"type":"value","options":{"0":{"text":"OK","color":C_OK}}},
                {"type":"value","options":{"1":{"text":"FAIL","color":C_FL}}}],
            thresholds={"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW: ECC Error Tracking
    # ════════════════════════════════════════════════════════
    panels.append(row("ECC Error Tracking", y)); y += 1

    panels.append(ts(
        "ECC Single-Bit Errors (Aggregate)",
        "gpu_ecc_sbe_agg — correctable errors. Rising trend = early memory degradation.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_ecc_sbe_agg{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="SBE Count",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]}]))

    panels.append(ts(
        "ECC Double-Bit Errors (Aggregate)",
        "gpu_ecc_dbe_agg — UNCORRECTABLE errors. > 0 = IMMEDIATE REPLACEMENT.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_ecc_dbe_agg{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="DBE Count",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "ECC Volatile (Since Reboot)",
        "gpu_ecc_sbe_vol / gpu_ecc_dbe_vol — errors since last GPU reset.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_ecc_sbe_vol{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} SBE'),
         tgt('gpu_ecc_dbe_vol{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} DBE')],
        axis="Errors"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Row Remapping Status
    # ════════════════════════════════════════════════════════
    panels.append(row("Row Remapping Status", y)); y += 1

    panels.append(ts(
        "Correctable Remapped Rows",
        "gpu_correctable_remapped_rows — tracks HBM bank repairs. Limit ~512.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_correctable_remapped_rows{' + N + ', ' + GPU + '}',
             '{{instance}} GPU{{gpu}}')],
        axis="Remapped Rows"))

    panels.append(ts(
        "Uncorrectable Remapped Rows",
        "gpu_uncorrectable_remapped_rows — > 0 = SCHEDULE REPLACEMENT.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_uncorrectable_remapped_rows{' + N + ', ' + GPU + '}',
             '{{instance}} GPU{{gpu}}')],
        axis="Remapped Rows",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "Row Remap Failure",
        "gpu_row_remap_failure — 1 = row remapping EXHAUSTED. IMMEDIATE REPLACEMENT.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_row_remap_failure{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Failure (0/1)",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: XID Error History
    # ════════════════════════════════════════════════════════
    panels.append(row("XID Error History", y)); y += 1

    panels.append(ts(
        "XID Error Timeline",
        "job_gpu_xid_error — Critical XIDs: 48 (ECC DBE), 63 (page retirement), "
        "64 (row remap), 74 (NVLink), 79 (NVLink access), 92/94/95 (ECC).",
        {"h":6,"w":24,"x":0,"y":y},
        [tgt('job_gpu_xid_error{' + N + '}','{{instance}} GPU{{gpu}} XID={{xid}}')],
        axis="XID Events"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: GPU Temperature & Throttling
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Temperature & Throttling", y)); y += 1

    panels.append(ts(
        "GPU Core Temperature",
        "gpu_temperature — B200 liquid-cooled max ~83°C, air-cooled ~90°C.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_temperature{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "HBM Memory Temperature",
        "gpu_hbm_memory_temperature — > 95°C warning, > 105°C critical.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_hbm_memory_temperature{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "Thermal Violation Duration",
        "gpu_thermal_violation — > 0 = GPU clocks throttled. Sustained = cooling issue.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_thermal_violation{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Violation (µs)",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: GPU Power Profile
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Power Profile", y)); y += 1

    panels.append(ts(
        "GPU Power Usage",
        "gpu_power_usage — B200 TDP = 1000W. Sustained near TDP = normal under load.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_power_usage{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "Power Limit vs Usage",
        "gpu_enforced_power_limit vs gpu_power_usage. Gap = headroom.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_enforced_power_limit{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} Limit'),
         tgt('gpu_power_usage{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} Usage')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "Power Violation Duration",
        "gpu_power_violation — > 0 = GPU clocks throttled due to power cap.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_power_violation{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Violation (µs)"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NVLink Per-GPU & NVSwitch
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink Per-GPU & NVSwitch", y)); y += 1

    panels.append(ts(
        "NVLink CRC Data Errors",
        "gpu_nvlink_crc_data_errors — rising = NVLink cable/connector degradation.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_nvlink_crc_data_errors{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="CRC Errors"))

    panels.append(ts(
        "NVLink CRC Flit Errors",
        "gpu_nvlink_crc_flit_errors — low-level link noise.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_nvlink_crc_flit_errors{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Flit Errors"))

    panels.append(ts(
        "NVSwitch Fatal / Non-Fatal",
        "gpu_health_nvswitch_fatal / gpu_health_nvswitch_non_fatal — fatal != PASS = ESCALATE.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_health_nvswitch_fatal{' + N + '}','{{instance}} Fatal'),
         tgt('gpu_health_nvswitch_non_fatal{' + N + '}','{{instance}} Non-Fatal')],
        axis="Health (0=PASS)"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: C2C Link & PCIe & Utilization
    # ════════════════════════════════════════════════════════
    panels.append(row("C2C Link, PCIe & Utilization", y)); y += 1

    panels.append(ts(
        "C2C Link Status",
        "gpu_c2c_link_status / gpu_c2c_link_bandwidth — chip-to-chip connectivity.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_c2c_link_status{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} Status'),
         tgt('gpu_c2c_link_bandwidth{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} BW')],
        axis="Status / BW"))

    panels.append(ts(
        "GPU Utilization Overview",
        "gpu_utilization, gpu_mem_utilization — baseline performance tracking.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_utilization{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} Compute'),
         tgt('gpu_mem_utilization{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} Mem')],
        axis="Utilization %", unit="percent"))

    panels.append(ts(
        "GPU Fabric Status",
        "gpu_fabric_status per GPU — GPU excluded from NVLink domain = reduced multi-GPU perf.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_fabric_status{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Fabric Status"))
    y += 6

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["01"],
        title="BMaaS — 01 GPU Health & Diagnostics",
        description="Per-GPU deep-dive: ECC errors, row remapping, XID errors, thermal/power, "
                    "NVLink per-GPU, NVSwitch, C2C, PCIe, utilization. Hardware replacement signals.",
        tags=["bmaas","gpu","health","diagnostics","ecc","xid","nvlink","b200","bcm11"],
        panels=panels,
        templating=standard_templating(extra_vars=[gpu_var()]),
        links=sub_dashboard_links()
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/01-gpu-health-diagnostics.json"
    d = build_01()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
    for p in d["panels"]:
        print(f"  [{p.get('type',''):14s}] {p.get('title','')}")
