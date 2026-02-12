#!/usr/bin/env python3
"""Generate K8s Node Storage & Pod Lifecycle Dashboard - v2.
Simplified: one-query pod status, fixed start time unit, filesystem queries
without node label dependency, ephemeral/emptydir focus.
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

LEGEND = {"displayMode": "table", "placement": "right",
          "calcs": ["min", "max", "mean", "lastNotNull"]}
LEGEND_BTM = {"displayMode": "table", "placement": "bottom",
              "calcs": ["min", "max", "mean", "lastNotNull"]}

def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}

def stat(title, desc, gp, targets, unit="none", decimals=0,
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

def gauge(title, desc, gp, targets, unit="percentunit", mx=1):
    return {
        "id": nid(), "title": title, "description": desc, "type": "gauge",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 1, "min": 0, "max": mx,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None},
                {"color": "#FF9830", "value": mx * 0.75},
                {"color": "#FF4040", "value": mx * 0.9}]}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
            "showThresholdLabels": True, "showThresholdMarkers": True},
        "targets": refs(targets)
    }

def ts(title, desc, gp, targets, axis, unit="short", overrides=None):
    return {
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 2, "fillOpacity": 15, "gradientMode": "none",
                "axisLabel": axis, "drawStyle": "line", "pointSize": 5,
                "showPoints": "auto", "spanNulls": True}},
            "overrides": overrides or []},
        "options": {"legend": LEGEND, "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs(targets)
    }

def stacked(title, desc, gp, targets, axis, unit="short"):
    return {
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 0, "fillOpacity": 80, "gradientMode": "none",
                "axisLabel": axis, "drawStyle": "bars",
                "stacking": {"mode": "normal"}, "showPoints": "never"}},
            "overrides": []},
        "options": {"legend": LEGEND, "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs(targets)
    }

def tbl(title, desc, gp, targets, transforms=None, overrides=None,
        sort=None, footer=None):
    return {
        "id": nid(), "title": title, "description": desc, "type": "table",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": overrides or []},
        "options": {"showHeader": True, "sortBy": sort or [],
            "footer": {"show": bool(footer), "reducer": ["sum"], "fields": footer or []}},
        "transformations": transforms or [],
        "targets": refs(targets)
    }


def build():
    panels = []
    y = 0

    # ================================================================
    # ROW 1: POD LIFECYCLE — SIMPLE
    # ================================================================
    panels.append(row("Pod Lifecycle", y)); y += 1

    # ONE simple query: pod count by phase — no joins, no node filter
    panels.append(ts(
        "Pods by Phase Over Time",
        "One query: sum by (phase) kube_pod_status_phase. Shows Running, Pending, "
        "Succeeded, Failed, Unknown all in one graph.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (phase) (kube_pod_status_phase{{{NS}}} == 1)', "{{phase}}")],
        axis="Pod Count", unit="short"
    ))

    # Restart rate per pod
    panels.append(ts(
        "Container Restart Rate per Pod",
        "Rate of container restarts. Spikes mean crash loops or OOMKills.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (pod) (rate(kube_pod_container_status_restarts_total{{{NS}}}[5m]))', "{{pod}}")],
        axis="Restarts/sec", unit="short"
    ))
    y += 8

    # Pod table: start time, uptime, phase — NO node filter on these metrics
    # kube_pod_start_time is unix SECONDS, dateTimeAsIso needs MILLISECONDS → multiply by 1000
    panels.append(tbl(
        "All Pods — Start Time, Phase, Uptime",
        "Simple pod list. Start time, uptime, and phase from kube-state-metrics. "
        "No node filter since these metrics do not carry a node label.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_start_time{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'time() - kube_pod_start_time{{{NS}}}', "", fmt="table"),
        ],
        transforms=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "container": True, "endpoint": True, "prometheus": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "node": "Node",
                    "Value #A": "Started At", "Value #B": "Uptime"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 300}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 140}]},
            {"matcher": {"id": "byName", "options": "Started At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Uptime"},
             "properties": [{"id": "unit", "value": "dtdurations"}]},
        ],
        sort=[{"displayName": "Started At", "desc": True}]
    ))
    y += 10

    # ================================================================
    # ROW 2: PER-POD EPHEMERAL STORAGE (container_fs_usage_bytes)
    # ================================================================
    panels.append(row("Per-Pod Ephemeral Storage Usage (container_fs_usage_bytes)", y)); y += 1

    # Stacked per-pod
    panels.append(stacked(
        "Ephemeral Storage per Pod — Stacked",
        "Each color = a pod. container_fs_usage_bytes tracks each container's writable layer "
        "and ephemeral writes (typically on /var). Height = total across all pods.",
        {"h": 10, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (pod) (container_fs_usage_bytes{{{NS}, container!=""}})', "{{pod}}")],
        axis="Bytes", unit="bytes"
    ))

    # Individual lines per pod
    panels.append(ts(
        "Ephemeral Storage per Pod — Individual",
        "Each line = one pod. Compare against ephemeral-storage limits (dashed red).",
        {"h": 10, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (pod) (container_fs_usage_bytes{{{NS}, container!=""}})', "{{pod}} Used"),
         tgt(f'sum by (pod) (kube_pod_container_resource_limits{{{NS}, resource=~"ephemeral.storage"}})', "{{pod}} Limit")],
        axis="Bytes", unit="bytes",
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

    # Top pods by ephemeral usage table
    panels.append(tbl(
        "Top Pods by Ephemeral Storage",
        "Pods ranked by container filesystem usage. Shows usage, request, and limit.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [
            tgt(f'sum by (pod, namespace) (container_fs_usage_bytes{{{NS}, container!=""}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace) (kube_pod_container_resource_requests{{{NS}, resource=~"ephemeral.storage"}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace) (kube_pod_container_resource_limits{{{NS}, resource=~"ephemeral.storage"}})', "", fmt="table"),
        ],
        transforms=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace",
                    "Value #A": "Current Usage", "Value #B": "Request", "Value #C": "Limit"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 300}]},
            {"matcher": {"id": "byRegexp", "options": "Current Usage|Request|Limit"},
             "properties": [{"id": "unit", "value": "bytes"}, {"id": "decimals", "value": 2}]},
        ],
        sort=[{"displayName": "Current Usage", "desc": True}],
        footer=["Current Usage", "Request", "Limit"]
    ))
    y += 8

    # Per-container breakdown
    panels.append(stacked(
        "Ephemeral Storage by Container (writable layer)",
        "Per-container writable layer size. Each container writes to an overlay filesystem, "
        "this metric tracks that layer. Pod/container granularity.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'container_fs_usage_bytes{{{NS}, container!="", container!="POD"}}',
             "{{pod}}/{{container}}")],
        axis="Writable Layer", unit="bytes"
    ))
    y += 8

    # ================================================================
    # ROW 3: NODE FILESYSTEM (/var and all mounts)
    # ================================================================
    panels.append(row("Node Filesystem — /var and All Mount Points", y)); y += 1

    # Usage % per mountpoint — no node filter, just show everything
    panels.append(ts(
        "Filesystem Usage % — All Mount Points",
        "Each line = a mount point on any node. Shows how full each filesystem is. "
        "node_filesystem metrics come from node-exporter. If empty, node-exporter may not "
        "be installed or metrics may use 'instance' instead of 'node' label.",
        {"h": 10, "w": 12, "x": 0, "y": y},
        [tgt('1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"})',
             "{{instance}}:{{mountpoint}}")],
        axis="Usage %", unit="percentunit"
    ))

    # /var specific
    panels.append(ts(
        "/var Usage % Over Time",
        "Specifically tracks /var and /var/* mount points. /var is where Kubernetes stores "
        "container images, overlayfs layers, logs, and ephemeral volumes.",
        {"h": 10, "w": 12, "x": 12, "y": y},
        [tgt('1 - (node_filesystem_avail_bytes{mountpoint=~"/var.*", fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{mountpoint=~"/var.*", fstype!~"tmpfs|overlay"})',
             "{{instance}}:{{mountpoint}} ({{device}})")],
        axis="/var Usage %", unit="percentunit"
    ))
    y += 10

    # Filesystem used bytes over time
    panels.append(ts(
        "Used Bytes Over Time — All Filesystems",
        "Absolute bytes used on each filesystem. Each line = one mount point.",
        {"h": 10, "w": 12, "x": 0, "y": y},
        [tgt('node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"} - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}',
             "{{instance}}:{{mountpoint}}")],
        axis="Used", unit="bytes"
    ))

    # /var used bytes vs total capacity
    panels.append(ts(
        "/var Used vs Total Capacity",
        "Red dashed = total /var capacity. Blue = used. Gap = free space.",
        {"h": 10, "w": 12, "x": 12, "y": y},
        [tgt('node_filesystem_size_bytes{mountpoint=~"/var.*", fstype!~"tmpfs|overlay"} - node_filesystem_avail_bytes{mountpoint=~"/var.*", fstype!~"tmpfs|overlay"}',
             "Used ({{instance}}:{{mountpoint}})"),
         tgt('node_filesystem_size_bytes{mountpoint=~"/var.*", fstype!~"tmpfs|overlay"}',
             "Total ({{instance}}:{{mountpoint}})")],
        axis="Bytes", unit="bytes",
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
    y += 10

    # Filesystem table
    panels.append(tbl(
        "All Filesystems — Current Status",
        "Every filesystem reported by node-exporter. Shows device, mount point, FS type, "
        "size, used, available, and usage %. Uses 'instance' label for node identity.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [
            tgt('node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"}', "", fmt="table"),
            tgt('node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"} - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}', "", fmt="table"),
            tgt('node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}', "", fmt="table"),
            tgt('1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"})', "", fmt="table"),
        ],
        transforms=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "job": True,
                    "service": True, "endpoint": True, "prometheus": True, "container": True},
                "renameByName": {
                    "instance": "Node", "mountpoint": "Mount Point", "device": "Device",
                    "fstype": "FS Type",
                    "Value #A": "Total Size", "Value #B": "Used",
                    "Value #C": "Available", "Value #D": "Usage %"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Node"}, "properties": [{"id": "custom.width", "value": 200}]},
            {"matcher": {"id": "byName", "options": "Mount Point"}, "properties": [{"id": "custom.width", "value": 180}]},
            {"matcher": {"id": "byName", "options": "Device"}, "properties": [{"id": "custom.width", "value": 200}]},
            {"matcher": {"id": "byRegexp", "options": "Total Size|Used|Available"},
             "properties": [{"id": "unit", "value": "bytes"}, {"id": "decimals", "value": 2}]},
            {"matcher": {"id": "byName", "options": "Usage %"},
             "properties": [{"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 1},
                {"id": "custom.displayMode", "value": "lcd-gauge"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 0.75},
                    {"color": "#FF4040", "value": 0.9}]}}]},
        ],
        sort=[{"displayName": "Usage %", "desc": True}]
    ))
    y += 8

    # ================================================================
    # ROW 4: EMPTYDIR / VOLUME ANALYSIS
    # ================================================================
    panels.append(row("EmptyDir & Volume Usage Inside Pods", y)); y += 1

    # kubelet_volume_stats — tracks emptyDir and PVC usage
    panels.append(ts(
        "Volume Usage Over Time (EmptyDir + PVC)",
        "kubelet_volume_stats_used_bytes tracks EmptyDir and PVC volumes mounted inside pods. "
        "EmptyDir volumes live on /var/lib/kubelet, consuming /var space.",
        {"h": 10, "w": 12, "x": 0, "y": y},
        [tgt(f'kubelet_volume_stats_used_bytes{{{NS}}}',
             "{{namespace}}/{{persistentvolumeclaim}}")],
        axis="Used", unit="bytes"
    ))

    # Volume usage as % of capacity
    panels.append(ts(
        "Volume Usage % (EmptyDir + PVC)",
        "How full each volume is. EmptyDir capacity = node ephemeral storage limit.",
        {"h": 10, "w": 12, "x": 12, "y": y},
        [tgt(f'kubelet_volume_stats_used_bytes{{{NS}}} / kubelet_volume_stats_capacity_bytes{{{NS}}}',
             "{{namespace}}/{{persistentvolumeclaim}}")],
        axis="Usage %", unit="percentunit"
    ))
    y += 10

    # Volume table
    panels.append(tbl(
        "All Volumes — Capacity, Used, Available",
        "EmptyDir and PVC volumes tracked by kubelet. Shows capacity, used, available.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kubelet_volume_stats_capacity_bytes{{{NS}}}', "", fmt="table"),
            tgt(f'kubelet_volume_stats_used_bytes{{{NS}}}', "", fmt="table"),
            tgt(f'kubelet_volume_stats_available_bytes{{{NS}}}', "", fmt="table"),
            tgt(f'kubelet_volume_stats_used_bytes{{{NS}}} / kubelet_volume_stats_capacity_bytes{{{NS}}}', "", fmt="table"),
        ],
        transforms=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "job": True,
                    "instance": True, "service": True, "endpoint": True, "prometheus": True},
                "renameByName": {
                    "node": "Node", "namespace": "Namespace",
                    "persistentvolumeclaim": "Volume Name",
                    "Value #A": "Capacity", "Value #B": "Used",
                    "Value #C": "Available", "Value #D": "Usage %"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byRegexp", "options": "Capacity|Used|Available"},
             "properties": [{"id": "unit", "value": "bytes"}, {"id": "decimals", "value": 2}]},
            {"matcher": {"id": "byName", "options": "Usage %"},
             "properties": [{"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 1},
                {"id": "custom.displayMode", "value": "lcd-gauge"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 0.75},
                    {"color": "#FF4040", "value": 0.9}]}}]},
        ],
        sort=[{"displayName": "Usage %", "desc": True}],
        footer=["Capacity", "Used", "Available"]
    ))
    y += 8

    # ================================================================
    # ROW 5: I/O RATES
    # ================================================================
    panels.append(row("Container Filesystem I/O Rates", y)); y += 1

    panels.append(ts(
        "Container Write Rate (to ephemeral storage)",
        "Bytes/sec written by each container. High rates = actively filling /var.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (pod) (rate(container_fs_writes_bytes_total{{{NS}, container!=""}}[5m]))', "{{pod}}")],
        axis="Write Rate", unit="Bps"
    ))

    panels.append(ts(
        "Container Read Rate (from ephemeral storage)",
        "Bytes/sec read by each container from its filesystem.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (pod) (rate(container_fs_reads_bytes_total{{{NS}, container!=""}}[5m]))', "{{pod}}")],
        axis="Read Rate", unit="Bps"
    ))
    y += 8

    # ================================================================
    # TEMPLATING — only 2 vars: datasource + namespace
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
    ]}

    return {
        "__inputs": [], "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "9.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"}],
        "id": None, "uid": "k8s-node-storage-v2",
        "title": "K8s Node Storage & Pod Lifecycle",
        "description": "Pod lifecycle, per-pod ephemeral storage, node filesystem (/var deep dive), "
                       "EmptyDir/PVC volume tracking, container I/O rates.",
        "tags": ["kubernetes", "storage", "filesystem", "ephemeral", "pods", "var"],
        "style": "dark", "timezone": "browser", "editable": True,
        "graphTooltip": 1, "fiscalYearStartMonth": 0, "liveNow": False,
        "refresh": "30s", "schemaVersion": 38, "version": 2,
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
