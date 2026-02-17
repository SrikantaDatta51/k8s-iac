#!/usr/bin/env python3
"""Dashboard 05 — Burn-in & Certification.
Node validation before production.
Answer: 'Is this node ready for customer workloads?'
"""
import json, sys
from panel_builders import *

def build_05():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: Burn-in Status Overview
    # ════════════════════════════════════════════════════════
    panels.append(row("Burn-in Status Overview", y)); y += 1

    for i,(state,label,color) in enumerate([
        ("installer_callinginit","Calling Init",C_TL),
        ("installer_burning","Installer Burning",C_OR),
        ("burning","Burning",C_WR),
        ("UP","Certified (UP)",C_OK),
    ]):
        panels.append(stat(label,
            f"Nodes currently in '{state}' state.",
            {"h":5,"w":6,"x":i*6,"y":y},
            [tgt(f'count(bcm_node_state{{' + CL + f', state="{state}"}}) or vector(0)',
                 '',instant=True)],
            color_mode="background",
            thresholds={"mode":"absolute","steps":[{"color":color,"value":None}]}))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: Node State Timeline
    # ════════════════════════════════════════════════════════
    panels.append(row("Node State Timeline", y)); y += 1

    panels.append(heatmap(
        "Node State Transitions",
        "Track node provisioning lifecycle: callinginit → burning → UP (or FAILED).",
        {"h":8,"w":24,"x":0,"y":y},
        [tgt('bcm_node_state_numeric{' + N + '}','{{instance}}')]))
    y += 8

    # ════════════════════════════════════════════════════════
    # ROW: GPU Stress Test Results
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Stress Test Results", y)); y += 1

    panels.append(ts(
        "GPU Temperature During Burn-in",
        "gpu_temperature during burn-in. Must stay within spec (< 83°C liquid, < 90°C air).",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_temperature{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "GPU Power During Burn-in",
        "gpu_power_usage during stress. Should sustain near TDP (1000W for B200).",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_power_usage{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "GPU Throttle Events During Burn-in",
        "gpu_thermal_violation + gpu_power_violation. Must be 0 for certification.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('gpu_thermal_violation{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} Thermal'),
         tgt('gpu_power_violation{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}} Power')],
        axis="Violation (µs)"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Memory Stress Results
    # ════════════════════════════════════════════════════════
    panels.append(row("Memory Stress Results", y)); y += 1

    panels.append(ts(
        "ECC SBE During Burn-in",
        "gpu_ecc_sbe_agg accumulation during burn-in. Must stay below threshold.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('gpu_ecc_sbe_agg{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="SBE Count"))

    panels.append(ts(
        "ECC DBE During Burn-in",
        "gpu_ecc_dbe_agg during burn-in. Must be ZERO for certification pass.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt('gpu_ecc_dbe_agg{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="DBE Count",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NVLink & Network Validation
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink & Network Validation", y)); y += 1

    panels.append(ts(
        "NVLink CRC Errors During Burn-in",
        "gpu_nvlink_crc_data_errors during all-to-all traffic test. Must be ZERO.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_nvlink_crc_data_errors{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="CRC Errors"))

    panels.append(ts(
        "NVLink Bandwidth During Stress",
        "gpu_nvlink_total_bandwidth during test. Must be ≥ 95% of spec.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_nvlink_total_bandwidth{' + N + ', ' + GPU + '}','{{instance}} GPU{{gpu}}')],
        axis="Bandwidth", unit="Bps"))

    panels.append(ts(
        "InfiniBand During MPI Benchmark",
        "ib_xmit_data / ib_rcv_data rates during benchmark. Must hit ≥ 95% of spec.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('rate(ib_xmit_data{' + N + '}[5m])','{{instance}} TX'),
         tgt('rate(ib_rcv_data{' + N + '}[5m])','{{instance}} RX')],
        axis="Throughput", unit="Bps"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Storage & Hardware Profile Validation
    # ════════════════════════════════════════════════════════
    panels.append(row("Storage & Hardware Profile Validation", y)); y += 1

    panels.append(ts(
        "SMART Before/After Burn-in",
        "smart_reallocated_sector_ct — no new reallocated sectors after burn-in.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('smart_reallocated_sector_ct{' + N + '}','{{instance}} {{disk}}')],
        axis="Reallocated Sectors"))

    panels.append(stat(
        "Hardware Profile Match",
        "node-hardware-profile comparison against reference profile. MATCH = certified.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('bcm_health_check_status{' + N + ', check="hardware-profile"}',
             '{{instance}}',instant=True)],
        color_mode="background",
        mappings=[
            {"type":"value","options":{"0":{"text":"MATCH ✅","color":C_OK}}},
            {"type":"value","options":{"1":{"text":"DRIFT ❌","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Time to Certification",
        "Duration from installer_callinginit to UP state.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(
            '(bcm_node_up_timestamp{' + N + '} - bcm_node_burn_start_timestamp{' + N + '}) > 0',
            '{{instance}}', instant=True)],
        color_mode="value", unit="s",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Certification Summary
    # ════════════════════════════════════════════════════════
    panels.append(row("Certification Summary", y)); y += 1

    panels.append(tbl(
        "Certification Summary — All Nodes",
        "Composite of all burn-in checks per node. All must PASS for production.",
        {"h":8,"w":24,"x":0,"y":y},
        [tgt(
            '('
            '(gpu_ecc_dbe_agg{' + N + '} == 0) * 1 + '
            '(gpu_thermal_violation{' + N + '} == 0) * 1 + '
            '(gpu_row_remap_failure{' + N + '} == 0) * 1'
            ') / 3',
            '', fmt="table")],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"instance":"Node","gpu":"GPU","Value":"Cert Score (1.0=PASS)"}}}],
        overrides=[
            {"matcher":{"id":"byName","options":"Cert Score (1.0=PASS)"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_FL,"value":None},{"color":C_WR,"value":0.67},
                    {"color":C_OK,"value":1}]}}]}],
        sort=[{"displayName":"Cert Score (1.0=PASS)","desc":False}]))
    y += 8

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["05"],
        title="BMaaS — 05 Burn-in & Certification",
        description="Node validation: burn-in state tracking, GPU/memory stress results, NVLink/IB validation, "
                    "storage health, hardware profile matching, certification summary.",
        tags=["bmaas","burnin","certification","validation","stress","b200","bcm11"],
        panels=panels,
        templating=standard_templating(extra_vars=[gpu_var()]),
        links=sub_dashboard_links()
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/05-burnin-certification.json"
    d = build_05()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
    for p in d["panels"]:
        print(f"  [{p.get('type',''):14s}] {p.get('title','')}")
