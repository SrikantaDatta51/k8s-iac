#!/usr/bin/env python3
"""Generate SentinAI Node Health Detector Grafana Dashboard — v3.
Professional quality — no emojis, clear legends, proper units.

Key features:
  - Fleet health score (top row)
  - Fleet heatmap (node × component status grid)
  - Workload type variable: Notebook / Single Node / Multi Node
  - Day 0 + Day 2 panels with critical path per workload type
  - DCGM exporter metrics integration
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

LEGEND = {"displayMode": "table", "placement": "right",
          "calcs": ["lastNotNull"]}
LEGEND_FULL = {"displayMode": "table", "placement": "right",
               "calcs": ["min", "max", "mean", "lastNotNull"]}

# Color palette (professional, muted)
C_PASS   = "#56A64B"
C_WARN   = "#E0A939"
C_FAIL   = "#C04040"
C_UNK    = "#8F8F8F"
C_P0     = "#C04040"
C_P1     = "#E0663E"
C_P2     = "#E0A939"
C_P3     = "#7EB26D"
C_BLUE   = "#3274D9"
C_PURPLE = "#8F3BB8"
C_TEAL   = "#6ED0E0"
C_ORANGE = "#EF843C"

N = 'node=~"$node"'

# ────────────────────────────────────────────────────────────
# WORKLOAD TYPE → CRITICAL PATH COMPONENTS
# Each workload type has its own set of Day 0 and Day 2 checks
# ────────────────────────────────────────────────────────────
WORKLOAD_CRITICAL_PATHS = {
    "notebook": {
        "label": "Notebook (Single GPU)",
        "day0": [
            "day0_gpu_operator", "day0_driver_version",
            "kubelet_health", "container_runtime_health",
        ],
        "day2": [
            "gpu_dcgm_overall_health", "gpu_ecc_errors", "gpu_xid_errors",
            "gpu_temperature", "gpu_memory_utilization",
            "memory_pressure", "filesystem_pressure",
            "kubelet_health", "container_runtime_health",
            "node_pressure_conditions",
        ],
        "description": "Single GPU workstation. Critical path: GPU driver + kubelet + runtime."
    },
    "single_node": {
        "label": "Single-Node Job (Multi-GPU)",
        "day0": [
            "day0_gpu_operator", "day0_driver_version", "day0_bios_audit",
            "kubelet_health", "container_runtime_health",
        ],
        "day2": [
            "gpu_dcgm_overall_health", "gpu_ecc_errors", "gpu_xid_errors",
            "gpu_temperature", "gpu_nvlink_health", "gpu_pcie_health",
            "gpu_power_violation", "gpu_memory_utilization", "gpu_row_remapping",
            "gpu_topology_check", "nvswitch_health",
            "day1_pcie_training", "day1_gpu_clock_throttle",
            "multi_node_nccl_allreduce", "multi_node_nvbandwidth",
            "cpu_mce_errors", "memory_pressure", "filesystem_pressure",
            "kubelet_health", "container_runtime_health",
            "node_pressure_conditions",
        ],
        "description": "Multi-GPU single node. Critical path: GPU + NVLink + NVSwitch + NCCL intra-node."
    },
    "multi_node": {
        "label": "Multi-Node Job (Distributed Training)",
        "day0": [
            "day0_gpu_operator", "day0_network_operator",
            "day0_sriov_vf_status", "day0_driver_version", "day0_bios_audit",
            "kubelet_health", "container_runtime_health",
        ],
        "day2": [
            "gpu_dcgm_overall_health", "gpu_ecc_errors", "gpu_xid_errors",
            "gpu_temperature", "gpu_nvlink_health", "gpu_pcie_health",
            "gpu_power_violation", "gpu_memory_utilization", "gpu_row_remapping",
            "gpu_topology_check", "nvswitch_health",
            "day1_pcie_training", "day1_gpu_clock_throttle",
            "day1_ib_link_flapping", "day1_hca_fault", "day1_subnet_manager",
            "multi_node_nccl_allreduce", "multi_node_nvbandwidth",
            "infiniband_multi_port", "infiniband_error_counters",
            "fabric_lid_assignment", "fabric_mtu_parity",
            "fabric_hca_traffic_balance", "fabric_ib_bandwidth",
            "cpu_mce_errors", "memory_pressure", "filesystem_pressure",
            "nic_link_health", "infiniband_health",
            "kubelet_health", "container_runtime_health",
            "node_pressure_conditions",
        ],
        "description": "Multi-node distributed training. Critical path: ALL — GPU + NVLink + IB + SR-IOV + Fabric + NCCL inter-node."
    },
}


def row(title, y, collapsed=False):
    return {"type": "row", "title": title, "collapsed": collapsed,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}

def stat(title, desc, gp, targets, unit="none", decimals=0,
         thresholds=None, color_mode="background", text_mode="auto",
         graph_mode="none", mappings=None):
    return {
        "id": nid(), "title": title, "description": desc, "type": "stat",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals,
            "thresholds": thresholds or {"mode": "absolute", "steps": [
                {"color": C_PASS, "value": None}]},
            "mappings": mappings or [],
            "noValue": "N/A"}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "auto", "textMode": text_mode,
            "colorMode": color_mode, "graphMode": graph_mode, "justifyMode": "center"},
        "targets": refs(targets)
    }

def ts(title, desc, gp, targets, axis, unit="short", overrides=None, stacking=None):
    custom = {"lineWidth": 2, "fillOpacity": 10, "gradientMode": "none",
              "axisLabel": axis, "drawStyle": "line", "pointSize": 4,
              "showPoints": "never", "spanNulls": True}
    if stacking:
        custom["stacking"] = {"mode": stacking}
        custom["fillOpacity"] = 60
        custom["lineWidth"] = 0
    return {
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "custom": custom},
            "overrides": overrides or []},
        "options": {"legend": LEGEND_FULL, "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs(targets)
    }

def tbl(title, desc, gp, targets, transforms=None, overrides=None, sort=None):
    return {
        "id": nid(), "title": title, "description": desc, "type": "table",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": overrides or []},
        "options": {"showHeader": True, "sortBy": sort or []},
        "transformations": transforms or [],
        "targets": refs(targets)
    }

def gauge(title, desc, gp, targets, unit="percentunit", thresholds=None):
    return {
        "id": nid(), "title": title, "description": desc, "type": "gauge",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 1,
            "thresholds": thresholds or {"mode": "absolute", "steps": [
                {"color": C_FAIL, "value": None},
                {"color": C_WARN, "value": 0.5},
                {"color": C_PASS, "value": 0.8}]},
            "min": 0, "max": 1}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
                    "showThresholdLabels": False, "showThresholdMarkers": True},
        "targets": refs(targets)
    }

def heatmap(title, desc, gp, targets):
    """Status heatmap — uses Grafana's state timeline panel for node×check grid."""
    return {
        "id": nid(), "title": title, "description": desc,
        "type": "state-timeline",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {
            "custom": {"lineWidth": 0, "fillOpacity": 80},
            "thresholds": {"mode": "absolute", "steps": [
                {"color": C_PASS, "value": None},
                {"color": C_WARN, "value": 1},
                {"color": C_FAIL, "value": 2},
                {"color": C_UNK, "value": 3}]},
            "mappings": [
                {"type": "value", "options": {"0": {"text": "PASS", "color": C_PASS}}},
                {"type": "value", "options": {"1": {"text": "WARN", "color": C_WARN}}},
                {"type": "value", "options": {"2": {"text": "FAIL", "color": C_FAIL}}},
                {"type": "value", "options": {"3": {"text": "UNKNOWN", "color": C_UNK}}},
            ]}, "overrides": []},
        "options": {"showValue": "auto", "mergeValues": True,
                    "alignValue": "center", "rowHeight": 0.85,
                    "tooltip": {"mode": "multi"},
                    "legend": {"displayMode": "list", "placement": "bottom"}},
        "targets": refs(targets)
    }


