#!/usr/bin/env python3
"""Generate Node Health Detector Grafana Dashboard.
Professional quality — no emojis, clear legends, proper units.
Metrics prefix: node_health_*
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
LEGEND_BTM = {"displayMode": "table", "placement": "bottom",
              "calcs": ["lastNotNull"]}

# Color palette (professional, no neon)
C_PASS   = "#56A64B"  # Muted green
C_WARN   = "#E0A939"  # Warm amber
C_FAIL   = "#C04040"  # Deep red
C_UNK    = "#8F8F8F"  # Neutral gray
C_P0     = "#C04040"  # Critical red
C_P1     = "#E0663E"  # High orange
C_P2     = "#E0A939"  # Medium amber
C_P3     = "#7EB26D"  # Low green
C_BLUE   = "#3274D9"  # Primary blue
C_PURPLE = "#8F3BB8"  # Accent purple

N = 'node=~"$node"'

def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
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
                {"color": C_PASS, "value": None},
                {"color": C_WARN, "value": 0.6},
                {"color": C_FAIL, "value": 0.9}]},
            "min": 0, "max": 1}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
                    "showThresholdLabels": False, "showThresholdMarkers": True},
        "targets": refs(targets)
    }


def build():
    panels = []
    y = 0

    # ================================================================
    # ROW 0: OVERVIEW — Node Health Status
    # ================================================================
    panels.append(row("Node Health Overview", y)); y += 1

    # Health status stat
    panels.append(stat(
        "Node Health", "Overall node health: 1 = healthy, 0 = unhealthy",
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

    # Cordon status
    panels.append(stat(
        "Cordon Signal", "Whether the detector recommends cordoning this node",
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

    # Check counts
    for i, (label, metric, color) in enumerate([
        ("Passed", "passed", C_PASS),
        ("Warned", "warned", C_WARN),
        ("Failed", "failed", C_FAIL),
        ("Total Checks", "checks_run", C_BLUE),
    ]):
        panels.append(stat(
            label, f"Number of checks in {label.lower()} state",
            {"h": 4, "w": 4, "x": 8 + i * 4, "y": y},
            [tgt(f'node_health_{metric}{{{N}}}', "{{node}}", instant=True)],
            color_mode="value", text_mode="value",
            thresholds={"mode": "absolute", "steps": [{"color": color, "value": None}]}
        ))
    y += 4

    # Component status — one stat per component
    components = ["gpu", "cpu", "memory", "storage", "network", "kubernetes"]
    for i, comp in enumerate(components):
        panels.append(stat(
            comp.upper(), f"Worst check status for {comp} component",
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

    # ================================================================
    # ROW 1: ALL CHECKS TABLE — comprehensive status view
    # ================================================================
    panels.append(row("All Checks — Detailed Status", y)); y += 1

    panels.append(tbl(
        "Check Results",
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
                    "severity": "Severity", "Value": "Status"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Check"}, "properties": [
                {"id": "custom.width", "value": 280}]},
            {"matcher": {"id": "byName", "options": "Component"}, "properties": [
                {"id": "custom.width", "value": 120}]},
            {"matcher": {"id": "byName", "options": "Severity"}, "properties": [
                {"id": "custom.width", "value": 100}]},
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
            {"matcher": {"id": "byName", "options": "Node"}, "properties": [
                {"id": "custom.width", "value": 200}]},
        ],
        sort=[{"displayName": "Status", "desc": True}]
    ))
    y += 12

    # ================================================================
    # ROW 2: CHECK STATUS OVER TIME
    # ================================================================
    panels.append(row("Check Status Over Time", y)); y += 1

    # By component
    panels.append(ts(
        "Component Health Over Time",
        "Worst status per component over time. 0=pass, 1=warn, 2=fail, 3=unknown.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'node_health_component_status{{{N}}}', "{{component}}")],
        axis="Status (0=pass, 2=fail)",
        overrides=[
            {"matcher": {"id": "byName", "options": "gpu"}, "properties": [{"id": "color", "value": {"fixedColor": C_BLUE, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "cpu"}, "properties": [{"id": "color", "value": {"fixedColor": C_PURPLE, "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "memory"}, "properties": [{"id": "color", "value": {"fixedColor": "#E0A939", "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "storage"}, "properties": [{"id": "color", "value": {"fixedColor": "#7EB26D", "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "network"}, "properties": [{"id": "color", "value": {"fixedColor": "#6ED0E0", "mode": "fixed"}}]},
            {"matcher": {"id": "byName", "options": "kubernetes"}, "properties": [{"id": "color", "value": {"fixedColor": "#EF843C", "mode": "fixed"}}]},
        ]
    ))

    # Failed checks count over time
    panels.append(ts(
        "Failed Checks Over Time",
        "Total count of failed checks. Spikes indicate new failures.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'node_health_failed{{{N}}}', "{{node}} — failed"),
         tgt(f'node_health_warned{{{N}}}', "{{node}} — warned")],
        axis="Check Count",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*failed.*"}, "properties": [{"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
            {"matcher": {"id": "byRegexp", "options": ".*warned.*"}, "properties": [{"id": "color", "value": {"fixedColor": C_WARN, "mode": "fixed"}}]},
        ]
    ))
    y += 8

    # Per-check status heatmap-style
    panels.append(ts(
        "Individual Check Status Over Time",
        "Each line = one check. 0=pass, 1=warn, 2=fail. "
        "Lines jumping up indicate check failures.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [tgt(f'node_health_check_status{{{N}}}', "{{check}}")],
        axis="Status (0=pass, 2=fail)"
    ))
    y += 10

    # ================================================================
    # ROW 3: GPU HEALTH (component-specific)
    # ================================================================
    panels.append(row("GPU Health", y)); y += 1

    # GPU checks status
    panels.append(ts(
        "GPU Check Status Over Time",
        "All GPU-component checks. 0=pass, 1=warn, 2=fail.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'node_health_check_status{{{N}, component="gpu"}}', "{{check}}")],
        axis="Status"
    ))

    # GPU cordon signals
    panels.append(ts(
        "GPU Cordon Signals",
        "Which GPU checks are requesting node cordon. 1 = cordon requested.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'node_health_check_cordon{{{N}, component="gpu"}}', "{{check}}")],
        axis="Cordon (1=yes)",
        overrides=[
            {"matcher": {"id": "byValue", "options": {"op": "gte", "value": 1}},
             "properties": [{"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]}
        ]
    ))
    y += 8

    # Live DCGM metrics (if DCGM exporter is available separately)
    panels.append(ts(
        "GPU Temperature (from DCGM Exporter)",
        "Real-time GPU temperature from DCGM exporter. "
        "Liquid-cooled B200: sustained max 70C. Air-cooled: max 83C.",
        {"h": 8, "w": 8, "x": 0, "y": y},
        [tgt('DCGM_FI_DEV_GPU_TEMP', "GPU {{gpu}}", )],
        axis="Temperature", unit="celsius"
    ))

    panels.append(ts(
        "GPU ECC Errors (from DCGM Exporter)",
        "Volatile ECC error counts: DBE (double-bit, uncorrectable) = P0 CRITICAL. "
        "SBE (single-bit, correctable) = monitor trend.",
        {"h": 8, "w": 8, "x": 8, "y": y},
        [tgt('DCGM_FI_DEV_ECC_DBE_VOL_TOTAL', "GPU {{gpu}} DBE (uncorrectable)"),
         tgt('DCGM_FI_DEV_ECC_SBE_VOL_TOTAL', "GPU {{gpu}} SBE (correctable)")],
        axis="Error Count",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*DBE.*"}, "properties": [{"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
            {"matcher": {"id": "byRegexp", "options": ".*SBE.*"}, "properties": [{"id": "color", "value": {"fixedColor": C_WARN, "mode": "fixed"}}]},
        ]
    ))

    panels.append(ts(
        "GPU Power Draw (from DCGM Exporter)",
        "Current power draw per GPU. B200 TDP = 1000W. "
        "Sustained draw near TDP is normal under load.",
        {"h": 8, "w": 8, "x": 16, "y": y},
        [tgt('DCGM_FI_DEV_POWER_USAGE', "GPU {{gpu}}")],
        axis="Power", unit="watt"
    ))
    y += 8

    panels.append(ts(
        "NVLink Errors (from DCGM Exporter)",
        "NVLink CRC flit errors, replay errors, recovery errors. "
        "Recovery > 0 = NVLink degradation. CRC/replay = noise if low.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL', "GPU {{gpu}} CRC"),
         tgt('DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL', "GPU {{gpu}} Replay"),
         tgt('DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL', "GPU {{gpu}} Recovery")],
        axis="Error Count",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*Recovery.*"}, "properties": [{"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}}]},
        ]
    ))

    panels.append(ts(
        "GPU Memory Usage (from DCGM Exporter)",
        "GPU framebuffer usage. B200 = 192 GB HBM3e per GPU.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('DCGM_FI_DEV_FB_USED', "GPU {{gpu}} Used"),
         tgt('DCGM_FI_DEV_FB_FREE', "GPU {{gpu}} Free")],
        axis="Memory", unit="decmbytes"
    ))
    y += 8

    # ================================================================
    # ROW 4: CPU & SYSTEM HEALTH
    # ================================================================
    panels.append(row("CPU, Memory, Storage Health", y)); y += 1

    panels.append(ts(
        "CPU/Memory/Storage Check Status",
        "All non-GPU component checks over time.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'node_health_check_status{{{N}, component=~"cpu|memory|storage"}}', "{{check}}")],
        axis="Status (0=pass, 2=fail)"
    ))

    panels.append(ts(
        "Network & Kubernetes Check Status",
        "Network interface and Kubernetes component checks.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'node_health_check_status{{{N}, component=~"network|kubernetes"}}', "{{check}}")],
        axis="Status (0=pass, 2=fail)"
    ))
    y += 8

    # ================================================================
    # ROW 5: SEVERITY BREAKDOWN
    # ================================================================
    panels.append(row("Severity Breakdown", y)); y += 1

    for i, (sev, label, color) in enumerate([
        ("0", "P0 Critical", C_P0), ("1", "P1 High", C_P1),
        ("2", "P2 Medium", C_P2), ("3", "P3 Low", C_P3),
    ]):
        panels.append(stat(
            label, f"Number of checks at severity {label}",
            {"h": 3, "w": 6, "x": i * 6, "y": y},
            [tgt(f'count(node_health_check_status{{{N}, severity="{sev}"}} > 0) or vector(0)',
                 label, instant=True)],
            color_mode="value",
            thresholds={"mode": "absolute", "steps": [{"color": color, "value": None}]}
        ))
    y += 3

    # Failing checks by severity
    panels.append(ts(
        "Failing Checks by Severity Over Time",
        "Count of checks in FAIL or WARN state, grouped by severity level.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'count by (severity) (node_health_check_status{{{N}}} >= 1)', "{{severity}}")],
        axis="Checks Failing/Warning",
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

    # ================================================================
    # ROW 6: CORDON/UNCORDON HISTORY
    # ================================================================
    panels.append(row("Cordon Signal History", y)); y += 1

    panels.append(ts(
        "Node Cordon Signal Over Time",
        "1 = detector recommends cordoning. 0 = healthy. "
        "Sustained 1 triggers automatic cordon after grace period.",
        {"h": 6, "w": 24, "x": 0, "y": y},
        [tgt(f'node_health_should_cordon{{{N}}}', "{{node}}")],
        axis="Cordon (1=yes, 0=no)",
        overrides=[
            {"matcher": {"id": "byFrameRefID", "options": "A"}, "properties": [
                {"id": "color", "value": {"fixedColor": C_FAIL, "mode": "fixed"}},
                {"id": "custom.fillOpacity", "value": 30}]}
        ]
    ))
    y += 6

    # Last check timestamp
    panels.append(stat(
        "Last Check Run", "Unix timestamp of the most recent check cycle",
        {"h": 3, "w": 8, "x": 0, "y": y},
        [tgt(f'node_health_last_check_timestamp_seconds{{{N}}}', "{{node}}", instant=True)],
        unit="dateTimeFromNow", color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": C_BLUE, "value": None}]}
    ))

    panels.append(stat(
        "Check Cycle Freshness", "How many seconds since last check. Should be < check interval.",
        {"h": 3, "w": 8, "x": 8, "y": y},
        [tgt(f'time() - node_health_last_check_timestamp_seconds{{{N}}}',
             "{{node}}", instant=True)],
        unit="s", color_mode="background",
        thresholds={"mode": "absolute", "steps": [
            {"color": C_PASS, "value": None},
            {"color": C_WARN, "value": 120},
            {"color": C_FAIL, "value": 300}]}
    ))

    panels.append(stat(
        "Node Health Status",
        "1 = all checks passing, 0 = one or more checks failing",
        {"h": 3, "w": 8, "x": 16, "y": y},
        [tgt(f'node_health_node_healthy{{{N}}}', "{{node}}", instant=True)],
        color_mode="background", graph_mode="area",
        mappings=[
            {"type": "value", "options": {"0": {"text": "UNHEALTHY", "color": C_FAIL}}},
            {"type": "value", "options": {"1": {"text": "HEALTHY", "color": C_PASS}}},
        ],
        thresholds={"mode": "absolute", "steps": [
            {"color": C_FAIL, "value": None}, {"color": C_PASS, "value": 1}]}
    ))
    y += 3

    # ================================================================
    # TEMPLATING
    # ================================================================
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
        "id": None, "uid": "node-health-detector-v1",
        "title": "Node Health Detector",
        "description": "Node health checks: GPU, CPU, Memory, Storage, Network, Kubernetes. "
                       "Severity classification, cordon/uncordon signals, per-component status.",
        "tags": ["node-health", "gpu", "dcgm", "kubernetes", "monitoring"],
        "style": "dark", "timezone": "browser", "editable": True,
        "graphTooltip": 1, "fiscalYearStartMonth": 0, "liveNow": False,
        "refresh": "30s", "schemaVersion": 38, "version": 1,
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
        print(f"  [{p['type']:12s}] {p.get('title', '')}")
