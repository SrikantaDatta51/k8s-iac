#!/usr/bin/env python3
"""Generate K8s Pod Details & Scheduler Metrics Dashboard - v2.
Focused on: rich pod info, phases, errors, kill/fail reasons,
deletion timestamps, scheduling delay from kube-state-metrics.
Removed: API server, etcd (not needed).
Scheduler: uses kube_pod_created vs kube_pod_start_time for scheduling delay.
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
        "options": {"legend": LEGEND_BTM, "tooltip": {"mode": "multi", "sort": "desc"}},
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
    # ROW 1: POD PHASES OVERVIEW
    # ================================================================
    panels.append(row("Pod Phases Overview", y)); y += 1

    phases = ["Running", "Pending", "Succeeded", "Failed", "Unknown"]
    colors = {"Running": "#73BF69", "Pending": "#FF9830", "Succeeded": "#5794F2",
              "Failed": "#FF4040", "Unknown": "#B877D9"}
    for i, ph in enumerate(phases):
        panels.append(stat(
            f"{ph} Pods", f"Current count of pods in {ph} phase",
            {"h": 3, "w": 4, "x": i * 4, "y": y},
            [tgt(f'count(kube_pod_status_phase{{{NS}, phase="{ph}"}} == 1) or vector(0)', ph, instant=True)],
            color_mode="value", text_mode="value",
            thresholds={"mode": "absolute", "steps": [{"color": colors[ph], "value": None}]}
        ))
    # Extra stat: total pods
    panels.append(stat(
        "Total Pods", "Total pod count across all phases",
        {"h": 3, "w": 4, "x": 20, "y": y},
        [tgt(f'count(kube_pod_info{{{NS}}}) or vector(0)', "Total", instant=True)],
        color_mode="value", text_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": "#5794F2", "value": None}]}
    ))
    y += 3

    # Pods by phase over time — stacked
    panels.append(stacked(
        "Pods by Phase Over Time",
        "Single query split by phase label. Each color = a phase. "
        "Height = total pod count.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'sum by (phase) (kube_pod_status_phase{{{NS}}} == 1)', "{{phase}}")],
        axis="Pod Count"
    ))
    y += 8

    # ================================================================
    # ROW 2: RICH POD TABLE with START + DELETION timestamps
    # ================================================================
    panels.append(row("All Pods — Start Time, Deletion Time, Uptime, Restarts", y)); y += 1

    # kube_pod_start_time * 1000 for ISO, kube_pod_deletion_timestamp * 1000 for deletion
    # time() - kube_pod_start_time for uptime, restarts total
    panels.append(tbl(
        "All Pods — Full Lifecycle Table",
        "Every pod with: Start Time (ISO), Deletion Time (if being deleted/terminated), "
        "Uptime (duration since start), Total Restarts. "
        "Deletion Time appears when a pod is being terminated or has been deleted. "
        "If Deletion Time is empty, the pod is still active.",
        {"h": 14, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_start_time{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'time() - kube_pod_start_time{{{NS}}}', "", fmt="table"),
            tgt(f'kube_pod_deletion_timestamp{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'sum by (pod, namespace) (kube_pod_container_status_restarts_total{{{NS}}})', "", fmt="table"),
        ],
        transforms=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "container": True, "endpoint": True, "prometheus": True,
                    "node": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace",
                    "Value #A": "Started At", "Value #B": "Uptime",
                    "Value #C": "Deleted At", "Value #D": "Total Restarts"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 320}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 150}]},
            {"matcher": {"id": "byName", "options": "Started At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Deleted At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"},
                {"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
            {"matcher": {"id": "byName", "options": "Uptime"},
             "properties": [{"id": "unit", "value": "dtdurations"}]},
            {"matcher": {"id": "byName", "options": "Total Restarts"},
             "properties": [{"id": "decimals", "value": 0},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 3},
                    {"color": "#FF4040", "value": 10}]}},
                {"id": "custom.displayMode", "value": "lcd-gauge"}]},
        ],
        sort=[{"displayName": "Started At", "desc": True}]
    ))
    y += 14

    # ================================================================
    # ROW 3: POD ERRORS — WHY PODS FAIL/GET KILLED
    # ================================================================
    panels.append(row("Pod Errors — Why Pods Fail, Get Killed, or Get Stuck", y)); y += 1

    # Containers WAITING — CrashLoopBackOff, ImagePullBackOff, etc.
    panels.append(ts(
        "Containers Stuck in Waiting State (by Reason)",
        "Containers that are NOT running — stuck waiting. "
        "CrashLoopBackOff = container keeps crashing and K8s is backing off restarts. "
        "ImagePullBackOff = cannot pull container image. "
        "CreateContainerConfigError = bad config (missing secret/configmap). "
        "ErrImagePull = image doesn't exist or no auth.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (reason) (kube_pod_container_status_waiting_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Containers Waiting"
    ))

    # Containers TERMINATED — OOMKilled, Error, etc.
    panels.append(ts(
        "Containers Killed or Terminated (by Reason)",
        "Containers that were forcefully stopped. "
        "OOMKilled = ran out of memory, K8s killed it. "
        "Error = container exited with non-zero code (application crash). "
        "Completed = finished normally (for Jobs). "
        "ContainerCannotRun = runtime error starting container. "
        "DeadlineExceeded = Job exceeded activeDeadlineSeconds.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (reason) (kube_pod_container_status_terminated_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Containers Terminated"
    ))
    y += 8

    # Tables: which SPECIFIC pods are waiting / last terminated
    panels.append(tbl(
        "Which Pods Are Stuck Right Now — Waiting Reasons",
        "List of pods with containers currently in Waiting state. "
        "These pods are NOT running. The Reason column tells you exactly why.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'kube_pod_container_status_waiting_reason{{{NS}}} == 1', "", fmt="table")],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "container": "Container",
                    "reason": "Why It Is Stuck"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 260}]},
            {"matcher": {"id": "byName", "options": "Why It Is Stuck"},
             "properties": [{"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
        ]
    ))

    panels.append(tbl(
        "Last Kill/Termination Reason per Container",
        "For each container, why it was LAST killed or terminated. "
        "OOMKilled = not enough memory limit. Error = app crashed. "
        "This persists even after restart so you can see the cause.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'kube_pod_container_status_last_terminated_reason{{{NS}}} == 1', "", fmt="table")],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "container": "Container",
                    "reason": "Kill Reason"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 260}]},
            {"matcher": {"id": "byName", "options": "Kill Reason"},
             "properties": [{"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
        ]
    ))
    y += 8

    # Pod Status Reasons (Evicted, NodeLost)
    panels.append(ts(
        "Pod-Level Status Reasons Over Time",
        "Pods with a special status reason: "
        "Evicted = pod was evicted by kubelet (disk pressure, memory pressure, PID pressure). "
        "NodeLost = node became unreachable. "
        "UnexpectedAdmissionError = admission webhook error.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (reason) (kube_pod_status_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Pods"
    ))

    # Readiness
    panels.append(ts(
        "Pod Readiness Over Time",
        "Ready = pod passes readiness probe, receiving traffic. "
        "Not Ready = pod exists but is NOT receiving traffic (failing readiness probe). "
        "High 'Not Ready' count = service degradation.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'count(kube_pod_status_ready{{{NS}, condition="true"}} == 1) or vector(0)', "Ready"),
         tgt(f'count(kube_pod_status_ready{{{NS}, condition="false"}} == 1) or vector(0)', "Not Ready")],
        axis="Pods"
    ))
    y += 8

    # ================================================================
    # ROW 4: RESTART ANALYSIS
    # ================================================================
    panels.append(row("Restart Analysis — Crash Loops & OOMKills", y)); y += 1

    panels.append(ts(
        "Total Restarts per Pod (cumulative)",
        "Cumulative restart count over time. A steep rising line = active crash loop. "
        "Flat line = stable pod. Each line = one pod.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (pod) (kube_pod_container_status_restarts_total{{{NS}}})', "{{pod}}")],
        axis="Restart Count"
    ))

    panels.append(ts(
        "Restart Rate per Pod (restarts/sec)",
        "Rate of restarts. Any sustained rate > 0 means the pod is actively cycling. "
        "Spikes indicate sudden failures (OOMKill, crash).",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (pod) (rate(kube_pod_container_status_restarts_total{{{NS}}}[5m]))', "{{pod}}")],
        axis="Restarts/sec"
    ))
    y += 8

    # ================================================================
    # ROW 5: SCHEDULING — using kube-state-metrics (works everywhere)
    # ================================================================
    panels.append(row("Pod Scheduling — Time to Schedule (from kube-state-metrics)", y)); y += 1

    # Key insight: scheduling delay = kube_pod_start_time - kube_pod_created
    # This measures: API creation → first container running
    # (includes: queue wait + scheduling + image pull + init containers)
    panels.append(ts(
        "Time from Pod Creation to Running (scheduling + startup delay)",
        "kube_pod_start_time - kube_pod_created = total time from when the pod object was "
        "created in the API until the first container started running. "
        "This includes: scheduler queue wait + scheduling decision + image pull + init containers. "
        "High values = scheduling delays, slow image pulls, or resource pressure.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [tgt(f'(kube_pod_start_time{{{NS}}} - kube_pod_created{{{NS}}}) > 0', "{{pod}}")],
        axis="Seconds to Start", unit="s"
    ))
    y += 10

    # Scheduling delay table — which pods took longest to schedule
    panels.append(tbl(
        "Pods by Scheduling Delay (longest first)",
        "How long each pod took from creation to first container start. "
        "Created At = when API received the pod spec. Started At = when first container ran. "
        "Delay = the gap (scheduling + image pull + init). "
        "Sort by Delay to find pods that took unusually long.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_created{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'kube_pod_start_time{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'kube_pod_start_time{{{NS}}} - kube_pod_created{{{NS}}}', "", fmt="table"),
        ],
        transforms=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "container": True, "endpoint": True, "prometheus": True,
                    "node": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace",
                    "Value #A": "Created At", "Value #B": "Started At",
                    "Value #C": "Delay (seconds)"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 320}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 150}]},
            {"matcher": {"id": "byName", "options": "Created At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Started At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Delay (seconds)"},
             "properties": [{"id": "unit", "value": "s"}, {"id": "decimals", "value": 1},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 30},
                    {"color": "#FF4040", "value": 120}]}},
                {"id": "custom.displayMode", "value": "lcd-gauge"}]},
        ],
        sort=[{"displayName": "Delay (seconds)", "desc": True}]
    ))
    y += 10

    # Scheduled vs Not Scheduled
    panels.append(ts(
        "Pods Scheduled vs Not Scheduled",
        "kube_pod_status_scheduled: condition=true means scheduler found a node. "
        "condition=false means no node is available (insufficient resources, "
        "taints/tolerations, node selectors, affinity rules).",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'count(kube_pod_status_scheduled{{{NS}, condition="true"}} == 1) or vector(0)', "Scheduled"),
         tgt(f'count(kube_pod_status_scheduled{{{NS}, condition="false"}} == 1) or vector(0)', "Not Scheduled (no node fits)")],
        axis="Pods"
    ))

    # Currently unscheduled pods table
    panels.append(tbl(
        "Currently Unscheduled Pods (waiting for a node)",
        "Pods where PodScheduled condition is False. These are stuck in Pending. "
        "Common reasons: insufficient CPU/memory/GPU, no matching node (taints, selectors), "
        "PVC not bound. Check Events via: kubectl describe pod <name>",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'kube_pod_status_scheduled{{{NS}, condition="false"}} == 1', "", fmt="table")],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True,
                    "condition": True},
                "renameByName": {"pod": "Pod", "namespace": "Namespace"}
            }}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 350}]},
        ]
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
    ]}

    return {
        "__inputs": [], "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "9.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"}],
        "id": None, "uid": "k8s-pod-details-v2",
        "title": "K8s Pod Details & Scheduling",
        "description": "Rich pod information: phases, start/deletion times, errors, kill reasons, "
                       "scheduling delay, readiness, restarts. Filtered by namespace.",
        "tags": ["kubernetes", "pods", "scheduler", "errors", "phases", "lifecycle"],
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
    out = sys.argv[1] if len(sys.argv) > 1 else "k8s-pod-details-dashboard.json"
    d = build()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    pc = len(d["panels"])
    vc = len(d["templating"]["list"])
    print(f"Generated {out}: {pc} panels, {vc} template variables")
    for p in d["panels"]:
        print(f"  [{p['type']:12s}] {p.get('title', '')}")
