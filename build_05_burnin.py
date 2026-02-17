#!/usr/bin/env python3
"""Dashboard 05 — Burn-in & Certification.
Hardware validation during commissioning/re-certification.
"""
import json, sys
from panel_builders import *

IB_PORTS = [30, 33, 34, 35, 4, 5, 7, 8, 9]

def build_05():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: Burn-in Status Overview
    # ════════════════════════════════════════════════════════
    panels.append(row("Burn-in Status Overview", y)); y += 1

    panels.append(stat(
        "Nodes in Burn-in (Closed)",
        "WHY: Nodes in CLOSED state are undergoing burn-in testing.\n\n"
        "METRIC: devices_closed — intentionally offline for validation.\n"
        "NOTE: Expected during commissioning. Track progress to certification.",
        {"h":5,"w":4,"x":0,"y":y},
        [tgt('sum(devices_closed{' + CL + '}) or vector(0)','Burn-in',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_WR,"value":None}]}))

    panels.append(stat(
        "Nodes Passed (UP)",
        "WHY: Nodes that passed certification and are serving workloads.\n\n"
        "METRIC: devices_up.",
        {"h":5,"w":4,"x":4,"y":y},
        [tgt('sum(devices_up{' + CL + '})','Passed',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None}]}))

    panels.append(stat(
        "Nodes Failed (DOWN)",
        "WHY: Nodes that failed burn-in and need hardware intervention.\n\n"
        "METRIC: devices_down.\n"
        "ACTION: > 0 = check failure reason (ECC, thermal, NVLink, IB, NVMe).",
        {"h":5,"w":4,"x":8,"y":y},
        [tgt('sum(devices_down{' + CL + '}) or vector(0)','Failed',instant=True)],
        color_mode="background", text_mode="value",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Overall Health",
        "WHY: BCM composite health during burn-in.\n\n"
        "METRIC: overall_health — aggregate scored value.\n"
        "SIGNIFICANCE: Declining during stress = hardware issue exposed.",
        {"h":5,"w":4,"x":12,"y":y},
        [tgt('avg(overall_health{' + EC + '})','Score',instant=True)],
        color_mode="value", text_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))

    panels.append(stat(
        "GPUs per Node",
        "WHY: Validate hardware — must be 8 GPUs for DGX B200.\n\n"
        "METRIC: gpu_count.\n"
        "FAIL CRITERIA: gpu_count != 8 = GPU not seated properly.",
        {"h":5,"w":4,"x":16,"y":y},
        [tgt('min(gpu_count{' + EC + '})','Min GPUs',instant=True)],
        color_mode="value", text_mode="value_and_name",
        thresholds={"mode":"absolute","steps":[{"color":C_FL,"value":None},{"color":C_OK,"value":8}]}))

    panels.append(gauge(
        "Pass Rate",
        "WHY: Track certification throughput.\n\n"
        "FORMULA: devices_up / devices_total.\n"
        "TARGET: 100% when all nodes pass.",
        {"h":5,"w":4,"x":20,"y":y},
        [tgt('sum(devices_up{' + CL + '}) / sum(devices_total{' + CL + '})','',instant=True)],
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.8},
            {"color":C_OK,"value":0.95}]}))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: GPU Stress — Temp & Power
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Stress Test — Temperature & Power", y)); y += 1

    panels.append(ts(
        "GPU Die Temp During Stress (All 8)",
        "WHY: GPU stress test should drive temps near max. Overheating = cooling issue.\n\n"
        "METRICS: gpu0_temperature .. gpu7_temperature.\n"
        "PASS: All GPUs < 83°C under full load. FAIL: Any > 90°C.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'gpu{i}_temperature{{' + EC + '}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "HBM Memory Temp During Stress",
        "WHY: HBM memory stress test — validates memory thermal limits.\n\n"
        "METRICS: gpu0_mem_temp .. gpu7_mem_temp.\n"
        "PASS: < 95°C. WARN: 95-105°C. FAIL: > 105°C.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'gpu{i}_mem_temp{{' + EC + '}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="HBM Temp", unit="celsius"))
    y += 6

    panels.append(ts(
        "GPU Power Under Stress",
        "WHY: All GPUs should reach near TDP (1000W) during stress test.\n\n"
        "METRICS: gpu0_power .. gpu7_power.\n"
        "PASS: All within 10% of TDP. FAIL: Significantly below = throttled GPU.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'gpu{i}_power{{' + EC + '}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Power", unit="watt"))

    panels.append(ts(
        "GPU Throttle During Stress",
        "WHY: Throttling during burn-in stress = COOLING ISSUE.\n\n"
        "METRICS: gpu0_throttle .. gpu7_throttle.\n"
        "PASS: All = 0 during stress. FAIL: Any > 0 = check CDU flow.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'gpu{i}_throttle{{' + EC + '}}', f'{{{{entity}}}} GPU{i}') for i in range(8)],
        axis="Throttle"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Memory Stress — ECC & Row Remap
    # ════════════════════════════════════════════════════════
    panels.append(row("Memory Stress — ECC & Row Remap", y)); y += 1

    panels.append(ts(
        "ECC SBE (Volatile) During Burn-in",
        "WHY: Stress test exposes latent memory defects.\n\n"
        "METRIC: gpu_ecc_sbe_vol — correctable errors since GPU reset.\n"
        "PASS: Low count and stable. FAIL: Rapidly rising.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('gpu_ecc_sbe_vol{' + EC + '}','{{entity}}')],
        axis="SBE"))

    panels.append(ts(
        "ECC DBE During Burn-in",
        "WHY: ANY double-bit error = FAIL CERTIFICATION. GPU must be replaced.\n\n"
        "METRIC: gpu_ecc_dbe_vol.\n"
        "CRITERIA: Must be 0 throughout entire burn-in.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('gpu_ecc_dbe_vol{' + EC + '}','{{entity}}')],
        axis="DBE",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))

    panels.append(ts(
        "Row Remap Status",
        "WHY: HBM row remapping during stress — shows pre-existing defects.\n\n"
        "METRICS: gpu_correctable_remapped_rows + gpu_uncorrectable_remapped_rows.\n"
        "FAIL: Uncorrectable > 0 = replace GPU before putting into production.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('gpu_correctable_remapped_rows{' + EC + '}','{{entity}} Correctable'),
         tgt('gpu_uncorrectable_remapped_rows{' + EC + '}','{{entity}} Uncorrectable')],
        axis="Remapped Rows"))

    panels.append(ts(
        "Hardware Corrupted Memory",
        "WHY: System DRAM failure = FAIL CERTIFICATION.\n\n"
        "METRIC: hardware_corrupted_memory.\n"
        "CRITERIA: Must be 0. > 0 = replace DIMM.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('hardware_corrupted_memory{' + EC + '}','{{entity}}')],
        axis="Pages",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: NVLink & IB Validation
    # ════════════════════════════════════════════════════════
    panels.append(row("NVLink & Network Validation", y)); y += 1

    panels.append(ts(
        "NVLink CRC Errors During Burn-in",
        "WHY: NVLink must be error-free for production workloads.\n\n"
        "METRICS: gpu_nvlink_crc_data_errors + gpu_nvlink_crc_flit_errors.\n"
        "PASS: Both = 0 after burn-in. Any > 0 = reseat/replace NVLink cable.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('gpu_nvlink_crc_data_errors{' + EC + '}','{{entity}} Data'),
         tgt('gpu_nvlink_crc_flit_errors{' + EC + '}','{{entity}} Flit')],
        axis="CRC Errors"))

    panels.append(ts(
        "NVLink Bandwidth Verification",
        "WHY: Verify full NVLink bandwidth is achieved during test.\n\n"
        "METRIC: gpu_nvlink_total_bandwidth.\n"
        "PASS: Reaching expected peak for B200 NVLink.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('gpu_nvlink_total_bandwidth{' + EC + '}','{{entity}}')],
        axis="Bandwidth"))

    panels.append(ts(
        "IB Link Downed During Burn-in",
        "WHY: InfiniBand link flaps during test = cable/HCA issue.\n\n"
        "METRIC: infiniband_mlx5_*_link_downed.\n"
        "PASS: No increase during burn-in.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'infiniband_mlx5_{p}_link_downed{{' + EC + '}}', f'{{{{entity}}}} mlx5_{p}')
         for p in IB_PORTS[:5]],
        axis="Link Downed"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Storage & System
    # ════════════════════════════════════════════════════════
    panels.append(row("Storage & System Validation", y)); y += 1

    panels.append(ts(
        "NVMe Health Check",
        "WHY: Validate NVMe drives pass health checks.\n\n"
        "METRICS: nvme*_critical + nvme*_spare.\n"
        "PASS: critical = 0, spare > 10%.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('nvme3_critical{' + EC + '}','{{entity}} nvme3 crit'),
         tgt('nvme3_spare{' + EC + '}','{{entity}} nvme3 spare'),
         tgt('nvme4_critical{' + EC + '}','{{entity}} nvme4 crit'),
         tgt('nvme4_spare{' + EC + '}','{{entity}} nvme4 spare')],
        axis="Health"))

    panels.append(ts(
        "Disk Space",
        "WHY: Validate sufficient disk space post burn-in.\n\n"
        "METRIC: free_space.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('free_space{' + EC + '}','{{entity}}')],
        axis="Free Space", unit="decbytes"))

    panels.append(ts(
        "System Load During Stress",
        "WHY: System stability under full load.\n\n"
        "METRICS: load_one + cores_total.\n"
        "PASS: Stable load, no crashes.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('load_one{' + EC + '}','{{entity}} Load'),
         tgt('cores_total{' + EC + '}','{{entity}} Cores')],
        axis="Count"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Certification Summary
    # ════════════════════════════════════════════════════════
    panels.append(row("Certification Summary", y)); y += 1

    panels.append(tbl(
        "Node Certification Summary",
        "WHY: Single view of all PASS/FAIL signals per node.\n\n"
        "FORMULA: Sum of failure signals — 0 = all tests PASSED.\n"
        "SIGNALS: gpu_ecc_dbe_agg, gpu_uncorrectable_remapped_rows, "
        "gpu_row_remap_failure, gpu_health_overall, hardware_corrupted_memory.",
        {"h":8,"w":24,"x":0,"y":y},
        [tgt(
            '(gpu_ecc_dbe_agg{' + EC + '}) + (gpu_uncorrectable_remapped_rows{' + EC + '}) + '
            '(gpu_row_remap_failure{' + EC + '}) + (gpu_health_overall{' + EC + '}) + '
            '(hardware_corrupted_memory{' + EC + '})',
            '', fmt="table"
        )],
        transforms=[{"id":"organize","options":{
            "excludeByName":{"Time":True,"__name__":True,"job":True,"cluster":True},
            "renameByName":{"entity":"Node","Value":"Fail Score (0 = PASS)"}}}],
        overrides=[
            {"matcher":{"id":"byName","options":"Fail Score (0 = PASS)"},"properties":[
                {"id":"custom.displayMode","value":"color-background-solid"},
                {"id":"thresholds","value":{"mode":"absolute","steps":[
                    {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}}]}],
        sort=[{"displayName":"Fail Score (0 = PASS)","desc":True}]))
    y += 8

    return wrap_dashboard(
        uid=UIDS["05"],
        title="BMaaS — 05 Burn-in & Certification",
        description="Hardware validation: GPU stress (temp/power/throttle), memory (ECC/row remap), "
                    "NVLink/IB validation, NVMe health, certification summary.",
        tags=["bmaas","burnin","certification","validation","gpu","ecc","nvlink","bcm11"],
        panels=panels,
        templating=standard_templating(),
        links=sub_dashboard_links()
    )

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/05-burnin-certification.json"
    d = build_05()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
