#!/usr/bin/env python3
"""Generate K8s Pod Details & Scheduling Dashboard - v3.
Focused: rich pod lifecycle (start, completion, deletion, exit reason),
phase analysis, error/kill tracking, pending time analysis.
Uses ONLY kube-state-metrics (works in all K8s clusters).
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
    panels.append(stat(
        "Total Pods", "Total pod count across all phases",
        {"h": 3, "w": 4, "x": 20, "y": y},
        [tgt(f'count(kube_pod_info{{{NS}}}) or vector(0)', "Total", instant=True)],
        color_mode="value", text_mode="value",
        thresholds={"mode": "absolute", "steps": [{"color": "#5794F2", "value": None}]}
    ))
    y += 3

    # Pods by phase over time
    panels.append(stacked(
        "Pods by Phase Over Time",
        "Single query split by phase label. Each color = a phase.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'sum by (phase) (kube_pod_status_phase{{{NS}}} == 1)', "{{phase}}")],
        axis="Pod Count"
    ))
    y += 8

    # ================================================================
    # ROW 2: FULL POD LIFECYCLE TABLE
    # Started At, Completed At, Deleted At, Exit Reason, Uptime, Restarts
    # ================================================================
    panels.append(row("Full Pod Lifecycle — Start, End, Exit Reason", y)); y += 1

    panels.append(tbl(
        "All Pods — Full Lifecycle Table",
        "Every pod with complete lifecycle timestamps:\n"
        "• Started At = kube_pod_start_time (when first container started)\n"
        "• Completed At = kube_pod_completion_time (when pod finished, for Jobs/completed pods)\n"
        "• Deleted At = kube_pod_deletion_timestamp (when pod deletion was requested)\n"
        "• Exit Reason = kube_pod_container_status_last_terminated_reason (OOMKilled, Error, Completed, etc.)\n"
        "• Uptime = how long since pod started\n"
        "• Total Restarts = cumulative container restart count\n\n"
        "If Completed/Deleted columns are empty, the pod is still active.",
        {"h": 16, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_start_time{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'time() - kube_pod_start_time{{{NS}}}', "", fmt="table"),
            tgt(f'kube_pod_completion_time{{{NS}}} * 1000', "", fmt="table"),
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
                    "Value #A": "Started At",
                    "Value #B": "Uptime",
                    "Value #C": "Completed At",
                    "Value #D": "Deleted At",
                    "Value #E": "Total Restarts"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 280}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 130}]},
            {"matcher": {"id": "byName", "options": "Started At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"},
                {"id": "custom.width", "value": 170}]},
            {"matcher": {"id": "byName", "options": "Completed At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"},
                {"id": "custom.width", "value": 170},
                {"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#5794F2", "value": None}]}}]},
            {"matcher": {"id": "byName", "options": "Deleted At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"},
                {"id": "custom.width", "value": 170},
                {"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
            {"matcher": {"id": "byName", "options": "Uptime"},
             "properties": [{"id": "unit", "value": "dtdurations"},
                {"id": "custom.width", "value": 120}]},
            {"matcher": {"id": "byName", "options": "Total Restarts"},
             "properties": [{"id": "decimals", "value": 0},
                {"id": "custom.width", "value": 130},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 3},
                    {"color": "#FF4040", "value": 10}]}},
                {"id": "custom.displayMode", "value": "lcd-gauge"}]},
        ],
        sort=[{"displayName": "Started At", "desc": True}]
    ))
    y += 16

    # Exit reason table — separate, more detailed
    panels.append(tbl(
        "Container Exit Reasons — Last Termination per Container",
        "For every container, the reason it was last terminated:\n"
        "• OOMKilled = container exceeded memory limit, killed by K8s\n"
        "• Error = container exited with non-zero exit code (application crash)\n"
        "• Completed = container finished normally (exit code 0)\n"
        "• ContainerCannotRun = container runtime error\n"
        "• DeadlineExceeded = Job exceeded activeDeadlineSeconds\n"
        "• Evicted = pod evicted by kubelet (disk/memory pressure)\n\n"
        "This shows the most recent termination — useful for diagnosing crash loops.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [tgt(f'kube_pod_container_status_last_terminated_reason{{{NS}}} == 1', "", fmt="table")],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True,
                    "node": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "container": "Container",
                    "reason": "Exit / Kill Reason"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 280}]},
            {"matcher": {"id": "byName", "options": "Container"}, "properties": [{"id": "custom.width", "value": 180}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 130}]},
            {"matcher": {"id": "byName", "options": "Exit / Kill Reason"},
             "properties": [
                {"id": "custom.displayMode", "value": "color-text"},
                {"id": "custom.width", "value": 200},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
        ],
        sort=[{"displayName": "Exit / Kill Reason", "desc": False}]
    ))
    y += 10

    # ================================================================
    # ROW 3: POD ERRORS — WAITING/TERMINATED/EVICTED
    # ================================================================
    panels.append(row("Pod Errors — Waiting, Killed, Evicted", y)); y += 1

    panels.append(ts(
        "Containers Stuck in Waiting State (by Reason)",
        "Containers NOT running — stuck waiting.\n"
        "• CrashLoopBackOff = keeps crashing, K8s backing off restarts\n"
        "• ImagePullBackOff / ErrImagePull = cannot pull image\n"
        "• CreateContainerConfigError = missing secret/configmap\n"
        "• ContainerCreating = still starting up (normal if brief)",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (reason) (kube_pod_container_status_waiting_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Containers Waiting"
    ))

    panels.append(ts(
        "Containers Killed or Terminated (by Reason)",
        "Containers that were forcefully stopped.\n"
        "• OOMKilled = ran out of memory\n"
        "• Error = exited non-zero (app crash)\n"
        "• Completed = finished normally\n"
        "• ContainerCannotRun = runtime error",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (reason) (kube_pod_container_status_terminated_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Containers Terminated"
    ))
    y += 8

    # Which pods are stuck right now
    panels.append(tbl(
        "Which Pods Are Stuck Right Now",
        "Pods with containers in Waiting state. These are NOT running.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'kube_pod_container_status_waiting_reason{{{NS}}} == 1', "", fmt="table")],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "container": "Container",
                    "reason": "Why Stuck"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 260}]},
            {"matcher": {"id": "byName", "options": "Why Stuck"},
             "properties": [{"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
        ]
    ))

    # Pod status reasons (Evicted, NodeLost)
    panels.append(ts(
        "Pod Status Reasons (Evicted, NodeLost, etc.)",
        "• Evicted = kubelet evicted the pod (disk/memory/PID pressure)\n"
        "• NodeLost = node became unreachable\n"
        "• UnexpectedAdmissionError = admission webhook error",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (reason) (kube_pod_status_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Pods"
    ))
    y += 8

    # Readiness
    panels.append(ts(
        "Pod Readiness — Ready vs Not Ready",
        "Ready = passing readiness probe, receiving traffic. "
        "Not Ready = exists but NOT receiving traffic.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'count(kube_pod_status_ready{{{NS}, condition="true"}} == 1) or vector(0)', "Ready"),
         tgt(f'count(kube_pod_status_ready{{{NS}, condition="false"}} == 1) or vector(0)', "Not Ready")],
        axis="Pods"
    ))

    # Restart rate
    panels.append(ts(
        "Container Restart Rate (restarts/sec)",
        "Rate of restarts per pod. Any sustained rate > 0 = pod is crash-looping.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (pod) (rate(kube_pod_container_status_restarts_total{{{NS}}}[5m]))', "{{pod}}")],
        axis="Restarts/sec"
    ))
    y += 8

    # ================================================================
    # ROW 4: PENDING POD ANALYSIS
    # ================================================================
    panels.append(row("Pending Pod Analysis — How Long Pods Wait Before Running", y)); y += 1

    # Currently pending pods — how long they've been pending
    # For pending pods, start_time doesn't exist yet, but created does.
    # We try multiple approaches:
    # 1. kube_pod_created if available → time() - kube_pod_created for pending pods
    # 2. Track phase changes over time

    # Approach: show pending pods count over time + table of those pending
    panels.append(ts(
        "Pending Pods Over Time",
        "How many pods are in Pending state at any point. A rising trend = "
        "cluster cannot schedule pods fast enough (resource pressure, "
        "taints, node selectors, PVC issues).",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'count(kube_pod_status_phase{{{NS}, phase="Pending"}} == 1) or vector(0)', "Pending Pods"),
         tgt(f'count(kube_pod_status_phase{{{NS}, phase="Running"}} == 1) or vector(0)', "Running Pods")],
        axis="Pods"
    ))

    # Pods stuck in Pending — show which ones
    panels.append(ts(
        "Individual Pods in Pending State",
        "Each line = a pod currently in Pending. If a line persists for minutes, "
        "the pod cannot be scheduled. Check events for the reason.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'kube_pod_status_phase{{{NS}, phase="Pending"}} == 1', "{{pod}}")],
        axis="Pending (1=yes)"
    ))
    y += 8

    # Pending pods table with time in pending
    # kube_pod_created gives creation timestamp. For pending pods that haven't started:
    # pending_duration = time() - kube_pod_created (if the metric exists)
    # We provide TWO queries — one using kube_pod_created, one using kube_pod_start_time
    # The created one shows pending time, the start one shows total lifetime
    panels.append(tbl(
        "Currently Pending Pods — How Long They Have Been Waiting",
        "Pods currently in Pending phase. Shows:\n"
        "• Created At = when the pod spec was submitted to the API (kube_pod_created * 1000)\n"
        "• Pending Duration = time() - kube_pod_created (how long it's been waiting)\n\n"
        "If Created At shows empty or 1970, the kube_pod_created metric may not be "
        "available in your kube-state-metrics version. In that case, use "
        "'kubectl get pod -o wide' to check creation times.\n\n"
        "Common reasons for being stuck in Pending:\n"
        "- Insufficient CPU/Memory/GPU on any node\n"
        "- Node taints with no matching tolerations\n"
        "- Node selector / affinity rules no node matches\n"
        "- PVC not bound (storage not available)\n"
        "- Too many pods on node (PodLimit)",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [
            # Only show pods that are in Pending phase
            # We filter by phase=Pending using the phase metric, then join
            tgt(f'(kube_pod_status_phase{{{NS}, phase="Pending"}} == 1) * 0 + kube_pod_created{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'(kube_pod_status_phase{{{NS}, phase="Pending"}} == 1) * 0 + (time() - kube_pod_created{{{NS}}})', "", fmt="table"),
        ],
        transforms=[
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "container": True, "endpoint": True, "prometheus": True,
                    "node": True, "phase": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace",
                    "Value #A": "Created At",
                    "Value #B": "Pending Duration"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 350}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 150}]},
            {"matcher": {"id": "byName", "options": "Created At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Pending Duration"},
             "properties": [{"id": "unit", "value": "dtdurations"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 60},
                    {"color": "#FF4040", "value": 300}]}},
                {"id": "custom.displayMode", "value": "lcd-gauge"}]},
        ],
        sort=[{"displayName": "Pending Duration", "desc": True}]
    ))
    y += 10

    # Fallback: simple unscheduled pods table (no dependency on kube_pod_created)
    panels.append(ts(
        "Pods: Scheduled vs Not Scheduled",
        "kube_pod_status_scheduled condition=true: scheduler found a node.\n"
        "condition=false: no suitable node (insufficient resources, taints).\n"
        "All 'Not Scheduled' pods are a subset of Pending pods.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'count(kube_pod_status_scheduled{{{NS}, condition="true"}} == 1) or vector(0)', "Scheduled"),
         tgt(f'count(kube_pod_status_scheduled{{{NS}, condition="false"}} == 1) or vector(0)', "Not Scheduled")],
        axis="Pods"
    ))

    panels.append(tbl(
        "Unscheduled Pods (scheduler cannot find a node)",
        "These pods have PodScheduled=False. The scheduler tried and failed.\n"
        "Run: kubectl describe pod <name> | grep Events\n"
        "to see the exact reason (e.g. 'Insufficient nvidia.com/gpu').",
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
    # ROW 5: HISTORICAL SCHEDULING DELAY
    # (for pods that DID get scheduled — how long did it take)
    # ================================================================
    panels.append(row("Historical Scheduling Delay (for pods that did start)", y)); y += 1

    # Use kube_pod_start_time - kube_pod_created
    # If kube_pod_created doesn't exist, this shows "No data"
    panels.append(ts(
        "Time from Creation to Running (per pod)",
        "kube_pod_start_time - kube_pod_created = total delay from API submission "
        "to first container running. Includes: scheduling + image pull + init containers.\n\n"
        "NOTE: Requires kube_pod_created metric (kube-state-metrics v1.6+). "
        "If this shows 'No data', your kube-state-metrics may not expose kube_pod_created.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'(kube_pod_start_time{{{NS}}} - on(pod, namespace) kube_pod_created{{{NS}}}) > 0', "{{pod}}")],
        axis="Delay (seconds)", unit="s"
    ))

    # Alternative: just show start times as a timeline
    panels.append(ts(
        "Pod Start Times (when pods went Running)",
        "Shows when each pod transitioned to Running. Useful for correlating "
        "with cluster events (scaling, deployments, node additions).",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'changes(kube_pod_start_time{{{NS}}}[5m])', "{{pod}}")],
        axis="Starts"
    ))
    y += 8

    # Scheduling delay table
    panels.append(tbl(
        "Pods by Startup Delay (longest first)",
        "How long each pod took from creation to first container start. "
        "Sorted by longest delay.\n\n"
        "NOTE: Requires kube_pod_created metric. If empty, this metric is not "
        "available in your cluster.",
        {"h": 10, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_created{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'kube_pod_start_time{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'kube_pod_start_time{{{NS}}} - on(pod, namespace) kube_pod_created{{{NS}}}', "", fmt="table"),
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
                    "Value #C": "Startup Delay"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 280}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 130}]},
            {"matcher": {"id": "byName", "options": "Created At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Started At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
            {"matcher": {"id": "byName", "options": "Startup Delay"},
             "properties": [{"id": "unit", "value": "s"}, {"id": "decimals", "value": 1},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 30},
                    {"color": "#FF4040", "value": 120}]}},
                {"id": "custom.displayMode", "value": "lcd-gauge"}]},
        ],
        sort=[{"displayName": "Startup Delay", "desc": True}]
    ))
    y += 10

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
        "id": None, "uid": "k8s-pod-details-v3",
        "title": "K8s Pod Details & Scheduling",
        "description": "Rich pod lifecycle: phases, start/completion/deletion times, exit reasons, "
                       "pending analysis, scheduling delay, readiness, restarts.",
        "tags": ["kubernetes", "pods", "lifecycle", "errors", "phases", "scheduling"],
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
    out = sys.argv[1] if len(sys.argv) > 1 else "k8s-pod-details-dashboard.json"
    d = build()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    pc = len(d["panels"])
    vc = len(d["templating"]["list"])
    print(f"Generated {out}: {pc} panels, {vc} template variables")
    for p in d["panels"]:
        print(f"  [{p['type']:12s}] {p.get('title', '')}")
