#!/usr/bin/env python3
"""Generate the K8s Node Storage & Pod Lifecycle Grafana Dashboard JSON.
Covers: pod start/stop lifecycle, node-level filesystem usage across all
mount points, and a deep /var analysis showing per-pod ephemeral storage.
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
    for i, t in enumerate(targets): t["refId"] = chr(65 + i)
    return targets

NS = 'namespace=~"$namespace"'
ND = 'node=~"$node"'
NSND = f'{NS}, {ND}'

LEGEND_TABLE = {"displayMode": "table", "placement": "right",
                "calcs": ["min", "max", "mean", "lastNotNull"]}
LEGEND_TABLE_BOTTOM = {"displayMode": "table", "placement": "bottom",
                       "calcs": ["min", "max", "mean", "lastNotNull"]}

def row_panel(title, y, collapsed=False):
    return {"type": "row", "title": title, "collapsed": collapsed,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}

def stat_p(title, desc, gp, targets, unit="none", decimals=0,
           thresholds=None, color_mode="background", text_mode="auto", orient="auto"):
    return {
        "id": nid(), "title": title, "description": desc, "type": "stat",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals,
            "thresholds": thresholds or {"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None}]},
            "mappings": []}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": orient, "textMode": text_mode,
            "colorMode": color_mode, "graphMode": "none", "justifyMode": "center"},
        "targets": refs(targets)
    }

def gauge_p(title, desc, gp, targets, unit="percentunit", max_val=1):
    return {
        "id": nid(), "title": title, "description": desc, "type": "gauge",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 1, "min": 0, "max": max_val,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None},
                {"color": "#FF9830", "value": max_val * 0.75},
                {"color": "#FF4040", "value": max_val * 0.9}]}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
            "showThresholdLabels": True, "showThresholdMarkers": True},
        "targets": refs(targets)
    }

def ts_panel(title, desc, gp, targets, axis_label, unit="bytes", overrides=None):
    return {
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 2, "fillOpacity": 15, "gradientMode": "none",
                "axisLabel": axis_label, "drawStyle": "line", "pointSize": 5,
                "showPoints": "auto", "spanNulls": True}},
            "overrides": overrides or []},
        "options": {"legend": LEGEND_TABLE,
            "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs(targets)
    }

def stacked_ts(title, desc, gp, targets, axis_label, unit="bytes"):
    return {
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 0, "fillOpacity": 80, "gradientMode": "none",
                "axisLabel": axis_label, "drawStyle": "bars", "pointSize": 5,
                "stacking": {"mode": "normal"}, "showPoints": "never"}},
            "overrides": []},
        "options": {"legend": LEGEND_TABLE,
            "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs(targets)
    }

def table_p(title, desc, gp, targets, transformations=None, overrides=None,
            sort_by=None, footer_fields=None):
    return {
        "id": nid(), "title": title, "description": desc, "type": "table",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": overrides or []},
        "options": {"showHeader": True,
            "sortBy": sort_by or [],
            "footer": {"show": bool(footer_fields), "reducer": ["sum"],
                       "fields": footer_fields or []}},
        "transformations": transformations or [],
        "targets": refs(targets)
    }


def build():
    panels = []
    y = 0

    # ================================================================
    # ROW 1: POD LIFECYCLE
    # ================================================================
    panels.append(row_panel("Pod Lifecycle — Start / Shutdown Times", y)); y += 1

    # Pod count over time
    panels.append(ts_panel(
        "Running Pod Count Over Time",
        "Number of pods in Running phase over time for selected scope.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'count(kube_pod_status_phase{{{NS}, phase="Running"}} == 1 * on(pod, namespace) group_left() (kube_pod_info{{{NSND}}} * 0 + 1))', "Running Pods"),
         tgt(f'count(kube_pod_status_phase{{{NS}, phase="Pending"}} == 1 * on(pod, namespace) group_left() (kube_pod_info{{{NSND}}} * 0 + 1))', "Pending Pods"),
         tgt(f'count(kube_pod_status_phase{{{NS}, phase="Failed"}} == 1 * on(pod, namespace) group_left() (kube_pod_info{{{NSND}}} * 0 + 1))', "Failed Pods")],
        axis_label="Pod Count", unit="short"
    ))

    # Pod starts over time (rate of new pods)
    panels.append(ts_panel(
        "Pod Starts and Restarts Over Time",
        "Rate of pod container starts and restarts. Spikes indicate scaling events or crash loops.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum(rate(kube_pod_container_status_restarts_total{{{NSND}}}[5m])) by (pod)', "{{pod}} restarts/s"),
         tgt(f'count(changes(kube_pod_start_time{{{NSND}}}[5m]))', "New Pod Starts")],
        axis_label="Rate", unit="short"
    ))
    y += 8

    # Pod lifecycle table — shows each pod, when it started, phase, age
    panels.append(table_p(
        "All Pods — Start Time, Phase, Uptime",
        "Every pod in scope with its start time, current phase, node, and uptime. "
        "Sorted by most recently started. Start time is a Unix timestamp converted to date.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_start_time{{{NSND}}}', "", fmt="table"),
            tgt(f'time() - kube_pod_start_time{{{NSND}}}', "", fmt="table"),
            tgt(f'kube_pod_status_phase{{{NS}}} == 1 * on(pod, namespace) group_left(node) kube_pod_info{{{NSND}}}', "", fmt="table"),
        ],
        transformations=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                                  "job": True, "instance": True, "service": True,
                                  "container": True, "endpoint": True,
                                  "prometheus": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "node": "Node",
                    "Value #A": "Start Time (Unix)", "Value #B": "Uptime (seconds)",
                    "phase": "Phase"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"},
             "properties": [{"id": "custom.width", "value": 300}]},
            {"matcher": {"id": "byName", "options": "Namespace"},
             "properties": [{"id": "custom.width", "value": 140}]},
            {"matcher": {"id": "byName", "options": "Node"},
             "properties": [{"id": "custom.width", "value": 200}]},
            {"matcher": {"id": "byName", "options": "Start Time (Unix)"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Uptime (seconds)"},
             "properties": [{"id": "unit", "value": "dtdurations"}]},
        ],
        sort_by=[{"displayName": "Start Time (Unix)", "desc": True}]
    ))
    y += 10

    # Pod completion/termination events
    panels.append(ts_panel(
        "Recently Terminated Pods (Phase Changes)",
        "Tracks pods entering Succeeded or Failed phase. Useful for identifying workload completions and failures.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'count(kube_pod_status_phase{{{NS}, phase="Succeeded"}} == 1 * on(pod, namespace) group_left() (kube_pod_info{{{NSND}}} * 0 + 1)) or vector(0)', "Succeeded Pods"),
         tgt(f'count(kube_pod_status_phase{{{NS}, phase="Failed"}} == 1 * on(pod, namespace) group_left() (kube_pod_info{{{NSND}}} * 0 + 1)) or vector(0)', "Failed Pods"),
         tgt(f'count(kube_pod_status_phase{{{NS}, phase="Unknown"}} == 1 * on(pod, namespace) group_left() (kube_pod_info{{{NSND}}} * 0 + 1)) or vector(0)', "Unknown Phase")],
        axis_label="Pod Count", unit="short"
    ))
    y += 8

    # ================================================================
    # ROW 2: NODE FILESYSTEM OVERVIEW — ALL MOUNT POINTS
    # ================================================================
    panels.append(row_panel("Node Filesystem Overview — All Mount Points", y)); y += 1

    # Summary stats
    panels.append(stat_p(
        "Total Filesystem Size (all mounts)",
        "Sum of all filesystem sizes on selected node(s)",
        {"h": 4, "w": 6, "x": 0, "y": y},
        [tgt(f'sum(node_filesystem_size_bytes{{node=~"$node", fstype!~"tmpfs|overlay"}})', "Total", instant=True)],
        unit="bytes", color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": "#5794F2", "value": None}]}
    ))
    panels.append(stat_p(
        "Total Used (all mounts)",
        "Sum of used bytes across all filesystems on selected node(s)",
        {"h": 4, "w": 6, "x": 6, "y": y},
        [tgt(f'sum(node_filesystem_size_bytes{{node=~"$node", fstype!~"tmpfs|overlay"}} - node_filesystem_avail_bytes{{node=~"$node", fstype!~"tmpfs|overlay"}})', "Used", instant=True)],
        unit="bytes", color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": "#FF9830", "value": None}]}
    ))
    panels.append(stat_p(
        "Total Available (all mounts)",
        "Sum of available bytes across all filesystems",
        {"h": 4, "w": 6, "x": 12, "y": y},
        [tgt(f'sum(node_filesystem_avail_bytes{{node=~"$node", fstype!~"tmpfs|overlay"}})', "Available", instant=True)],
        unit="bytes", color_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": "#73BF69", "value": None}]}
    ))
    panels.append(gauge_p(
        "Overall Disk Utilization %",
        "Percentage of all non-tmpfs filesystem capacity that is used",
        {"h": 4, "w": 6, "x": 18, "y": y},
        [tgt(f'1 - (sum(node_filesystem_avail_bytes{{node=~"$node", fstype!~"tmpfs|overlay"}}) / sum(node_filesystem_size_bytes{{node=~"$node", fstype!~"tmpfs|overlay"}}))', "Used %", instant=True)]
    ))
    y += 4

    # Table of all filesystems on node
    panels.append(table_p(
        "All Filesystems — Size, Used, Available, Usage %",
        "Every filesystem on selected node(s) with device info, mount point, "
        "total size, used, available, and usage percentage.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [
            tgt(f'node_filesystem_size_bytes{{node=~"$node"}}', "", fmt="table"),
            tgt(f'node_filesystem_size_bytes{{node=~"$node"}} - node_filesystem_avail_bytes{{node=~"$node"}}', "", fmt="table"),
            tgt(f'node_filesystem_avail_bytes{{node=~"$node"}}', "", fmt="table"),
            tgt(f'1 - (node_filesystem_avail_bytes{{node=~"$node"}} / node_filesystem_size_bytes{{node=~"$node"}})', "", fmt="table"),
        ],
        transformations=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "job": True,
                                  "instance": True, "service": True, "endpoint": True,
                                  "prometheus": True, "container": True},
                "renameByName": {
                    "node": "Node", "mountpoint": "Mount Point", "device": "Device",
                    "fstype": "FS Type",
                    "Value #A": "Total Size", "Value #B": "Used",
                    "Value #C": "Available", "Value #D": "Usage %"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Node"}, "properties": [{"id": "custom.width", "value": 200}]},
            {"matcher": {"id": "byName", "options": "Mount Point"}, "properties": [{"id": "custom.width", "value": 180}]},
            {"matcher": {"id": "byName", "options": "Device"}, "properties": [{"id": "custom.width", "value": 200}]},
            {"matcher": {"id": "byName", "options": "FS Type"}, "properties": [{"id": "custom.width", "value": 80}]},
            {"matcher": {"id": "byRegexp", "options": "Total Size|Used|Available"},
             "properties": [{"id": "unit", "value": "bytes"}, {"id": "decimals", "value": 2}]},
            {"matcher": {"id": "byName", "options": "Usage %"},
             "properties": [{"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 1},
                {"id": "custom.displayMode", "value": "gradient-gauge"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 0.75},
                    {"color": "#FF4040", "value": 0.9}]}}]},
        ],
        sort_by=[{"displayName": "Usage %", "desc": True}]
    ))
    y += 8

    # Time series: all filesystem usage % over time
    panels.append(ts_panel(
        "Filesystem Usage % Over Time — All Mount Points",
        "Each line is a mount point. Shows how full each filesystem is getting over time. "
        "Helps identify filesystems approaching capacity.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [tgt(f'1 - (node_filesystem_avail_bytes{{node=~"$node"}} / node_filesystem_size_bytes{{node=~"$node"}})',
             "{{node}}:{{mountpoint}} ({{device}})")],
        axis_label="Usage %", unit="percentunit",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*:/$|.*:/var.*"},
             "properties": [{"id": "custom.lineWidth", "value": 3}]}
        ]
    ))
    y += 10

    # Time series: absolute used bytes per mount point
    panels.append(ts_panel(
        "Filesystem Used Bytes Over Time — Per Mount Point",
        "Absolute bytes used on each filesystem over time. Each line = one mount point on the node.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [tgt(f'node_filesystem_size_bytes{{node=~"$node"}} - node_filesystem_avail_bytes{{node=~"$node"}}',
             "{{node}}:{{mountpoint}} ({{device}})")],
        axis_label="Used", unit="bytes"
    ))
    y += 10

    # ================================================================
    # ROW 3: /var DEEP DIVE
    # ================================================================
    panels.append(row_panel("/var Deep Dive — Ephemeral Storage & Container Layers", y)); y += 1

    # /var usage gauge
    panels.append(gauge_p(
        "/var Usage %",
        "How full /var is right now. /var is the primary ephemeral storage mount in Kubernetes — "
        "contains container images, logs, and ephemeral volumes.",
        {"h": 5, "w": 6, "x": 0, "y": y},
        [tgt(f'1 - (node_filesystem_avail_bytes{{node=~"$node", mountpoint=~"/var.*"}} / node_filesystem_size_bytes{{node=~"$node", mountpoint=~"/var.*"}})',
             "{{mountpoint}}", instant=True)]
    ))

    # /var absolute sizes
    panels.append(stat_p(
        "/var Capacity Breakdown",
        "Total size, used, and available on /var partitions",
        {"h": 5, "w": 6, "x": 6, "y": y},
        [tgt(f'node_filesystem_size_bytes{{node=~"$node", mountpoint=~"/var.*"}}', "Total ({{mountpoint}})", instant=True),
         tgt(f'node_filesystem_size_bytes{{node=~"$node", mountpoint=~"/var.*"}} - node_filesystem_avail_bytes{{node=~"$node", mountpoint=~"/var.*"}}', "Used ({{mountpoint}})", instant=True),
         tgt(f'node_filesystem_avail_bytes{{node=~"$node", mountpoint=~"/var.*"}}', "Available ({{mountpoint}})", instant=True)],
        unit="bytes", decimals=2, color_mode="value", text_mode="value_and_name", orient="horizontal",
        thresholds={"mode": "absolute", "steps": [{"color": "#73BF69", "value": None}]}
    ))

    # How /var is consumed — by category
    panels.append(stat_p(
        "/var Consumers — Category Breakdown",
        "Key consumers of /var space: container filesystem layers (ephemeral), "
        "container logs, and kubelet volumes.",
        {"h": 5, "w": 12, "x": 12, "y": y},
        [
            tgt(f'sum(container_fs_usage_bytes{{{NSND}}})', "Container Ephemeral FS (all pods)", instant=True),
            tgt(f'sum(container_fs_usage_bytes{{{NSND}, container!=""}})', "Container Writable Layers", instant=True),
            tgt(f'sum(kubelet_volume_stats_used_bytes{{node=~"$node"}})', "PVC/EmptyDir Volumes", instant=True),
        ],
        unit="bytes", decimals=2, color_mode="value", text_mode="value_and_name", orient="horizontal",
        thresholds={"mode": "absolute", "steps": [{"color": "#73BF69", "value": None}]}
    ))
    y += 5

    # /var usage % over time
    panels.append(ts_panel(
        "/var Usage % Over Time",
        "How /var utilization changes over time. Watch for upward trends that could lead to node eviction.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'1 - (node_filesystem_avail_bytes{{node=~"$node", mountpoint=~"/var.*"}} / node_filesystem_size_bytes{{node=~"$node", mountpoint=~"/var.*"}})',
             "{{node}}:{{mountpoint}}")],
        axis_label="Usage %", unit="percentunit",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*"},
             "properties": [
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 0.75},
                    {"color": "#FF4040", "value": 0.9}]}}
             ]}
        ]
    ))

    # /var used bytes over time
    panels.append(ts_panel(
        "/var Used Bytes Over Time",
        "Absolute bytes used on /var over time. Compare against total capacity.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'node_filesystem_size_bytes{{node=~"$node", mountpoint=~"/var.*"}} - node_filesystem_avail_bytes{{node=~"$node", mountpoint=~"/var.*"}}',
             "Used ({{node}}:{{mountpoint}})"),
         tgt(f'node_filesystem_size_bytes{{node=~"$node", mountpoint=~"/var.*"}}',
             "Total ({{node}}:{{mountpoint}})")],
        axis_label="Bytes", unit="bytes",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": "Total.*"},
             "properties": [
                {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}},
                {"id": "custom.fillOpacity", "value": 0},
                {"id": "color", "value": {"mode": "fixed", "fixedColor": "#FF4040"}},
                {"id": "custom.lineWidth", "value": 3}
             ]}
        ]
    ))
    y += 8

    # ================================================================
    # ROW 4: PER-POD EPHEMERAL STORAGE ON /var
    # ================================================================
    panels.append(row_panel("Per-Pod Ephemeral Storage Usage (Container FS on /var)", y)); y += 1

    # Stacked: per-pod container_fs_usage_bytes
    panels.append(stacked_ts(
        "Per-Pod Ephemeral Storage Usage — Stacked",
        "Each color = a pod. Height = total ephemeral storage used by ALL pods. "
        "container_fs_usage_bytes measures the writable container layer, which lives on /var.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [tgt(f'sum by (pod) (container_fs_usage_bytes{{{NSND}, container!=""}})', "{{pod}}")],
        axis_label="Ephemeral FS Used", unit="bytes"
    ))
    y += 10

    # Per-pod time series (not stacked, line chart)
    panels.append(ts_panel(
        "Per-Pod Ephemeral Storage — Individual Lines",
        "Each line = one pod's ephemeral storage consumption. "
        "Compare against ephemeral limits to identify pods at risk of eviction.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [tgt(f'sum by (pod) (container_fs_usage_bytes{{{NSND}, container!=""}})', "{{pod}} Used"),
         tgt(f'sum by (pod) (kube_pod_container_resource_limits{{{NSND}, resource=~"ephemeral.storage"}})', "{{pod}} Limit")],
        axis_label="Bytes", unit="bytes",
        overrides=[
            {"matcher": {"id": "byRegexp", "options": ".*Limit.*"},
             "properties": [
                {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [6, 4]}},
                {"id": "custom.fillOpacity", "value": 0},
                {"id": "color", "value": {"mode": "fixed", "fixedColor": "#FF4040"}}
             ]}
        ]
    ))
    y += 10

    # Table: top pods by ephemeral storage
    panels.append(table_p(
        "Top Pods by Ephemeral Storage Usage",
        "Pods ranked by current ephemeral filesystem usage. Shows usage, request, limit, "
        "and how much headroom remains before eviction risk.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [
            tgt(f'sum by (pod, namespace, node) (container_fs_usage_bytes{{{NSND}, container!=""}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{NSND}, resource=~"ephemeral.storage"}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{NSND}, resource=~"ephemeral.storage"}})', "", fmt="table"),
        ],
        transformations=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "node": "Node",
                    "Value #A": "Current Usage", "Value #B": "Request", "Value #C": "Limit"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 300}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 140}]},
            {"matcher": {"id": "byName", "options": "Node"}, "properties": [{"id": "custom.width", "value": 200}]},
            {"matcher": {"id": "byRegexp", "options": "Current Usage|Request|Limit"},
             "properties": [{"id": "unit", "value": "bytes"}, {"id": "decimals", "value": 2}]},
            {"matcher": {"id": "byName", "options": "Current Usage"},
             "properties": [{"id": "custom.displayMode", "value": "gradient-gauge"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 1073741824},
                    {"color": "#FF4040", "value": 10737418240}]}}]},
        ],
        sort_by=[{"displayName": "Current Usage", "desc": True}],
        footer_fields=["Current Usage", "Request", "Limit"]
    ))
    y += 8

    # ================================================================
    # ROW 5: CONTAINER LAYER ANALYSIS
    # ================================================================
    panels.append(row_panel("Container Layer & Log Analysis on /var", y)); y += 1

    # Per-container writable layer
    panels.append(stacked_ts(
        "Container Writable Layer Usage — Stacked by Container",
        "Each container's writable overlay layer. This is the 'container layer' on /var that "
        "grows when containers write to the filesystem (not to a volume).",
        {"h": 10, "w": 12, "x": 0, "y": y},
        [tgt(f'container_fs_usage_bytes{{{NSND}, container!="", container!="POD"}}',
             "{{pod}}/{{container}}")],
        axis_label="Writable Layer", unit="bytes"
    ))

    # Container log sizes (if available)
    panels.append(ts_panel(
        "Container Log Sizes Over Time",
        "Size of each container's log file tracked by kubelet. Large log files consume /var space. "
        "Uses kubelet_container_log_filesystem_used_bytes if available.",
        {"h": 10, "w": 12, "x": 12, "y": y},
        [tgt(f'kubelet_container_log_filesystem_used_bytes{{node=~"$node"}}',
             "{{pod}}/{{container}}")],
        axis_label="Log Size", unit="bytes"
    ))
    y += 10

    # Per-container I/O rates
    panels.append(ts_panel(
        "Container Filesystem Write Rate",
        "Rate of bytes written by each container. High write rates on /var indicate "
        "containers that are actively growing their writable layer or ephemeral files.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (pod, container) (rate(container_fs_writes_bytes_total{{{NSND}, container!=""}}[5m]))',
             "{{pod}}/{{container}}")],
        axis_label="Write Rate", unit="Bps"
    ))

    # Container filesystem read rate
    panels.append(ts_panel(
        "Container Filesystem Read Rate",
        "Rate of bytes read by each container from the filesystem.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (pod, container) (rate(container_fs_reads_bytes_total{{{NSND}, container!=""}}[5m]))',
             "{{pod}}/{{container}}")],
        axis_label="Read Rate", unit="Bps"
    ))
    y += 8

    # ================================================================
    # ROW 6: VOLUME ANALYSIS (PVC / EmptyDir)
    # ================================================================
    panels.append(row_panel("Volume Analysis — PVC & EmptyDir on /var", y)); y += 1

    # Volume usage table
    panels.append(table_p(
        "All Volumes — Capacity, Used, Available, Usage %",
        "PersistentVolumeClaims and EmptyDir volumes tracked by kubelet. "
        "These consume /var space when backed by the node's local filesystem.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kubelet_volume_stats_capacity_bytes{{node=~"$node"}}', "", fmt="table"),
            tgt(f'kubelet_volume_stats_used_bytes{{node=~"$node"}}', "", fmt="table"),
            tgt(f'kubelet_volume_stats_available_bytes{{node=~"$node"}}', "", fmt="table"),
            tgt(f'kubelet_volume_stats_used_bytes{{node=~"$node"}} / kubelet_volume_stats_capacity_bytes{{node=~"$node"}}', "", fmt="table"),
        ],
        transformations=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "job": True,
                                  "instance": True, "service": True, "endpoint": True,
                                  "prometheus": True},
                "renameByName": {
                    "node": "Node", "namespace": "Namespace",
                    "persistentvolumeclaim": "PVC Name",
                    "Value #A": "Capacity", "Value #B": "Used",
                    "Value #C": "Available", "Value #D": "Usage %"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byRegexp", "options": "Capacity|Used|Available"},
             "properties": [{"id": "unit", "value": "bytes"}, {"id": "decimals", "value": 2}]},
            {"matcher": {"id": "byName", "options": "Usage %"},
             "properties": [{"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 1},
                {"id": "custom.displayMode", "value": "gradient-gauge"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 0.75},
                    {"color": "#FF4040", "value": 0.9}]}}]},
        ],
        sort_by=[{"displayName": "Usage %", "desc": True}],
        footer_fields=["Capacity", "Used", "Available"]
    ))
    y += 8

    # Volume usage over time
    panels.append(ts_panel(
        "Volume Usage Over Time",
        "How volume usage changes over time. Each line = one PVC or EmptyDir.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'kubelet_volume_stats_used_bytes{{node=~"$node"}}',
             "{{namespace}}/{{persistentvolumeclaim}}")],
        axis_label="Used", unit="bytes"
    ))
    y += 8

    # ================================================================
    # TEMPLATING
    # ================================================================
    templating = {"list": [
        {"name": "datasource", "type": "datasource", "label": "Prometheus Data Source",
         "query": "prometheus", "current": {}, "hide": 0,
         "includeAll": False, "multi": False, "options": [],
         "refresh": 1, "regex": "", "skipUrlSync": False},
        {"name": "namespace", "type": "query", "label": "Namespace (multi-select)",
         "datasource": ds(),
         "definition": "label_values(kube_pod_info, namespace)",
         "query": {"query": "label_values(kube_pod_info, namespace)", "refId": "ns"},
         "current": {}, "hide": 0,
         "includeAll": True, "multi": True,
         "options": [], "refresh": 2, "regex": "", "sort": 1, "skipUrlSync": False},
        {"name": "node", "type": "query", "label": "Node (multi-select)",
         "datasource": ds(),
         "definition": 'label_values(kube_pod_info{namespace=~"$namespace"}, node)',
         "query": {"query": 'label_values(kube_pod_info{namespace=~"$namespace"}, node)', "refId": "nd"},
         "current": {}, "hide": 0,
         "includeAll": True, "multi": True,
         "options": [], "refresh": 2, "regex": "", "sort": 1, "skipUrlSync": False},
    ]}

    return {
        "__inputs": [], "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "9.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"}],
        "id": None, "uid": "k8s-node-storage-v1",
        "title": "K8s Node Storage & Pod Lifecycle",
        "description": "Pod lifecycle tracking, node filesystem usage across all mount points, "
                       "/var deep dive with per-pod ephemeral storage, container layers, and volume analysis.",
        "tags": ["kubernetes", "storage", "filesystem", "var", "ephemeral", "pods"],
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
    out = sys.argv[1] if len(sys.argv) > 1 else "k8s-node-storage-dashboard.json"
    d = build()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    pc = len(d["panels"])
    vc = len(d["templating"]["list"])
    print(f"Generated {out}: {pc} panels, {vc} template variables")
    for p in d["panels"]:
        print(f"  [{p['type']:12s}] {p.get('title', '')}")
