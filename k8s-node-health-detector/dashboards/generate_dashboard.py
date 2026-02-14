#!/usr/bin/env python3
"""Generate SentinAI Node Health Detector Grafana Dashboard — v4.
Dedicated panel per critical path component using industry-standard metrics.

Data sources used:
  - DCGM Exporter (DCGM_FI_*)           — GPU health
  - node_exporter (node_*)               — CPU, memory, disk, network, IB
  - kube-state-metrics (kube_*)          — K8s state
  - kubelet (/metrics)                   — container runtime ops
  - SentinAI agent (node_health_*)       — health check results
"""
import json, sys

_id = 0
def nid():
    global _id; _id += 1; return _id

def ds():
    return {"type": "prometheus", "uid": "${datasource}"}

def tgt(expr, legend, instant=False, fmt="time_series"):
    t = {"refId": "", "datasource": ds(), "expr": expr, "legendFormat": legend}
    if instant: t["instant"] = True
    if fmt == "table": t["format"] = "table"; t["instant"] = True
    return t

def refs(targets):
    for i, t in enumerate(targets): t["refId"] = chr(65 + i % 26)
    return targets

LEGEND_R = {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull"]}
LEGEND_F = {"displayMode": "table", "placement": "right", "calcs": ["min","max","mean","lastNotNull"]}

# Professional palette
C_OK  = "#56A64B"; C_WR = "#E0A939"; C_FL = "#C04040"; C_UK = "#8F8F8F"
C_P0  = "#C04040"; C_P1 = "#E0663E"; C_P2 = "#E0A939"; C_P3 = "#7EB26D"
C_BL  = "#3274D9"; C_PU = "#8F3BB8"; C_TL = "#6ED0E0"; C_OR = "#EF843C"

N = 'node=~"$node"'
I = 'instance=~"$node.*"'  # node_exporter uses instance

# ── PANEL BUILDERS ─────────────────────────────────────────

def row(title, y, collapsed=False):
    return {"type":"row","title":title,"collapsed":collapsed,
            "gridPos":{"h":1,"w":24,"x":0,"y":y},"id":nid(),"panels":[]}

def stat(title, desc, gp, targets, unit="none", decimals=0,
         thresholds=None, color_mode="background", text_mode="auto",
         graph_mode="none", mappings=None):
    return {"id":nid(),"title":title,"description":desc,"type":"stat",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"unit":unit,"decimals":decimals,
            "thresholds":thresholds or {"mode":"absolute","steps":[{"color":C_OK,"value":None}]},
            "mappings":mappings or [],"noValue":"N/A"},"overrides":[]},
        "options":{"reduceOptions":{"calcs":["lastNotNull"],"fields":"","values":False},
            "orientation":"auto","textMode":text_mode,
            "colorMode":color_mode,"graphMode":graph_mode,"justifyMode":"center"},
        "targets":refs(targets)}

def ts(title, desc, gp, targets, axis, unit="short", overrides=None, stacking=None):
    custom = {"lineWidth":2,"fillOpacity":10,"gradientMode":"none",
              "axisLabel":axis,"drawStyle":"line","pointSize":4,
              "showPoints":"never","spanNulls":True}
    if stacking:
        custom["stacking"] = {"mode":stacking}; custom["fillOpacity"]=60; custom["lineWidth"]=0
    return {"id":nid(),"title":title,"description":desc,"type":"timeseries",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"unit":unit,"custom":custom},"overrides":overrides or []},
        "options":{"legend":LEGEND_F,"tooltip":{"mode":"multi","sort":"desc"}},
        "targets":refs(targets)}

def tbl(title, desc, gp, targets, transforms=None, overrides=None, sort=None):
    return {"id":nid(),"title":title,"description":desc,"type":"table",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"custom":{"align":"auto","displayMode":"auto","filterable":True}},
            "overrides":overrides or []},
        "options":{"showHeader":True,"sortBy":sort or []},
        "transformations":transforms or [],"targets":refs(targets)}

def gauge(title, desc, gp, targets, unit="percentunit", thresholds=None):
    return {"id":nid(),"title":title,"description":desc,"type":"gauge",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"unit":unit,"decimals":1,
            "thresholds":thresholds or {"mode":"absolute","steps":[
                {"color":C_FL,"value":None},{"color":C_WR,"value":0.5},
                {"color":C_OK,"value":0.8}]},
            "min":0,"max":1},"overrides":[]},
        "options":{"reduceOptions":{"calcs":["lastNotNull"]},
            "showThresholdLabels":False,"showThresholdMarkers":True},
        "targets":refs(targets)}

def heatmap(title, desc, gp, targets):
    return {"id":nid(),"title":title,"description":desc,"type":"state-timeline",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"custom":{"lineWidth":0,"fillOpacity":80},
            "thresholds":{"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_WR,"value":1},
                {"color":C_FL,"value":2},{"color":C_UK,"value":3}]},
            "mappings":[
                {"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                {"type":"value","options":{"1":{"text":"WARN","color":C_WR}}},
                {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}},
                {"type":"value","options":{"3":{"text":"UNK","color":C_UK}}}]},"overrides":[]},
        "options":{"showValue":"auto","mergeValues":True,"alignValue":"center",
            "rowHeight":0.85,"tooltip":{"mode":"multi"},
            "legend":{"displayMode":"list","placement":"bottom"}},
        "targets":refs(targets)}