def _check_regex(check_list):
    """Build '(check1|check2|...)' regex from a list of check names."""
    return "(" + "|".join(check_list) + ")"


def build():
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # TOP ROW: FLEET HEALTH SCORE
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet Health Score", y)); y += 1

    # Overall fleet health score — percentage of healthy nodes
    panels.append(gauge(
        "Fleet Health Score",
        "Percentage of nodes reporting healthy across the fleet. "
        "1.0 = all nodes healthy. Watch for drops below 0.8.",
        {"h": 6, "w": 6, "x": 0, "y": y},
        [tgt('avg(node_health_node_healthy) or vector(0)', "Fleet Health", instant=True)],
    ))

    # Total nodes healthy / total
    panels.append(stat(
        "Healthy Nodes",
        "Count of nodes with all checks passing",
        {"h": 3, "w": 3, "x": 6, "y": y},
        [tgt('count(node_health_node_healthy == 1) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": C_PASS, "value": None}]}
    ))

    panels.append(stat(
        "Unhealthy Nodes",
        "Count of nodes with one or more failing checks",
        {"h": 3, "w": 3, "x": 9, "y": y},
        [tgt('count(node_health_node_healthy == 0) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [
            {"color": C_PASS, "value": None}, {"color": C_FAIL, "value": 1}]}
    ))

    panels.append(stat(
        "Cordoned Nodes",
        "Nodes where SentinAI recommends cordon",
        {"h": 3, "w": 3, "x": 6, "y": y + 3},
        [tgt('count(node_health_should_cordon == 1) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [
            {"color": C_PASS, "value": None}, {"color": C_FAIL, "value": 1}]}
    ))

    panels.append(stat(
        "Total Nodes",
        "Total nodes monitored by SentinAI",
        {"h": 3, "w": 3, "x": 9, "y": y + 3},
        [tgt('count(node_health_node_healthy) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": C_BLUE, "value": None}]}
    ))

    # Fleet checks summary
    panels.append(stat(
        "Fleet Checks Passing",
        "Total passing checks across all nodes",
        {"h": 3, "w": 3, "x": 12, "y": y},
        [tgt('sum(node_health_passed) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": C_PASS, "value": None}]}
    ))

    panels.append(stat(
        "Fleet Checks Warned",
        "Total warned checks across all nodes",
        {"h": 3, "w": 3, "x": 15, "y": y},
        [tgt('sum(node_health_warned) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [
            {"color": C_PASS, "value": None}, {"color": C_WARN, "value": 1}]}
    ))

    panels.append(stat(
        "Fleet Checks Failed",
        "Total failed checks across all nodes",
        {"h": 3, "w": 3, "x": 12, "y": y + 3},
        [tgt('sum(node_health_failed) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [
            {"color": C_PASS, "value": None}, {"color": C_FAIL, "value": 1}]}
    ))

    panels.append(stat(
        "Fleet Total Checks",
        "Total checks executed across all nodes",
        {"h": 3, "w": 3, "x": 15, "y": y + 3},
        [tgt('sum(node_health_checks_run) or vector(0)', "", instant=True)],
        color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": C_BLUE, "value": None}]}
    ))

    # Per-component fleet score
    components = ["gpu", "cpu", "memory", "storage", "network", "kubernetes"]
    for i, comp in enumerate(components):
        x = 18 + (i % 2) * 3
        yy = y + (i // 2) * 2
        panels.append(stat(
            comp.upper(), f"Worst status for {comp} across fleet",
            {"h": 2, "w": 3, "x": x, "y": yy},
            [tgt(f'max(node_health_component_status{{component="{comp}"}}) or vector(-1)',
                 "", instant=True)],
            color_mode="background",
            mappings=[
                {"type": "value", "options": {"-1": {"text": "N/A", "color": C_UNK}}},
                {"type": "value", "options": {"0": {"text": "PASS", "color": C_PASS}}},
                {"type": "value", "options": {"1": {"text": "WARN", "color": C_WARN}}},
                {"type": "value", "options": {"2": {"text": "FAIL", "color": C_FAIL}}},
            ],
            thresholds={"mode": "absolute", "steps": [
                {"color": C_PASS, "value": None}, {"color": C_WARN, "value": 1},
                {"color": C_FAIL, "value": 2}]}
        ))
    y += 6

    # Fleet health over time
    panels.append(ts(
        "Fleet Health Score Over Time",
        "Percentage of healthy nodes over time. 1.0 = all healthy.",
        {"h": 6, "w": 12, "x": 0, "y": y},
        [tgt('avg(node_health_node_healthy)', "Fleet Health Score"),
         tgt('count(node_health_node_healthy == 0) / count(node_health_node_healthy)',
             "Unhealthy Ratio")],
        axis="Score (0-1)", unit="percentunit",
        overrides=[
            {"matcher": {"id": "byName", "options": "Fleet Health Score"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_PASS, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "Unhealthy Ratio"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
        ]
    ))

    panels.append(ts(
        "Nodes by Health Status Over Time",
        "Stacked area: healthy vs unhealthy vs cordoned nodes.",
        {"h": 6, "w": 12, "x": 12, "y": y},
        [tgt('count(node_health_node_healthy == 1) or vector(0)', "Healthy"),
         tgt('count(node_health_node_healthy == 0) or vector(0)', "Unhealthy"),
         tgt('count(node_health_should_cordon == 1) or vector(0)', "Cordoned")],
        axis="Nodes", stacking="normal",
        overrides=[
            {"matcher": {"id": "byName", "options": "Healthy"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_PASS, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "Unhealthy"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "Cordoned"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_P1, "mode": "fixed"}}]},
        ]
    ))
    y += 6

    # ════════════════════════════════════════════════════════
    # FLEET HEATMAP — Node × Component Status Grid
    # ════════════════════════════════════════════════════════
    panels.append(row("Fleet Heatmap — Node Health Grid", y)); y += 1

    # Node × Component status heatmap
    panels.append(heatmap(
        "Node x Component Status (Fleet View)",
        "Each row = one node, each segment = component worst status. "
        "Green = PASS, Amber = WARN, Red = FAIL. Scan for red blocks.",
        {"h": 12, "w": 24, "x": 0, "y": y},
        [tgt(f'node_health_component_status', "{{node}} / {{component}}")]
    ))
    y += 12

    # Individual check heatmap — per node
    panels.append(heatmap(
        "Node x Check Status (Selected Nodes)",
        "Per-check status for selected nodes. Each row = one check on one node. "
        "Use this to drill into specific node failures.",
        {"h": 12, "w": 24, "x": 0, "y": y},
        [tgt(f'node_health_check_status{{{N}}}', "{{node}} / {{check}}")]
    ))
    y += 12

    # ════════════════════════════════════════════════════════
    # PER-NODE OVERVIEW (filtered by $node)
    # ════════════════════════════════════════════════════════
    panels.append(row("Selected Node — Health Overview", y)); y += 1

    panels.append(stat(
        "Node Health", "1 = healthy, 0 = unhealthy",
        {"h": 4, "w": 4, "x": 0, "y": y},
        [tgt(f'node_health_node_healthy{{{N}}}', "{{node}}", instant=True)],
        color_mode="background",
        mappings=[
            {"type": "value", "options": {"0": {"text": "UNHEALTHY", "color": C_FAIL}}},
            {"type": "value", "options": {"1": {"text": "HEALTHY", "color": C_PASS}}},
        ],
        thresholds={"mode": "absolute", "steps": [
            {"color": C_FAIL, "value": None}, {"color": C_PASS, "value": 1}]}
    ))

    panels.append(stat(
        "Cordon Signal", "Whether the detector recommends cordoning",
        {"h": 4, "w": 4, "x": 4, "y": y},
        [tgt(f'node_health_should_cordon{{{N}}}', "{{node}}", instant=True)],
        color_mode="background",
        mappings=[
            {"type": "value", "options": {"0": {"text": "NO CORDON", "color": C_PASS}}},
            {"type": "value", "options": {"1": {"text": "CORDON NEEDED", "color": C_FAIL}}},
        ],
        thresholds={"mode": "absolute", "steps": [
            {"color": C_PASS, "value": None}, {"color": C_FAIL, "value": 1}]}
    ))

    for i, (label, metric, color) in enumerate([
        ("Passed", "passed", C_PASS), ("Warned", "warned", C_WARN),
        ("Failed", "failed", C_FAIL), ("Total", "checks_run", C_BLUE),
    ]):
        panels.append(stat(
            label, f"Checks {label.lower()}",
            {"h": 4, "w": 4, "x": 8 + i * 4, "y": y},
            [tgt(f'node_health_{metric}{{{N}}}', "{{node}}", instant=True)],
            color_mode="value", text_mode="value",
            thresholds={"mode": "absolute", "steps": [{"color": color, "value": None}]}
        ))
    y += 4

    # Component status for selected node
    for i, comp in enumerate(components):
        panels.append(stat(
            comp.upper(), f"Worst {comp} check",
            {"h": 3, "w": 4, "x": i * 4, "y": y},
            [tgt(f'node_health_component_status{{{N}, component="{comp}"}}', "", instant=True)],
            color_mode="background",
            mappings=[
                {"type": "value", "options": {"0": {"text": "PASS", "color": C_PASS}}},
                {"type": "value", "options": {"1": {"text": "WARN", "color": C_WARN}}},
                {"type": "value", "options": {"2": {"text": "FAIL", "color": C_FAIL}}},
                {"type": "value", "options": {"3": {"text": "UNKNOWN", "color": C_UNK}}},
            ],
            thresholds={"mode": "absolute", "steps": [
                {"color": C_PASS, "value": None}, {"color": C_WARN, "value": 1},
                {"color": C_FAIL, "value": 2}, {"color": C_UNK, "value": 3}]}
        ))
    y += 3

    # ════════════════════════════════════════════════════════
    # DAY 0 — PROVISIONING HEALTH (by Workload Type)
    # ════════════════════════════════════════════════════════
    panels.append(row("Day 0 — Provisioning Health (by Workload Type)", y)); y += 1

    for wk_key, wk in WORKLOAD_CRITICAL_PATHS.items():
        check_re = _check_regex(wk["day0"])
        panels.append(tbl(
            f"Day 0 Critical Path: {wk['label']}",
            f"Provisioning gate checks for {wk['label']}. "
            f"ALL must PASS before workload can schedule.\n\n"
            f"{wk['description']}",
            {"h": 8, "w": 8, "x": list(WORKLOAD_CRITICAL_PATHS.keys()).index(wk_key) * 8, "y": y},
            [tgt(f'node_health_check_status{{{N}, check=~"{check_re}"}}', "", fmt="table")],
            transforms=[
                {"id": "organize", "options": {
                    "excludeByName": {"Time": True, "__name__": True, "job": True,
                        "instance": True, "endpoint": True, "service": True,
                        "namespace": True, "pod": True, "prometheus": True},
                    "renameByName": {
                        "node": "Node", "check": "Check", "component": "Component",
                        "severity": "Sev", "Value": "Status"}}}
            ],
            overrides=[
                {"matcher": {"id": "byName", "options": "Check"}, "properties": [
                    {"id": "custom.width", "value": 200}]},
                {"matcher": {"id": "byName", "options": "Status"}, "properties": [
                    {"id": "custom.width", "value": 80},
                    {"id": "mappings", "value": [
                        {"type": "value", "options": {"0": {"text": "PASS", "color": C_PASS}}},
                        {"type": "value", "options": {"1": {"text": "WARN", "color": C_WARN}}},
                        {"type": "value", "options": {"2": {"text": "FAIL", "color": C_FAIL}}},
                    ]},
                    {"id": "custom.displayMode", "value": "color-background-solid"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": C_PASS, "value": None}, {"color": C_WARN, "value": 1},
                        {"color": C_FAIL, "value": 2}]}},
                ]},
            ],
            sort=[{"displayName": "Status", "desc": True}]
        ))
    y += 8

    # Day 0 check status over time
    panels.append(ts(
        "Day 0 All Provisioning Checks Over Time",
        "SR-IOV VF, GPU Operator, Network Operator, BIOS, driver versions.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'node_health_check_status{{{N}, check=~"day0_.*"}}', "{{node}} / {{check}}")],
        axis="Status (0=pass, 2=fail)"
    ))
    y += 8

    # ════════════════════════════════════════════════════════
    # DAY 2 — RUNTIME HEALTH (by Workload Type)
    # ════════════════════════════════════════════════════════
    panels.append(row("Day 2 — Runtime Health (by Workload Type)", y)); y += 1

    for wk_key, wk in WORKLOAD_CRITICAL_PATHS.items():
        check_re = _check_regex(wk["day2"])
        panels.append(tbl(
            f"Day 2 Critical Path: {wk['label']}",
            f"Runtime health checks for {wk['label']}. "
            f"Failure = job degradation or crash.\n\n"
            f"{wk['description']}",
            {"h": 10, "w": 8, "x": list(WORKLOAD_CRITICAL_PATHS.keys()).index(wk_key) * 8, "y": y},
            [tgt(f'node_health_check_status{{{N}, check=~"{check_re}"}}', "", fmt="table")],
            transforms=[
                {"id": "organize", "options": {
                    "excludeByName": {"Time": True, "__name__": True, "job": True,
                        "instance": True, "endpoint": True, "service": True,
                        "namespace": True, "pod": True, "prometheus": True},
                    "renameByName": {
                        "node": "Node", "check": "Check", "component": "Component",
                        "severity": "Sev", "Value": "Status"}}}
            ],
            overrides=[
                {"matcher": {"id": "byName", "options": "Check"}, "properties": [
                    {"id": "custom.width", "value": 200}]},
                {"matcher": {"id": "byName", "options": "Status"}, "properties": [
                    {"id": "custom.width", "value": 80},
                    {"id": "mappings", "value": [
                        {"type": "value", "options": {"0": {"text": "PASS", "color": C_PASS}}},
                        {"type": "value", "options": {"1": {"text": "WARN", "color": C_WARN}}},
                        {"type": "value", "options": {"2": {"text": "FAIL", "color": C_FAIL}}},
                    ]},
                    {"id": "custom.displayMode", "value": "color-background-solid"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": C_PASS, "value": None}, {"color": C_WARN, "value": 1},
                        {"color": C_FAIL, "value": 2}]}},
                ]},
            ],
            sort=[{"displayName": "Status", "desc": True}]
        ))
    y += 10

    # ════════════════════════════════════════════════════════
    # ALL CHECKS TABLE
    # ════════════════════════════════════════════════════════
    panels.append(row("All Checks — Detailed Status", y)); y += 1

    panels.append(tbl(
        "Check Results (All)",
        "Every registered health check with current status, severity, and component.",
        {"h": 12, "w": 24, "x": 0, "y": y},
        [tgt(f'node_health_check_status{{{N}}}', "", fmt="table")],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "job": True,
                    "instance": True, "endpoint": True, "service": True,
                    "namespace": True, "pod": True, "prometheus": True},
                "renameByName": {
                    "node": "Node", "check": "Check", "component": "Component",
                    "severity": "Severity", "Value": "Status"}}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Check"}, "properties": [
                {"id": "custom.width", "value": 280}]},
            {"matcher": {"id": "byName", "options": "Component"}, "properties": [
                {"id": "custom.width", "value": 120}]},
            {"matcher": {"id": "byName", "options": "Status"}, "properties": [
                {"id": "custom.width", "value": 120},
                {"id": "mappings", "value": [
                    {"type": "value", "options": {"0": {"text": "PASS", "color": C_PASS}}},
                    {"type": "value", "options": {"1": {"text": "WARN", "color": C_WARN}}},
                    {"type": "value", "options": {"2": {"text": "FAIL", "color": C_FAIL}}},
                    {"type": "value", "options": {"3": {"text": "UNKNOWN", "color": C_UNK}}},
                ]},
                {"id": "custom.displayMode", "value": "color-background-solid"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": C_PASS, "value": None}, {"color": C_WARN, "value": 1},
                    {"color": C_FAIL, "value": 2}, {"color": C_UNK, "value": 3}]}},
            ]},
        ],
        sort=[{"displayName": "Status", "desc": True}]
    ))
    y += 12

    # ════════════════════════════════════════════════════════
    # GPU HEALTH — DCGM EXPORTER METRICS
    # ════════════════════════════════════════════════════════
    panels.append(row("GPU Health — DCGM Exporter", y)); y += 1

    panels.append(ts(
        "GPU Temperature", "Liquid-cooled B200: max 70C sustained. Air-cooled: max 83C.",
        {"h": 8, "w": 8, "x": 0, "y": y},
        [tgt('DCGM_FI_DEV_GPU_TEMP', "GPU {{gpu}}")],
        axis="Temperature", unit="celsius"
    ))

    panels.append(ts(
        "GPU ECC Errors",
        "DBE (double-bit, uncorrectable) = P0 CRITICAL. SBE = monitor trend.",
        {"h": 8, "w": 8, "x": 8, "y": y},
        [tgt('DCGM_FI_DEV_ECC_DBE_VOL_TOTAL', "GPU {{gpu}} DBE"),
         tgt('DCGM_FI_DEV_ECC_SBE_VOL_TOTAL', "GPU {{gpu}} SBE")],
        axis="Error Count",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*DBE.*"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
            {"matcher": {"id": "byRegexp", "options": ".*SBE.*"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_WARN, "mode": "fixed"}}]},
        ]
    ))

    panels.append(ts(
        "GPU Power Draw", "B200 TDP = 1000W.",
        {"h": 8, "w": 8, "x": 16, "y": y},
        [tgt('DCGM_FI_DEV_POWER_USAGE', "GPU {{gpu}}")],
        axis="Power", unit="watt"
    ))
    y += 8

    panels.append(ts(
        "XID Error Timeline",
        "All XIDs on this node. Spikes = investigate. Critical: 48,79,74,61-64,94-95.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('DCGM_FI_DEV_XID_ERRORS', "GPU {{gpu}} XID")],
        axis="XID Count"
    ))

    panels.append(ts(
        "NVLink Errors",
        "CRC, replay, recovery. Recovery > 0 = NVLink degradation.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL', "GPU {{gpu}} CRC"),
         tgt('DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL', "GPU {{gpu}} Replay"),
         tgt('DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL', "GPU {{gpu}} Recovery")],
        axis="Error Count",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*Recovery.*"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
        ]
    ))
    y += 8

    panels.append(ts(
        "SM Clock — Current vs Max",
        "Clock delta > 10% = throttling. 30-90% perf degradation.",
        {"h": 8, "w": 8, "x": 0, "y": y},
        [tgt('DCGM_FI_DEV_SM_CLOCK', "GPU {{gpu}} Current"),
         tgt('DCGM_FI_DEV_MAX_SM_CLOCK', "GPU {{gpu}} Max")],
        axis="MHz"
    ))

    panels.append(ts(
        "PCIe Gen / Width",
        "Expected: Gen5 x16. Gen4 = 50% BW loss.",
        {"h": 8, "w": 8, "x": 8, "y": y},
        [tgt('DCGM_FI_DEV_PCIE_LINK_GEN', "GPU {{gpu}} Gen"),
         tgt('DCGM_FI_DEV_PCIE_LINK_WIDTH', "GPU {{gpu}} Width")],
        axis="Gen / Width"
    ))

    panels.append(ts(
        "Thermal & Power Violations",
        "Throttle time in microseconds.",
        {"h": 8, "w": 8, "x": 16, "y": y},
        [tgt('DCGM_FI_DEV_THERMAL_VIOLATION', "GPU {{gpu}} Thermal"),
         tgt('DCGM_FI_DEV_POWER_VIOLATION', "GPU {{gpu}} Power")],
        axis="Violation (us)",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*Thermal.*"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_P1, "mode": "fixed"}}]},
            {"matcher": {"id": "byRegexp", "options": ".*Power.*"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_P2, "mode": "fixed"}}]},
        ]
    ))
    y += 8

    panels.append(ts(
        "GPU Memory Usage", "B200 = 192 GB HBM3e per GPU.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('DCGM_FI_DEV_FB_USED', "GPU {{gpu}} Used"),
         tgt('DCGM_FI_DEV_FB_FREE', "GPU {{gpu}} Free")],
        axis="Memory", unit="decmbytes"
    ))

    panels.append(ts(
        "GPU Retired Pages",
        "Retired pages (SBE < 60 = OK, DBE must be 0). Indicates HBM degradation.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('DCGM_FI_DEV_RETIRED_SBE', "GPU {{gpu}} Retired SBE"),
         tgt('DCGM_FI_DEV_RETIRED_DBE', "GPU {{gpu}} Retired DBE")],
        axis="Retired Pages",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*DBE.*"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
        ]
    ))
    y += 8

    # ════════════════════════════════════════════════════════
    # SEVERITY BREAKDOWN
    # ════════════════════════════════════════════════════════
    panels.append(row("Severity Breakdown", y)); y += 1

    for i, (sev, label, color) in enumerate([
        ("0", "P0 Critical", C_P0), ("1", "P1 High", C_P1),
        ("2", "P2 Medium", C_P2), ("3", "P3 Low", C_P3),
    ]):
        panels.append(stat(
            label, f"Failing checks at severity {label}",
            {"h": 3, "w": 6, "x": i * 6, "y": y},
            [tgt(f'count(node_health_check_status{{{N}, severity="{sev}"}} > 0) or vector(0)',
                 label, instant=True)],
            color_mode="value",
            thresholds={"mode": "absolute", "steps": [{"color": color, "value": None}]}
        ))
    y += 3

    panels.append(ts(
        "Failing Checks by Severity Over Time", "",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'count by (severity) (node_health_check_status{{{N}}} >= 1)', "{{severity}}")],
        axis="Checks Failing",
        overrides=[
            {"matcher": {"id": "byName", "options": "0"}, "properties": [
                {"id": "displayName", "value": "P0 Critical"},
                {"id": "color", "value": {"fixedColor": C_P0, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "1"}, "properties": [
                {"id": "displayName", "value": "P1 High"},
                {"id": "color", "value": {"fixedColor": C_P1, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "2"}, "properties": [
                {"id": "displayName", "value": "P2 Medium"},
                {"id": "color", "value": {"fixedColor": C_P2, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "3"}, "properties": [
                {"id": "displayName", "value": "P3 Low"},
                {"id": "color", "value": {"fixedColor": C_P3, "mode": "fixed"}}]},
        ]
    ))
    y += 8

    # ════════════════════════════════════════════════════════
    # CORDON HISTORY & FRESHNESS
    # ════════════════════════════════════════════════════════
    panels.append(row("Cordon History & Agent Freshness", y)); y += 1

    panels.append(ts(
        "Cordon Signal Over Time",
        "1 = cordon recommended. Sustained = auto-cordon after grace period.",
        {"h": 6, "w": 12, "x": 0, "y": y},
        [tgt(f'node_health_should_cordon{{{N}}}', "{{node}}")],
        axis="Cordon (1=yes, 0=no)",
        overrides=[
            {"matcher": {"id": "byFrameRefID", "options": "A"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}},
                {"id": "custom.fillOpacity", "value": 30}]}
        ]
    ))

    panels.append(stat(
        "Last Check Run", "Timestamp of most recent check cycle",
        {"h": 3, "w": 4, "x": 12, "y": y},
        [tgt(f'node_health_last_check_timestamp_seconds{{{N}}}', "{{node}}", instant=True)],
        unit="dateTimeFromNow", color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": C_BLUE, "value": None}]}
    ))

    panels.append(stat(
        "Freshness", "Seconds since last check. Should be < interval.",
        {"h": 3, "w": 4, "x": 16, "y": y},
        [tgt(f'time() - node_health_last_check_timestamp_seconds{{{N}}}',
             "{{node}}", instant=True)],
        unit="s", color_mode="background",
        thresholds={"mode": "absolute", "steps": [
            {"color": C_PASS, "value": None},
            {"color": C_WARN, "value": 120},
            {"color": C_FAIL, "value": 300}]}
    ))

    panels.append(stat(
        "Health Status", "Redundant health indicator",
        {"h": 3, "w": 4, "x": 20, "y": y},
        [tgt(f'node_health_node_healthy{{{N}}}', "{{node}}", instant=True)],
        color_mode="background", graph_mode="area",
        mappings=[
            {"type": "value", "options": {"0": {"text": "UNHEALTHY", "color": C_FAIL}}},
            {"type": "value", "options": {"1": {"text": "HEALTHY", "color": C_PASS}}},
        ],
        thresholds={"mode": "absolute", "steps": [
            {"color": C_FAIL, "value": None}, {"color": C_PASS, "value": 1}]}
    ))

    panels.append(ts(
        "Component Health Over Time",
        "Worst status per component. 0=pass, 1=warn, 2=fail, 3=unknown.",
        {"h": 6, "w": 12, "x": 12, "y": y + 3},
        [tgt(f'node_health_component_status{{{N}}}', "{{component}}")],
        axis="Status",
        overrides=[
            {"matcher": {"id": "byName", "options": "gpu"}, "properties": [{"id": "color", "value": {"fixedColor": C_BLUE, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "cpu"}, "properties": [{"id": "color", "value": {"fixedColor": C_PURPLE, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "network"}, "properties": [{"id": "color", "value": {"fixedColor": C_TEAL, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "kubernetes"}, "properties": [{"id": "color", "value": {"fixedColor": C_ORANGE, "mode": "fixed"}}]},
        ]
    ))
    y += 9

    # ════════════════════════════════════════════════════════
    # TEMPLATING
    # ════════════════════════════════════════════════════════
    templating = {"list": [
        {"name": "datasource", "type": "datasource", "label": "Prometheus",
         "query": "prometheus", "current": {}, "hide": 0,
         "includeAll": False, "multi": False, "options": [],
         "refresh": 1, "regex": "", "skipUrlSync": False},
        {"name": "node", "type": "query", "label": "Node",
         "datasource": ds(),
         "definition": "label_values(node_health_node_healthy, node)",
         "query": {"query": "label_values(node_health_node_healthy, node)", "refId": "n"},
         "current": {}, "hide": 0,
         "includeAll": True, "multi": True,
         "options": [], "refresh": 2, "regex": "", "sort": 1, "skipUrlSync": False},
    ]}

    return {
        "__inputs": [], "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "9.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"}],
        "id": None, "uid": "sentinai-node-health-v3",
        "title": "SentinAI — Node Health Detector",
        "description": "Fleet health score, node heatmaps, Day 0/Day 2 panels by workload type "
                       "(Notebook / Single Node / Multi Node), DCGM metrics, severity breakdown.",
        "tags": ["sentinai", "node-health", "gpu", "dcgm", "fleet", "kubernetes"],
        "style": "dark", "timezone": "browser", "editable": True,
        "graphTooltip": 1, "fiscalYearStartMonth": 0, "liveNow": False,
        "refresh": "30s", "schemaVersion": 38, "version": 3,
        "time": {"from": "now-6h", "to": "now"}, "timepicker": {},
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts", "type": "dashboard"}]},
        "templating": templating,
        "panels": panels
    }


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "node-health-dashboard.json"
    d = build()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    pc = len(d["panels"])
    vc = len(d["templating"]["list"])
    print(f"Generated {out}: {pc} panels, {vc} template variables")
    for p in d["panels"]:
        print(f"  [{p['type']:14s}] {p.get('title', '')}")
