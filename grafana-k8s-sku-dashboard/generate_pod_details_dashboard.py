#!/usr/bin/env python3
"""Generate K8s Pod Details & Scheduler Metrics Grafana Dashboard.
Rich pod information: phases, errors, container status, scheduling latency,
API server health. All filtered by namespace.
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
        "options": {"legend": LEGEND, "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs(targets)
    }

def histo(title, desc, gp, targets, axis, unit="s"):
    """Histogram / heatmap-style timeseries for latency distributions."""
    return {
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 2, "fillOpacity": 20, "gradientMode": "none",
                "axisLabel": axis, "drawStyle": "line", "pointSize": 4,
                "showPoints": "auto", "spanNulls": True}},
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

    # Summary stats — current counts
    phases = ["Running", "Pending", "Succeeded", "Failed", "Unknown"]
    colors = {"Running": "#73BF69", "Pending": "#FF9830", "Succeeded": "#5794F2",
              "Failed": "#FF4040", "Unknown": "#B877D9"}
    for i, ph in enumerate(phases):
        w = 4 if i < 4 else 8
        x = i * 4 if i < 4 else 16
        panels.append(stat(
            f"{ph} Pods", f"Current count of pods in {ph} phase",
            {"h": 3, "w": w, "x": x, "y": y},
            [tgt(f'count(kube_pod_status_phase{{{NS}, phase="{ph}"}} == 1) or vector(0)', ph, instant=True)],
            color_mode="value", text_mode="value",
            thresholds={"mode": "absolute", "steps": [{"color": colors[ph], "value": None}]}
        ))
    y += 3

    # Pods by phase over time — single query, split by phase label
    panels.append(stacked(
        "Pods by Phase Over Time",
        "One query, split by phase label. Shows the distribution of all pod phases "
        "over time. Each color = a phase (Running, Pending, Succeeded, Failed, Unknown).",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt(f'sum by (phase) (kube_pod_status_phase{{{NS}}} == 1)', "{{phase}}")],
        axis="Pod Count"
    ))
    y += 8

    # ================================================================
    # ROW 2: RICH POD DETAILS TABLE
    # ================================================================
    panels.append(row("All Pods — Rich Details", y)); y += 1

    # Main pod table: name, namespace, start time, uptime, restarts, ready, phase
    panels.append(tbl(
        "All Pods — Name, Namespace, Start Time, Uptime, Restarts",
        "Every pod with rich details. Start time is in ISO format (kube_pod_start_time * 1000). "
        "Restarts = total container restart count. Sorted by most recently started.",
        {"h": 12, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_start_time{{{NS}}} * 1000', "", fmt="table"),
            tgt(f'time() - kube_pod_start_time{{{NS}}}', "", fmt="table"),
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
                    "Value #C": "Total Restarts"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 320}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 150}]},
            {"matcher": {"id": "byName", "options": "Started At"},
             "properties": [{"id": "unit", "value": "dateTimeAsIso"}]},
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
    y += 12

    # ================================================================
    # ROW 3: POD CONTAINER STATUS — WAITING/TERMINATED REASONS
    # ================================================================
    panels.append(row("Container Status — Errors, Waiting, Terminated", y)); y += 1

    # Containers waiting with reasons
    panels.append(ts(
        "Containers Waiting (by Reason)",
        "Containers in Waiting state. Common reasons: CrashLoopBackOff, ImagePullBackOff, "
        "ErrImagePull, CreateContainerConfigError. Each line = a reason.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (reason) (kube_pod_container_status_waiting_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Containers"
    ))

    # Containers terminated with reasons
    panels.append(ts(
        "Containers Terminated (by Reason)",
        "Containers that were terminated. Reasons: OOMKilled, Error, Completed, "
        "ContainerCannotRun, DeadlineExceeded. Spikes indicate problems.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (reason) (kube_pod_container_status_terminated_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Containers"
    ))
    y += 8

    # Per-pod waiting/error detail table
    panels.append(tbl(
        "Pods with Container Errors — Waiting Reasons",
        "Pods that have containers currently in Waiting state. Shows the reason. "
        "Filter to see which specific pods are stuck and why.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [
            tgt(f'kube_pod_container_status_waiting_reason{{{NS}}} == 1', "", fmt="table"),
        ],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "container": "Container",
                    "reason": "Waiting Reason"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 280}]},
            {"matcher": {"id": "byName", "options": "Waiting Reason"},
             "properties": [{"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
        ],
        sort=[{"displayName": "Waiting Reason", "desc": False}]
    ))

    # Last terminated reasons
    panels.append(tbl(
        "Pods — Last Terminated Reason",
        "Shows the most recent termination reason for each container. "
        "OOMKilled means the container ran out of memory. Error means it exited non-zero.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [
            tgt(f'kube_pod_container_status_last_terminated_reason{{{NS}}} == 1', "", fmt="table"),
        ],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace", "container": "Container",
                    "reason": "Last Terminated Reason"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 280}]},
            {"matcher": {"id": "byName", "options": "Last Terminated Reason"},
             "properties": [{"id": "custom.displayMode", "value": "color-text"},
                {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                    {"color": "#FF4040", "value": None}]}}]},
        ]
    ))
    y += 8

    # Restart count per pod over time
    panels.append(ts(
        "Container Restarts per Pod Over Time",
        "Total restart count per pod. A continuously rising line = crash loop. "
        "Flat line = stable. Each line = a pod.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (pod) (kube_pod_container_status_restarts_total{{{NS}}})', "{{pod}}")],
        axis="Restart Count"
    ))

    # Restart rate per pod
    panels.append(ts(
        "Container Restart Rate per Pod",
        "Rate of restarts (restarts/sec). Spikes indicate crash loops or OOMKills. "
        "Sustained rate > 0 = pod is cycling.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'sum by (pod) (rate(kube_pod_container_status_restarts_total{{{NS}}}[5m]))', "{{pod}}")],
        axis="Restarts/sec"
    ))
    y += 8

    # Pod status reason (Evicted, NodeLost, etc.)
    panels.append(ts(
        "Pod Status Reasons (Evicted, NodeLost, etc.)",
        "Pods with a status reason set. Evicted = pod was evicted (disk pressure, memory pressure). "
        "NodeLost = node became unreachable.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'sum by (reason) (kube_pod_status_reason{{{NS}}} == 1)', "{{reason}}")],
        axis="Pods"
    ))

    # Not ready pods
    panels.append(ts(
        "Pods Not Ready Over Time",
        "Count of pods where readiness probe is failing. These pods exist but "
        "are not receiving traffic through Services.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt(f'count(kube_pod_status_ready{{{NS}, condition="false"}} == 1) or vector(0)', "Not Ready"),
         tgt(f'count(kube_pod_status_ready{{{NS}, condition="true"}} == 1) or vector(0)', "Ready")],
        axis="Pods"
    ))
    y += 8

    # ================================================================
    # ROW 4: POD SCHEDULING — SCHEDULING LATENCY & ATTEMPTS
    # ================================================================
    panels.append(row("Pod Scheduling — Latency, Attempts, Queue Depth", y)); y += 1

    # Scheduling attempts by result
    panels.append(ts(
        "Scheduler Attempts (by Result)",
        "How many scheduling attempts per second and whether they succeeded. "
        "result=scheduled: pod was placed. result=unschedulable: no node fits. "
        "result=error: scheduler internal error.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('sum by (result) (rate(scheduler_schedule_attempts_total[5m]))', "{{result}}")],
        axis="Attempts/sec"
    ))

    # Pending pods in scheduler queue
    panels.append(ts(
        "Pods Pending in Scheduler Queue",
        "Number of pods waiting in the scheduler queue. queue=unschedulable: pods "
        "that failed and are waiting for retry. queue=backoff: pods in exponential backoff. "
        "queue=active: pods ready for scheduling attempt.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('scheduler_pending_pods', "{{queue}}")],
        axis="Pending Pods"
    ))
    y += 8

    # E2E scheduling latency percentiles
    panels.append(histo(
        "End-to-End Scheduling Latency (p50, p90, p99)",
        "Time from pod entering the scheduler queue to being bound to a node. "
        "p99 > 1s indicates scheduler is struggling. High latency = not enough resources "
        "or complex scheduling constraints.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('histogram_quantile(0.50, sum by (le) (rate(scheduler_e2e_scheduling_duration_seconds_bucket[5m])))', "p50"),
         tgt('histogram_quantile(0.90, sum by (le) (rate(scheduler_e2e_scheduling_duration_seconds_bucket[5m])))', "p90"),
         tgt('histogram_quantile(0.99, sum by (le) (rate(scheduler_e2e_scheduling_duration_seconds_bucket[5m])))', "p99")],
        axis="Latency", unit="s"
    ))

    # Scheduling algorithm duration
    panels.append(histo(
        "Scheduling Algorithm Duration (p50, p90, p99)",
        "Time the scheduling algorithm itself takes (filtering + scoring nodes). "
        "Does not include queue wait time. High values = too many nodes or complex predicates.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('histogram_quantile(0.50, sum by (le) (rate(scheduler_scheduling_attempt_duration_seconds_bucket{result="scheduled"}[5m])))', "p50 (scheduled)"),
         tgt('histogram_quantile(0.90, sum by (le) (rate(scheduler_scheduling_attempt_duration_seconds_bucket{result="scheduled"}[5m])))', "p90 (scheduled)"),
         tgt('histogram_quantile(0.99, sum by (le) (rate(scheduler_scheduling_attempt_duration_seconds_bucket{result="scheduled"}[5m])))', "p99 (scheduled)"),
         tgt('histogram_quantile(0.99, sum by (le) (rate(scheduler_scheduling_attempt_duration_seconds_bucket{result="unschedulable"}[5m])))', "p99 (unschedulable)")],
        axis="Duration", unit="s"
    ))
    y += 8

    # Pods scheduled vs unschedulable over time
    panels.append(ts(
        "Pods Scheduled vs Unschedulable (rate)",
        "Rate at which pods are being successfully scheduled vs failing. "
        "A rising unschedulable rate means the cluster is running out of capacity.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('rate(scheduler_schedule_attempts_total{result="scheduled"}[5m])', "Scheduled/sec"),
         tgt('rate(scheduler_schedule_attempts_total{result="unschedulable"}[5m])', "Unschedulable/sec"),
         tgt('rate(scheduler_schedule_attempts_total{result="error"}[5m])', "Error/sec")],
        axis="Rate"
    ))

    # Preemption attempts
    panels.append(ts(
        "Scheduler Preemption Attempts",
        "Rate of preemption attempts. Preemption = evicting lower-priority pods to make "
        "room for higher-priority ones. Frequent preemption indicates resource pressure.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('rate(scheduler_preemption_attempts_total[5m])', "Preemption Attempts/sec"),
         tgt('sum(rate(scheduler_preemption_victims[5m]))', "Preemption Victims/sec")],
        axis="Rate"
    ))
    y += 8

    # Framework extension point duration
    panels.append(ts(
        "Scheduler Plugin Duration by Extension Point",
        "Time each scheduler plugin takes at each extension point (Filter, Score, PreFilter, etc.). "
        "Helps identify slow scheduler plugins.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt('histogram_quantile(0.99, sum by (extension_point, le) (rate(scheduler_framework_extension_point_duration_seconds_bucket[5m])))',
             "p99 {{extension_point}}")],
        axis="Duration", unit="s"
    ))
    y += 8

    # ================================================================
    # ROW 5: PODS NOT SCHEDULING — WHY
    # ================================================================
    panels.append(row("Pods Not Scheduling — Diagnostics", y)); y += 1

    # Unschedulable pods
    panels.append(ts(
        "Unschedulable Pods Count",
        "Pods that cannot be scheduled. kube_pod_status_unschedulable shows pods "
        "whose PodScheduled condition is False. These are stuck in Pending.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt(f'count(kube_pod_status_scheduled{{{NS}, condition="false"}} == 1) or vector(0)', "Unscheduled Pods"),
         tgt(f'count(kube_pod_status_scheduled{{{NS}, condition="true"}} == 1) or vector(0)', "Scheduled Pods")],
        axis="Pods"
    ))

    # Scheduler incoming pods rate
    panels.append(ts(
        "Incoming Pods to Scheduler Queue",
        "Rate of pods entering the scheduler queue. Spikes = large-scale deployments "
        "or scaling events.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('sum by (event) (rate(scheduler_queue_incoming_pods_total[5m]))', "{{event}}")],
        axis="Pods/sec"
    ))
    y += 8

    # Unschedulable pods table
    panels.append(tbl(
        "Currently Unscheduled Pods",
        "Pods where PodScheduled condition is False. These are in Pending state "
        "waiting for a node. Check Events in kubectl for the specific reason.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [
            tgt(f'kube_pod_status_scheduled{{{NS}, condition="false"}} == 1', "", fmt="table"),
        ],
        transforms=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "uid": True,
                    "job": True, "instance": True, "service": True,
                    "endpoint": True, "prometheus": True, "Value": True,
                    "condition": True},
                "renameByName": {
                    "pod": "Pod", "namespace": "Namespace"
                }}}
        ],
        overrides=[
            {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 400}]},
            {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 180}]},
        ],
        sort=[{"displayName": "Pod", "desc": False}]
    ))
    y += 8

    # ================================================================
    # ROW 6: API SERVER HEALTH
    # ================================================================
    panels.append(row("API Server Health", y)); y += 1

    # API request rate by verb
    panels.append(ts(
        "API Server Request Rate (by verb)",
        "Rate of API requests by HTTP verb (GET, LIST, WATCH, CREATE, UPDATE, DELETE, PATCH). "
        "High LIST/WATCH rates are normal. Spikes in CREATE/DELETE = deployment activity.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('sum by (verb) (rate(apiserver_request_total[5m]))', "{{verb}}")],
        axis="Requests/sec"
    ))

    # API request errors
    panels.append(ts(
        "API Server Errors (4xx, 5xx)",
        "Rate of API errors by response code. 409=conflict (normal during updates), "
        "429=throttled, 500+=server errors (bad). Filter: only error codes shown.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('sum by (code) (rate(apiserver_request_total{code=~"[45].."}[5m]))', "HTTP {{code}}")],
        axis="Errors/sec"
    ))
    y += 8

    # API request latency
    panels.append(histo(
        "API Server Request Latency (p50, p90, p99)",
        "Time the API server takes to respond. p99 > 1s = overloaded API server or etcd. "
        "Verbs like LIST are naturally slower than GET.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('histogram_quantile(0.50, sum by (le) (rate(apiserver_request_duration_seconds_bucket{verb!="WATCH"}[5m])))', "p50"),
         tgt('histogram_quantile(0.90, sum by (le) (rate(apiserver_request_duration_seconds_bucket{verb!="WATCH"}[5m])))', "p90"),
         tgt('histogram_quantile(0.99, sum by (le) (rate(apiserver_request_duration_seconds_bucket{verb!="WATCH"}[5m])))', "p99")],
        axis="Latency", unit="s"
    ))

    # API server inflight requests
    panels.append(ts(
        "API Server Inflight Requests",
        "Currently in-flight requests to the API server. mutating = write operations, "
        "readOnly = read operations. High inflight = API server under pressure.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('apiserver_current_inflight_requests', "{{requestKind}}")],
        axis="Inflight"
    ))
    y += 8

    # API request latency by resource
    panels.append(histo(
        "API Latency p99 by Resource (top slow resources)",
        "Which Kubernetes resources are slowest to query. Helps identify if pods, "
        "nodes, secrets, or configmaps are causing API slowdowns.",
        {"h": 8, "w": 24, "x": 0, "y": y},
        [tgt('topk(10, histogram_quantile(0.99, sum by (resource, le) (rate(apiserver_request_duration_seconds_bucket{verb!="WATCH"}[5m]))))',
             "{{resource}}")],
        axis="p99 Latency", unit="s"
    ))
    y += 8

    # ================================================================
    # ROW 7: ETCD (BACKING STORE) HEALTH
    # ================================================================
    panels.append(row("etcd Health (API Server Backend)", y)); y += 1

    panels.append(histo(
        "etcd Request Latency (p99)",
        "Latency of API server requests to etcd. etcd slowness directly impacts "
        "scheduling and all cluster operations. p99 > 100ms = etcd issues.",
        {"h": 8, "w": 12, "x": 0, "y": y},
        [tgt('histogram_quantile(0.99, sum by (operation, le) (rate(etcd_request_duration_seconds_bucket[5m])))',
             "{{operation}}")],
        axis="Latency", unit="s"
    ))

    panels.append(ts(
        "etcd Object Count by Resource",
        "Number of objects stored in etcd by resource type. Helps understand cluster scale.",
        {"h": 8, "w": 12, "x": 12, "y": y},
        [tgt('topk(10, etcd_object_counts)', "{{resource}}")],
        axis="Objects"
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
        "id": None, "uid": "k8s-pod-details-v1",
        "title": "K8s Pod Details & Scheduler Metrics",
        "description": "Rich pod information: phases, errors, container status, scheduling latency, "
                       "API server health, etcd backend. All filtered by namespace.",
        "tags": ["kubernetes", "pods", "scheduler", "api-server", "errors", "phases"],
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
    out = sys.argv[1] if len(sys.argv) > 1 else "k8s-pod-details-dashboard.json"
    d = build()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    pc = len(d["panels"])
    vc = len(d["templating"]["list"])
    print(f"Generated {out}: {pc} panels, {vc} template variables")
    for p in d["panels"]:
        print(f"  [{p['type']:12s}] {p.get('title', '')}")