# Status overrides for check tables
CHECK_STATUS_OVERRIDES = [
    {"matcher":{"id":"byName","options":"Status"},"properties":[
        {"id":"custom.width","value":80},
        {"id":"mappings","value":[
            {"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
            {"type":"value","options":{"1":{"text":"WARN","color":C_WR}}},
            {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}]},
        {"id":"custom.displayMode","value":"color-background-solid"},
        {"id":"thresholds","value":{"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":1},{"color":C_FL,"value":2}]}}]},
    {"matcher":{"id":"byName","options":"Check"},"properties":[{"id":"custom.width","value":220}]},
]
ORGANIZE_T = {"id":"organize","options":{
    "excludeByName":{"Time":True,"__name__":True,"job":True,"instance":True,
        "endpoint":True,"service":True,"namespace":True,"pod":True,"prometheus":True},
    "renameByName":{"node":"Node","check":"Check","component":"Comp",
        "severity":"Sev","Value":"Status"}}}


def build():
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # FLEET HEALTH SCORE
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet Health Score", y)); y += 1

    panels.append(gauge(
        "Fleet Health Score", "Fraction of healthy nodes. 1.0 = all healthy.",
        {"h":5,"w":5,"x":0,"y":y},
        [tgt('avg(node_health_node_healthy) or vector(0)','Fleet',instant=True)]))

    for i,(lbl,expr,color) in enumerate([
        ("Healthy",'count(node_health_node_healthy==1) or vector(0)',C_OK),
        ("Unhealthy",'count(node_health_node_healthy==0) or vector(0)',C_FL),
        ("Cordoned",'count(node_health_should_cordon==1) or vector(0)',C_P1),
        ("Total Nodes",'count(node_health_node_healthy) or vector(0)',C_BL)]):
        panels.append(stat(lbl,"",{"h":5,"w":3,"x":5+i*3,"y":y},
            [tgt(expr,"",instant=True)],color_mode="value",
            thresholds={"mode":"absolute","steps":[{"color":color,"value":None}]}))

    # Per-component fleet worst
    comps = ["gpu","cpu","memory","storage","network","kubernetes"]
    for i,c in enumerate(comps):
        panels.append(stat(c.upper(),"",{"h":5,"w":2,"x":17+i%3*2+i//3*6-i//3*6,"y":y+(i//3)*2 if i>=3 else y},
            [tgt(f'max(node_health_component_status{{component="{c}"}}) or vector(-1)',"",instant=True)],
            color_mode="background",
            mappings=[{"type":"value","options":{"-1":{"text":"N/A","color":C_UK}}},
                {"type":"value","options":{"0":{"text":"OK","color":C_OK}}},
                {"type":"value","options":{"1":{"text":"WARN","color":C_WR}}},
                {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}],
            thresholds={"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_WR,"value":1},{"color":C_FL,"value":2}]}))
    y += 5

    panels.append(ts("Fleet Health Over Time","",{"h":5,"w":12,"x":0,"y":y},
        [tgt('avg(node_health_node_healthy)','Score'),
         tgt('count(node_health_node_healthy==0)/count(node_health_node_healthy)','Unhealthy%')],
        axis="Score", unit="percentunit",
        overrides=[
            {"matcher":{"id":"byName","options":"Score"},"properties":[{"id":"color","value":{"fixedColor":C_OK,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"Unhealthy%"},"properties":[{"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    panels.append(ts("Healthy vs Unhealthy Nodes","",{"h":5,"w":12,"x":12,"y":y},
        [tgt('count(node_health_node_healthy==1) or vector(0)','Healthy'),
         tgt('count(node_health_node_healthy==0) or vector(0)','Unhealthy')],
        axis="Nodes",stacking="normal",
        overrides=[
            {"matcher":{"id":"byName","options":"Healthy"},"properties":[{"id":"color","value":{"fixedColor":C_OK,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"Unhealthy"},"properties":[{"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    y += 5

    # ════════════════════════════════════════════════════════
    # FLEET HEATMAPS
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet Heatmap", y)); y += 1
    panels.append(heatmap("Node x Component Status","Each row = node/component. Scan for red.",
        {"h":10,"w":12,"x":0,"y":y},
        [tgt('node_health_component_status','{{node}} / {{component}}')]))
    panels.append(heatmap("Node x Check Status (Selected)","Per-check drill-down for selected nodes.",
        {"h":10,"w":12,"x":12,"y":y},
        [tgt(f'node_health_check_status{{{N}}}','{{node}} / {{check}}')]))
    y += 10

    # ════════════════════════════════════════════════════════════════════
    # ██  DAY 0 — PER-COMPONENT PROVISIONING PANELS  ██
    # ════════════════════════════════════════════════════════════════════
    panels.append(row("Day 0 — Critical Path Components (Provisioning)", y)); y += 1

    # ── 1. GPU OPERATOR / DRIVER ───────────────────────────
    panels.append(ts(
        "GPU Operator: GPU Count per Node",
        "count(DCGM_FI_DEV_GPU_TEMP) per instance = GPUs visible after operator injection. "
        "Expected: 8 for DGX B200. 0 = driver failure.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'count by (instance) (DCGM_FI_DEV_GPU_TEMP)','{{instance}}')],
        axis="GPU Count"))
    panels.append(ts(
        "GPU Operator: Driver & CUDA Version",
        "DCGM exporter exposes driver version as a label. "
        "All nodes should report the same version to avoid NCCL conflicts.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('DCGM_FI_DRIVER_VERSION','{{instance}} driver={{driver_version}}')],
        axis="Version Present (1)"))
    panels.append(stat(
        "GPU Operator Check", "",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_health_check_status{{{N}, check="day0_gpu_operator"}}','{{node}}',instant=True)],
        color_mode="background",
        mappings=[{"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                  {"type":"value","options":{"1":{"text":"WARN","color":C_WR}}},
                  {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None},{"color":C_WR,"value":1},{"color":C_FL,"value":2}]}))
    y += 6

    # ── 2. NETWORK OPERATOR / MOFED ───────────────────────
    panels.append(ts(
        "Network Operator: IB Port State",
        "node_infiniband_state from node_exporter. 5 = LinkUp (Active). "
        "All HCA ports must be 5 (Active) for RDMA traffic.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'node_infiniband_state{{{I}}}','{{device}} port {{port}}')],
        axis="State (5=Active)"))
    panels.append(ts(
        "Network Operator: IB Physical State",
        "node_infiniband_physical_state. 5 = LinkUp. "
        "Physical != Active means cable/switch issue.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'node_infiniband_physical_state{{{I}}}','{{device}} port {{port}}')],
        axis="Phys State (5=LinkUp)"))
    panels.append(stat(
        "Network Operator Check", "",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_health_check_status{{{N}, check="day0_network_operator"}}','{{node}}',instant=True)],
        color_mode="background",
        mappings=[{"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                  {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None},{"color":C_FL,"value":2}]}))
    y += 6

    # ── 3. SR-IOV ──────────────────────────────────────────
    panels.append(ts(
        "SR-IOV: Virtual Function Count",
        "sriov_vf_count (from sriov-network-operator metrics or SentinAI). "
        "0 VFs = SR-IOV not configured or VFs stuck in INIT.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'node_health_check_status{{{N}, check="day0_sriov_vf_status"}}','{{node}} SR-IOV')],
        axis="Status (0=OK)"))
    panels.append(ts(
        "SR-IOV: Network Interfaces (VFs)",
        "node_network_up for VF interfaces. 1 = link detected.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'node_network_up{{{I}, device=~".*vf.*|ens.*f[0-9].*"}}','{{instance}} {{device}}')],
        axis="Link Up (1=yes)"))
    panels.append(stat(
        "SR-IOV Check", "",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_health_check_status{{{N}, check="day0_sriov_vf_status"}}','{{node}}',instant=True)],
        color_mode="background",
        mappings=[{"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                  {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None},{"color":C_FL,"value":2}]}))
    y += 6

    # ── 4. KUBELET ─────────────────────────────────────────
    panels.append(ts(
        "Kubelet: Running Pods & Containers",
        "kubelet_running_pods and kubelet_running_containers. "
        "If both are 0 on a healthy node, kubelet may not be scheduling.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'kubelet_running_pods{{{I}}}','{{instance}} pods'),
         tgt(f'kubelet_running_containers{{{I}}}','{{instance}} containers')],
        axis="Count"))
    panels.append(ts(
        "Kubelet: Pod Start Duration (p99)",
        "kubelet_pod_start_duration_seconds — time from API admission to running. "
        "Spikes indicate scheduling or image pull bottlenecks.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'histogram_quantile(0.99, rate(kubelet_pod_start_duration_seconds_bucket{{{I}}}[5m]))','{{instance}} p99')],
        axis="Duration", unit="s"))
    panels.append(stat(
        "Kubelet Check", "",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_health_check_status{{{N}, check="kubelet_health"}}','{{node}}',instant=True)],
        color_mode="background",
        mappings=[{"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                  {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None},{"color":C_FL,"value":2}]}))
    y += 6

    # ── 5. CONTAINER RUNTIME ───────────────────────────────
    panels.append(ts(
        "Container Runtime: Operations/sec",
        "kubelet_runtime_operations_total rate — create, start, stop, remove. "
        "Flat line on a busy node = runtime frozen.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'sum by (operation_type) (rate(kubelet_runtime_operations_total{{{I}}}[5m]))','{{operation_type}}')],
        axis="Ops/s"))
    panels.append(ts(
        "Container Runtime: Error Rate",
        "kubelet_runtime_operations_errors_total rate. Spikes = runtime issues "
        "(image pull failures, OCI errors, device plugin failures).",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'sum by (operation_type) (rate(kubelet_runtime_operations_errors_total{{{I}}}[5m]))','{{operation_type}}')],
        axis="Errors/s"))
    panels.append(stat(
        "Container Runtime Check", "",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_health_check_status{{{N}, check="container_runtime_health"}}','{{node}}',instant=True)],
        color_mode="background",
        mappings=[{"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                  {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None},{"color":C_FL,"value":2}]}))
    y += 6

    # ── 6. BIOS / SYSTEM ──────────────────────────────────
    panels.append(ts(
        "System: Kernel & Boot Time",
        "node_boot_time_seconds — when node last booted. "
        "Recent boot after unexpected reboot = investigate MCE/panic.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'node_boot_time_seconds{{{I}}}','{{instance}}')],
        axis="Boot Timestamp", unit="dateTimeAsIso"))
    panels.append(ts(
        "System: HugePages Configuration",
        "node_memory_HugePages_Total / Free. "
        "HugePages = 0 means BIOS/kernel not configured for RDMA pinned memory.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'node_memory_HugePages_Total{{{I}}}','{{instance}} Total'),
         tgt(f'node_memory_HugePages_Free{{{I}}}','{{instance}} Free')],
        axis="Pages"))
    panels.append(stat(
        "BIOS Audit Check", "",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_health_check_status{{{N}, check="day0_bios_audit"}}','{{node}}',instant=True)],
        color_mode="background",
        mappings=[{"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                  {"type":"value","options":{"1":{"text":"WARN","color":C_WR}}},
                  {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None},{"color":C_WR,"value":1},{"color":C_FL,"value":2}]}))
    y += 6

    # ════════════════════════════════════════════════════════════════════
    # ██  DAY N — PER-COMPONENT RUNTIME PANELS  ██
    # ════════════════════════════════════════════════════════════════════
    panels.append(row("Day N — Critical Path Components (Runtime)", y)); y += 1

    # ── 1. GPU COMPUTE ─────────────────────────────────────
    panels.append(ts(
        "GPU Compute: Utilization",
        "DCGM_FI_DEV_GPU_UTIL — GPU engine utilization (0-100%). "
        "Under training load, expect 90-100%. Low util during job = straggler.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('DCGM_FI_DEV_GPU_UTIL','GPU {{gpu}}')],
        axis="Utilization", unit="percent"))
    panels.append(ts(
        "GPU Compute: SM Clock vs Max",
        "DCGM_FI_DEV_SM_CLOCK vs MAX. >10% delta = thermal/power throttle (Silent Killer).",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('DCGM_FI_DEV_SM_CLOCK','GPU {{gpu}} Current'),
         tgt('DCGM_FI_DEV_MAX_SM_CLOCK','GPU {{gpu}} Max')],
        axis="MHz"))
    panels.append(ts(
        "GPU Compute: Temperature",
        "DCGM_FI_DEV_GPU_TEMP. B200 liquid: max 70C. B200 air: max 83C. >90C = cordon.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('DCGM_FI_DEV_GPU_TEMP','GPU {{gpu}}')],
        axis="Temperature", unit="celsius"))
    panels.append(ts(
        "GPU Compute: Power Draw",
        "DCGM_FI_DEV_POWER_USAGE. B200 TDP = 1000W. Sustained near TDP = normal under load.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('DCGM_FI_DEV_POWER_USAGE','GPU {{gpu}}')],
        axis="Power", unit="watt"))
    y += 6

    # ── 2. GPU MEMORY (HBM) ───────────────────────────────
    panels.append(ts(
        "GPU Memory: Framebuffer Usage",
        "DCGM_FI_DEV_FB_USED / FREE. B200 = 192 GB HBM3e per GPU.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('DCGM_FI_DEV_FB_USED','GPU {{gpu}} Used'),
         tgt('DCGM_FI_DEV_FB_FREE','GPU {{gpu}} Free')],
        axis="Memory", unit="decmbytes"))
    panels.append(ts(
        "GPU Memory: ECC Errors",
        "DBE (double-bit) = P0 CRITICAL, immediate cordon. SBE = monitor trend.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('DCGM_FI_DEV_ECC_DBE_VOL_TOTAL','GPU {{gpu}} DBE'),
         tgt('DCGM_FI_DEV_ECC_SBE_VOL_TOTAL','GPU {{gpu}} SBE')],
        axis="Errors",
        overrides=[
            {"matcher":{"id":"byRegexp","options":".*DBE.*"},"properties":[{"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]},
            {"matcher":{"id":"byRegexp","options":".*SBE.*"},"properties":[{"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]}]))
    panels.append(ts(
        "GPU Memory: Retired Pages",
        "DCGM_FI_DEV_RETIRED_SBE/DBE. SBE < 60 = OK. DBE must be 0. "
        "Rising SBE = HBM degradation trend.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('DCGM_FI_DEV_RETIRED_SBE','GPU {{gpu}} Retired SBE'),
         tgt('DCGM_FI_DEV_RETIRED_DBE','GPU {{gpu}} Retired DBE')],
        axis="Retired Pages",
        overrides=[
            {"matcher":{"id":"byRegexp","options":".*DBE.*"},"properties":[{"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]}]))
    panels.append(ts(
        "GPU Memory: Row Remap",
        "DCGM_FI_DEV_ROW_REMAP_FAILURE. Must be 0. >0 = HBM bank unrepairable.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('DCGM_FI_DEV_ROW_REMAP_FAILURE','GPU {{gpu}} Remap Fail'),
         tgt('DCGM_FI_DEV_ROW_REMAP_PENDING','GPU {{gpu}} Remap Pending')],
        axis="Count"))
    y += 6

    # ── 3. XID ERRORS ──────────────────────────────────────
    panels.append(ts(
        "XID Error Timeline",
        "DCGM_FI_DEV_XID_ERRORS — every GPU error on a single time axis. "
        "Critical: 48 (ECC DBE), 79 (off bus), 74 (NVLink), 61-64, 94-95.",
        {"h":6,"w":24,"x":0,"y":y},
        [tgt('DCGM_FI_DEV_XID_ERRORS','GPU {{gpu}} XID')],
        axis="XID Count"))
    y += 6

    # ── 4. NVLink ──────────────────────────────────────────
    panels.append(ts(
        "NVLink: CRC Flit Errors",
        "DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL. Low-level link noise. "
        "Sustained increase = cable/connector degradation.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL','GPU {{gpu}}')],
        axis="CRC Errors"))
    panels.append(ts(
        "NVLink: Replay Errors",
        "DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL. Re-transmissions. "
        "Small counts = noise. Sustained = NVLink degradation.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL','GPU {{gpu}}')],
        axis="Replay Errors"))
    panels.append(ts(
        "NVLink: Recovery Errors",
        "DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL. >0 = link went down and recovered. "
        "P0 signal — link unreliable, potential NVLink fabric failure (XID 74).",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL','GPU {{gpu}}')],
        axis="Recovery Errors"))
    y += 6

    # ── 5. PCIe ────────────────────────────────────────────
    panels.append(ts(
        "PCIe: Link Generation",
        "DCGM_FI_DEV_PCIE_LINK_GEN. Expected: 5 (Gen5). "
        "Gen4 = 50% BW loss. Gen3 = 75% loss. Silent performance killer.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('DCGM_FI_DEV_PCIE_LINK_GEN','GPU {{gpu}}')],
        axis="PCIe Gen"))
    panels.append(ts(
        "PCIe: Link Width",
        "DCGM_FI_DEV_PCIE_LINK_WIDTH. Expected: 16 (x16). "
        "x8 = 50% BW loss. x4 = 75% loss.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('DCGM_FI_DEV_PCIE_LINK_WIDTH','GPU {{gpu}}')],
        axis="Width"))
    panels.append(ts(
        "PCIe: Replay Counter",
        "DCGM_FI_DEV_PCIE_REPLAY_COUNTER. Re-transmissions. "
        "Rising count = PCIe signal quality degradation.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('DCGM_FI_DEV_PCIE_REPLAY_COUNTER','GPU {{gpu}}')],
        axis="Replays"))
    y += 6

    # ── 6. POWER & THERMAL VIOLATIONS ──────────────────────
    panels.append(ts(
        "Thermal Violation Duration",
        "DCGM_FI_DEV_THERMAL_VIOLATION in microseconds. "
        "Any value > 0 = GPU clocks were throttled due to temperature.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt('DCGM_FI_DEV_THERMAL_VIOLATION','GPU {{gpu}}')],
        axis="Duration (us)"))
    panels.append(ts(
        "Power Violation Duration",
        "DCGM_FI_DEV_POWER_VIOLATION in microseconds. "
        "Any value > 0 = GPU clocks throttled due to power cap.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt('DCGM_FI_DEV_POWER_VIOLATION','GPU {{gpu}}')],
        axis="Duration (us)"))
    y += 6

    # ── 7. INFINIBAND / RDMA ───────────────────────────────
    panels.append(ts(
        "InfiniBand: Data Transmitted",
        "node_infiniband_port_data_transmitted_bytes_total rate. "
        "Should be roughly equal across all HCA ports. Silent port = straggler.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'rate(node_infiniband_port_data_transmitted_bytes_total{{{I}}}[5m])','{{device}} p{{port}} TX')],
        axis="TX Bytes/s", unit="Bps"))
    panels.append(ts(
        "InfiniBand: Data Received",
        "node_infiniband_port_data_received_bytes_total rate.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'rate(node_infiniband_port_data_received_bytes_total{{{I}}}[5m])','{{device}} p{{port}} RX')],
        axis="RX Bytes/s", unit="Bps"))
    panels.append(ts(
        "InfiniBand: Port Errors",
        "node_infiniband error counters: symbol, link_downed, rcv_errors.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'rate(node_infiniband_port_receive_errors_total{{{I}}}[5m])','{{device}} RcvErr'),
         tgt(f'rate(node_infiniband_link_downed_total{{{I}}}[5m])','{{device}} LinkDown'),
         tgt(f'rate(node_infiniband_symbol_error_total{{{I}}}[5m])','{{device}} SymbolErr')],
        axis="Errors/s"))
    y += 6

    # ── 8. CPU ─────────────────────────────────────────────
    panels.append(ts(
        "CPU: Utilization",
        "1 - avg(rate(node_cpu_seconds_total{mode='idle'})) — CPU busy percentage.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'1 - avg by (instance) (rate(node_cpu_seconds_total{{{I}, mode="idle"}}[5m]))','{{instance}}')],
        axis="Utilization", unit="percentunit"))
    panels.append(ts(
        "CPU: Load Average",
        "node_load1 / node_load5 / node_load15 relative to CPU count.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'node_load1{{{I}}}','1min'),
         tgt(f'node_load5{{{I}}}','5min'),
         tgt(f'node_load15{{{I}}}','15min')],
        axis="Load Average"))
    panels.append(ts(
        "CPU: Temperature",
        "node_hwmon_temp_celsius or node_thermal_zone_temp. CPU overheating = MCE risk.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_hwmon_temp_celsius{{{I}, chip=~".*coretemp.*"}}','{{chip}} {{sensor}}'),
         tgt(f'node_thermal_zone_temp{{{I}}}','Zone {{zone}} {{type}}')],
        axis="Temperature", unit="celsius"))
    y += 6

    # ── 9. SYSTEM MEMORY ───────────────────────────────────
    panels.append(ts(
        "Memory: Usage",
        "1 - (MemAvailable / MemTotal). System memory utilization. "
        ">95% = OOM risk, container eviction.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'1 - node_memory_MemAvailable_bytes{{{I}}} / node_memory_MemTotal_bytes{{{I}}}','{{instance}}')],
        axis="Usage", unit="percentunit"))
    panels.append(ts(
        "Memory: ECC Errors (EDAC)",
        "node_edac_correctable/uncorrectable_errors_total. "
        "Uncorrectable > 0 = DIMM failure, immediate cordon.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'node_edac_correctable_errors_total{{{I}}}','{{instance}} CE'),
         tgt(f'node_edac_uncorrectable_errors_total{{{I}}}','{{instance}} UE')],
        axis="ECC Errors",
        overrides=[
            {"matcher":{"id":"byRegexp","options":".*UE.*"},"properties":[{"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}}]},
            {"matcher":{"id":"byRegexp","options":".*CE.*"},"properties":[{"id":"color","value":{"fixedColor":C_WR,"mode":"fixed"}}]}]))
    panels.append(ts(
        "Memory: Available",
        "node_memory_MemAvailable_bytes — actual available memory.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'node_memory_MemAvailable_bytes{{{I}}}','{{instance}}')],
        axis="Available", unit="bytes"))
    y += 6

    # ── 10. STORAGE ────────────────────────────────────────
    panels.append(ts(
        "Storage: Filesystem Usage",
        "node_filesystem_avail_bytes / size. Critical mounts: /, /var, /var/lib/kubelet.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt(f'1 - node_filesystem_avail_bytes{{{I}, mountpoint=~"/|/var|/var/lib/kubelet"}} / node_filesystem_size_bytes{{{I}, mountpoint=~"/|/var|/var/lib/kubelet"}}','{{instance}} {{mountpoint}}')],
        axis="Usage", unit="percentunit"))
    panels.append(ts(
        "Storage: Disk I/O",
        "node_disk_io_time_seconds_total rate — disk busy time. "
        "Sustained 100% = I/O bottleneck.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt(f'rate(node_disk_io_time_seconds_total{{{I}}}[5m])','{{instance}} {{device}}')],
        axis="IO Time", unit="percentunit"))
    panels.append(ts(
        "Storage: Read/Write Throughput",
        "node_disk_read/written_bytes_total rate.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt(f'rate(node_disk_read_bytes_total{{{I}}}[5m])','{{instance}} {{device}} Read'),
         tgt(f'rate(node_disk_written_bytes_total{{{I}}}[5m])','{{instance}} {{device}} Write')],
        axis="Throughput", unit="Bps"))
    y += 6

    # ── 11. K8S NODE CONDITIONS ────────────────────────────
    panels.append(ts(
        "K8s: Node Conditions",
        "kube_node_status_condition — MemoryPressure, DiskPressure, PIDPressure, Ready. "
        "Ready=0 or any Pressure=1 = critical.",
        {"h":6,"w":12,"x":0,"y":y},
        [tgt(f'kube_node_status_condition{{node=~"$node", status="true", condition=~"Ready|MemoryPressure|DiskPressure|PIDPressure"}}','{{node}} {{condition}}')],
        axis="Condition (1=true)"))
    panels.append(ts(
        "K8s: Node Allocatable vs Capacity",
        "kube_node_status_allocatable vs capacity for ephemeral-storage and pods. "
        "Large gap = high system reserved.",
        {"h":6,"w":12,"x":12,"y":y},
        [tgt(f'kube_node_status_allocatable{{node=~"$node", resource="pods"}}','{{node}} Allocatable Pods'),
         tgt(f'kube_node_status_capacity{{node=~"$node", resource="pods"}}','{{node}} Capacity Pods')],
        axis="Resources"))
    y += 6

    # ════════════════════════════════════════════════════════
    # WORKLOAD-TYPE CRITICAL PATH TABLES
    # ════════════════════════════════════════════════════════
    panels.append(row("Workload Critical Path — Day 0 Provisioning Gate", y)); y += 1

    WK = {"notebook":{"label":"Notebook (Single GPU)",
        "day0":["day0_gpu_operator","day0_driver_version","kubelet_health","container_runtime_health"]},
      "single_node":{"label":"Single-Node Job (Multi-GPU)",
        "day0":["day0_gpu_operator","day0_driver_version","day0_bios_audit","kubelet_health","container_runtime_health"]},
      "multi_node":{"label":"Multi-Node (Distributed)",
        "day0":["day0_gpu_operator","day0_network_operator","day0_sriov_vf_status","day0_driver_version","day0_bios_audit","kubelet_health","container_runtime_health"]}}

    for i,(k,v) in enumerate(WK.items()):
        re = "("+"|".join(v["day0"])+")"
        panels.append(tbl(f"Day 0: {v['label']}","",{"h":8,"w":8,"x":i*8,"y":y},
            [tgt(f'node_health_check_status{{{N}, check=~"{re}"}}','',fmt="table")],
            transforms=[ORGANIZE_T], overrides=CHECK_STATUS_OVERRIDES,
            sort=[{"displayName":"Status","desc":True}]))
    y += 8

    panels.append(row("Workload Critical Path — Day N Runtime Health", y)); y += 1

    WKN = {"notebook":{"label":"Notebook (Single GPU)",
        "dayn":["gpu_dcgm_overall_health","gpu_ecc_errors","gpu_xid_errors","gpu_temperature",
                "gpu_memory_utilization","memory_pressure","filesystem_pressure",
                "kubelet_health","container_runtime_health","node_pressure_conditions"]},
      "single_node":{"label":"Single-Node (Multi-GPU)",
        "dayn":["gpu_dcgm_overall_health","gpu_ecc_errors","gpu_xid_errors","gpu_temperature",
                "gpu_nvlink_health","gpu_pcie_health","gpu_power_violation","gpu_memory_utilization",
                "gpu_row_remapping","gpu_topology_check","nvswitch_health",
                "day1_pcie_training","day1_gpu_clock_throttle",
                "multi_node_nccl_allreduce","multi_node_nvbandwidth",
                "cpu_mce_errors","memory_pressure","filesystem_pressure",
                "kubelet_health","container_runtime_health","node_pressure_conditions"]},
      "multi_node":{"label":"Multi-Node (Distributed)",
        "dayn":["gpu_dcgm_overall_health","gpu_ecc_errors","gpu_xid_errors","gpu_temperature",
                "gpu_nvlink_health","gpu_pcie_health","gpu_power_violation","gpu_memory_utilization",
                "gpu_row_remapping","gpu_topology_check","nvswitch_health",
                "day1_pcie_training","day1_gpu_clock_throttle",
                "day1_ib_link_flapping","day1_hca_fault","day1_subnet_manager",
                "multi_node_nccl_allreduce","multi_node_nvbandwidth",
                "infiniband_multi_port","infiniband_error_counters",
                "fabric_lid_assignment","fabric_mtu_parity","fabric_hca_traffic_balance","fabric_ib_bandwidth",
                "cpu_mce_errors","memory_pressure","filesystem_pressure",
                "nic_link_health","infiniband_health",
                "kubelet_health","container_runtime_health","node_pressure_conditions"]}}

    for i,(k,v) in enumerate(WKN.items()):
        re = "("+"|".join(v["dayn"])+")"
        panels.append(tbl(f"Day N: {v['label']}","",{"h":12,"w":8,"x":i*8,"y":y},
            [tgt(f'node_health_check_status{{{N}, check=~"{re}"}}','',fmt="table")],
            transforms=[ORGANIZE_T], overrides=CHECK_STATUS_OVERRIDES,
            sort=[{"displayName":"Status","desc":True}]))
    y += 12

    # ════════════════════════════════════════════════════════
    # ALL CHECKS TABLE
    # ════════════════════════════════════════════════════════
    panels.append(row("All Checks — Full Detail", y)); y += 1
    panels.append(tbl(
        "All Checks","Every registered check with status, severity, component.",
        {"h":12,"w":24,"x":0,"y":y},
        [tgt(f'node_health_check_status{{{N}}}','',fmt="table")],
        transforms=[ORGANIZE_T],
        overrides=CHECK_STATUS_OVERRIDES + [
            {"matcher":{"id":"byName","options":"Comp"},"properties":[{"id":"custom.width","value":100}]},
            {"matcher":{"id":"byName","options":"Sev"},"properties":[{"id":"custom.width","value":60}]}],
        sort=[{"displayName":"Status","desc":True}]))
    y += 12

    # ════════════════════════════════════════════════════════
    # SEVERITY + CORDON
    # ════════════════════════════════════════════════════════
    panels.append(row("Severity & Cordon", y)); y += 1

    for i,(sv,lbl,c) in enumerate([("0","P0 Critical",C_P0),("1","P1 High",C_P1),
                                    ("2","P2 Medium",C_P2),("3","P3 Low",C_P3)]):
        panels.append(stat(lbl,"",{"h":3,"w":6,"x":i*6,"y":y},
            [tgt(f'count(node_health_check_status{{{N}, severity="{sv}"}} > 0) or vector(0)',lbl,instant=True)],
            color_mode="value",
            thresholds={"mode":"absolute","steps":[{"color":c,"value":None}]}))
    y += 3

    panels.append(ts("Cordon Signal","1 = cordon recommended.",{"h":6,"w":12,"x":0,"y":y},
        [tgt(f'node_health_should_cordon{{{N}}}','{{node}}')],
        axis="Cordon",
        overrides=[{"matcher":{"id":"byFrameRefID","options":"A"},"properties":[
            {"id":"color","value":{"fixedColor":C_FL,"mode":"fixed"}},
            {"id":"custom.fillOpacity","value":30}]}]))
    panels.append(ts("Failing by Severity","",{"h":6,"w":12,"x":12,"y":y},
        [tgt(f'count by (severity) (node_health_check_status{{{N}}} >= 1)','{{severity}}')],
        axis="Count",
        overrides=[
            {"matcher":{"id":"byName","options":"0"},"properties":[{"id":"displayName","value":"P0"},{"id":"color","value":{"fixedColor":C_P0,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"1"},"properties":[{"id":"displayName","value":"P1"},{"id":"color","value":{"fixedColor":C_P1,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"2"},"properties":[{"id":"displayName","value":"P2"},{"id":"color","value":{"fixedColor":C_P2,"mode":"fixed"}}]},
            {"matcher":{"id":"byName","options":"3"},"properties":[{"id":"displayName","value":"P3"},{"id":"color","value":{"fixedColor":C_P3,"mode":"fixed"}}]}]))
    y += 6

    panels.append(stat("Last Check","",{"h":3,"w":6,"x":0,"y":y},
        [tgt(f'node_health_last_check_timestamp_seconds{{{N}}}','{{node}}',instant=True)],
        unit="dateTimeFromNow",color_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))
    panels.append(stat("Freshness","Seconds since last check.",{"h":3,"w":6,"x":6,"y":y},
        [tgt(f'time() - node_health_last_check_timestamp_seconds{{{N}}}','{{node}}',instant=True)],
        unit="s",color_mode="background",
        thresholds={"mode":"absolute","steps":[{"color":C_OK,"value":None},{"color":C_WR,"value":120},{"color":C_FL,"value":300}]}))
    panels.append(stat("Health","",{"h":3,"w":6,"x":12,"y":y},
        [tgt(f'node_health_node_healthy{{{N}}}','{{node}}',instant=True)],
        color_mode="background",graph_mode="area",
        mappings=[{"type":"value","options":{"0":{"text":"UNHEALTHY","color":C_FL}}},
                  {"type":"value","options":{"1":{"text":"HEALTHY","color":C_OK}}}],
        thresholds={"mode":"absolute","steps":[{"color":C_FL,"value":None},{"color":C_OK,"value":1}]}))
    y += 3

    # ════════════════════════════════════════════════════════
    templating = {"list":[
        {"name":"datasource","type":"datasource","label":"Prometheus",
         "query":"prometheus","current":{},"hide":0,
         "includeAll":False,"multi":False,"options":[],"refresh":1,"regex":"","skipUrlSync":False},
        {"name":"node","type":"query","label":"Node","datasource":ds(),
         "definition":"label_values(node_health_node_healthy, node)",
         "query":{"query":"label_values(node_health_node_healthy, node)","refId":"n"},
         "current":{},"hide":0,"includeAll":True,"multi":True,
         "options":[],"refresh":2,"regex":"","sort":1,"skipUrlSync":False}]}

    return {
        "__inputs":[],"__requires":[
            {"type":"grafana","id":"grafana","name":"Grafana","version":"9.0.0"},
            {"type":"datasource","id":"prometheus","name":"Prometheus","version":"1.0.0"}],
        "id":None,"uid":"sentinai-node-health-v4",
        "title":"SentinAI — Node Health Detector",
        "description":"Fleet health, per-component Day 0/Day N panels with DCGM, node_exporter, "
                      "kubelet, kube-state-metrics. Workload critical path tables.",
        "tags":["sentinai","node-health","gpu","dcgm","fleet","kubernetes","day0","dayn"],
        "style":"dark","timezone":"browser","editable":True,
        "graphTooltip":1,"fiscalYearStartMonth":0,"liveNow":False,
        "refresh":"30s","schemaVersion":38,"version":4,
        "time":{"from":"now-6h","to":"now"},"timepicker":{},
        "annotations":{"list":[{"builtIn":1,"datasource":{"type":"grafana","uid":"-- Grafana --"},
            "enable":True,"hide":True,"iconColor":"rgba(0, 211, 255, 1)",
            "name":"Annotations & Alerts","type":"dashboard"}]},
        "templating":templating, "panels":panels}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "node-health-dashboard.json"
    d = build()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    pc = len(d["panels"])
    vc = len(d["templating"]["list"])
    print(f"Generated {out}: {pc} panels, {vc} template variables")
    for p in d["panels"]:
        t = p.get("type","")
        print(f"  [{t:14s}] {p.get('title', '')}")
