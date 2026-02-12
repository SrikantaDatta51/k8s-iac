#!/usr/bin/env python3
"""Generate the K8s SKU Violation Grafana Dashboard JSON."""

import json
import copy

# --- Helpers ---
_id = 0
def next_id():
    global _id; _id += 1; return _id

def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": next_id(), "panels": []}

def ds():
    return {"type": "prometheus", "uid": "${datasource}"}

def target(expr, legend, instant=False, fmt="time_series"):
    t = {"refId": "", "datasource": ds(), "expr": expr, "legendFormat": legend}
    if instant: t["instant"] = True
    if fmt == "table": t["format"] = "table"; t["instant"] = True
    return t

def assign_refs(targets):
    for i, t in enumerate(targets):
        t["refId"] = chr(65 + i)
    return targets

def stat_panel(title, desc, gp, targets, unit="none", decimals=0,
               thresholds=None, mappings=None, color_mode="background",
               text_mode="auto", graph_mode="none", orientation="auto"):
    p = {
        "id": next_id(), "title": title, "description": desc, "type": "stat",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals,
            "thresholds": thresholds or {"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None}, {"color": "#FF4040", "value": 1}]},
            "mappings": mappings or []}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": orientation, "textMode": text_mode,
            "colorMode": color_mode, "graphMode": graph_mode, "justifyMode": "center"},
        "targets": assign_refs(targets)
    }
    return p

def gauge_panel(title, desc, gp, targets, unit="percentunit"):
    return {
        "id": next_id(), "title": title, "description": desc, "type": "gauge",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 1, "min": 0, "max": 1,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None},
                {"color": "#FF9830", "value": 0.75},
                {"color": "#FF4040", "value": 1}]}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
            "showThresholdLabels": True, "showThresholdMarkers": True},
        "targets": assign_refs(targets)
    }

def barchart_panel(title, desc, gp, targets, axis_label, unit="short",
                   req_color="#5794F2", lim_color="#FF9830"):
    return {
        "id": next_id(), "title": title, "description": desc, "type": "barchart",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 2,
            "color": {"mode": "palette-classic"},
            "custom": {"lineWidth": 1, "fillOpacity": 80, "gradientMode": "scheme",
                "axisLabel": axis_label, "axisSoftMin": 0,
                "stacking": {"mode": "none"}}},
            "overrides": [
                {"matcher": {"id": "byRegexp", "options": ".*Request.*"},
                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": req_color}}]},
                {"matcher": {"id": "byRegexp", "options": ".*Limit.*"},
                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": lim_color}}]}
            ]},
        "options": {"orientation": "horizontal", "barWidth": 0.7, "groupWidth": 0.7,
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"}, "xTickLabelRotation": -45},
        "targets": assign_refs(targets)
    }

def timeseries_panel(title, desc, gp, targets, axis_label, unit="short",
                     sku_series_name="SKU Capacity", req_color="#5794F2",
                     lim_color="#FF9830"):
    overrides = [
        {"matcher": {"id": "byName", "options": sku_series_name},
         "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": "#FF4040"}},
            {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}},
            {"id": "custom.fillOpacity", "value": 0},
            {"id": "custom.lineWidth", "value": 3}]},
        {"matcher": {"id": "byRegexp", "options": ".*Request.*"},
         "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": req_color}}]},
        {"matcher": {"id": "byRegexp", "options": ".*Limit.*"},
         "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": lim_color}}]}
    ]
    return {
        "id": next_id(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 2, "fillOpacity": 15, "gradientMode": "scheme",
                "axisLabel": axis_label, "drawStyle": "line", "pointSize": 5,
                "showPoints": "auto", "spanNulls": True}},
            "overrides": overrides},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": assign_refs(targets)
    }

def per_pod_ts_panel(title, desc, gp, resource, divisor_expr, axis_label, unit="short"):
    """Time series showing per-pod actual usage vs requests vs limits."""
    ns_node = 'namespace="$namespace", node=~"$node"'
    if resource == "cpu":
        usage_expr = f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{ns_node}}}[5m]))'
    elif resource == "memory":
        usage_expr = f'sum by (pod) (container_memory_working_set_bytes{{{ns_node}}}) / {divisor_expr}'
    else:
        usage_expr = f'sum by (pod) (container_fs_usage_bytes{{{ns_node}}}) / {divisor_expr}'

    req_expr = f'sum by (pod) (kube_pod_container_resource_requests{{{ns_node}, resource="{resource}"}})' + (f' / {divisor_expr}' if resource != "cpu" else '')
    lim_expr = f'sum by (pod) (kube_pod_container_resource_limits{{{ns_node}, resource="{resource}"}})' + (f' / {divisor_expr}' if resource != "cpu" else '')

    targets = [
        target(usage_expr, "{{pod}} Actual"),
        target(req_expr, "{{pod}} Request"),
        target(lim_expr, "{{pod}} Limit"),
    ]
    overrides = [
        {"matcher": {"id": "byRegexp", "options": ".*Actual.*"},
         "properties": [{"id": "custom.lineWidth", "value": 2},
                        {"id": "custom.fillOpacity", "value": 20}]},
        {"matcher": {"id": "byRegexp", "options": ".*Request.*"},
         "properties": [{"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [8, 4]}},
                        {"id": "custom.fillOpacity", "value": 0}]},
        {"matcher": {"id": "byRegexp", "options": ".*Limit.*"},
         "properties": [{"id": "custom.lineStyle", "value": {"fill": "dot", "dash": [2, 4]}},
                        {"id": "custom.fillOpacity", "value": 0},
                        {"id": "color", "value": {"mode": "fixed", "fixedColor": "#FF4040"}}]}
    ]
    return {
        "id": next_id(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 1, "fillOpacity": 10, "gradientMode": "scheme",
                "axisLabel": axis_label, "drawStyle": "line", "pointSize": 3,
                "showPoints": "never", "spanNulls": True}},
            "overrides": overrides},
        "options": {"legend": {"displayMode": "table", "placement": "right",
                               "calcs": ["lastNotNull", "max"]},
            "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": assign_refs(targets)
    }

def abusing_pods_panel(title, desc, gp, resource, divisor_expr):
    """Table showing pods whose actual usage exceeds their requests or limits."""
    ns_node = 'namespace="$namespace", node=~"$node"'
    if resource == "cpu":
        usage = f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{ns_node}}}[5m]))'
        req = f'sum by (pod) (kube_pod_container_resource_requests{{{ns_node}, resource="cpu"}})'
        lim = f'sum by (pod) (kube_pod_container_resource_limits{{{ns_node}, resource="cpu"}})'
        over_req = f'({usage} - {req}) > 0'
        over_lim = f'({usage} - {lim}) > 0'
    else:
        usage = f'sum by (pod) (container_memory_working_set_bytes{{{ns_node}}}) / {divisor_expr}' if resource == "memory" else f'sum by (pod) (container_fs_usage_bytes{{{ns_node}}}) / {divisor_expr}'
        req = f'sum by (pod) (kube_pod_container_resource_requests{{{ns_node}, resource="{resource}"}}) / {divisor_expr}'
        lim = f'sum by (pod) (kube_pod_container_resource_limits{{{ns_node}, resource="{resource}"}}) / {divisor_expr}'
        over_req = f'({usage} - {req}) > 0'
        over_lim = f'({usage} - {lim}) > 0'

    return {
        "id": next_id(), "title": title, "description": desc, "type": "table",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto",
            "filterable": True}},
            "overrides": [
                {"matcher": {"id": "byRegexp", "options": ".*Excess.*"},
                 "properties": [{"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 0.01},
                        {"color": "#FF4040", "value": 1}]}}]}
            ]},
        "options": {"showHeader": True, "sortBy": [{"displayName": "Value #A", "desc": True}],
            "footer": {"show": False}},
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {"excludeByName": {"Time": True}}}
        ],
        "targets": assign_refs([
            target(over_req, "Excess over Request", fmt="table"),
            target(over_lim, "Excess over Limit", fmt="table"),
        ])
    }

# --- Main Dashboard ---
def build_dashboard():
    ok_violation_mappings = [{"type": "value", "options": {
        "0": {"text": "WITHIN LIMITS", "color": "#73BF69", "index": 0},
        "1": {"text": "EXCEEDS SKU", "color": "#FF4040", "index": 1}}}]

    panels = []
    y = 0

    # ============================================================
    # ROW: SKU Violation Summary
    # ============================================================
    panels.append(row("SKU Violation Summary", y)); y += 1

    # Status panels
    for i, (res, res_label, sku_var, divisor) in enumerate([
        ("cpu", "CPU", "$sku_cpu_cores", ""),
        ("memory", "Memory", "($sku_memory_value * $memory_unit)", ""),
        ("ephemeral-storage", "Ephemeral Storage", "($sku_ephemeral_value * $ephemeral_unit)", ""),
    ]):
        ns_node = 'namespace="$namespace", node=~"$node"'
        expr = f'clamp_max(ceil(sum(kube_pod_container_resource_requests{{{ns_node}, resource="{res}"}}) / {sku_var}), 1)'
        panels.append(stat_panel(
            f"{res_label} - SKU Status",
            f"Shows whether total {res_label.lower()} requests exceed the configured SKU capacity",
            {"h": 4, "w": 4, "x": i * 4, "y": y},
            [target(expr, f"{res_label}", instant=True)],
            mappings=ok_violation_mappings
        ))

    # Capacity % panel
    ns_node = 'namespace="$namespace", node=~"$node"'
    panels.append(stat_panel(
        "SKU Capacity Utilization",
        "Percentage of each SKU dimension consumed by pod requests",
        {"h": 4, "w": 6, "x": 12, "y": y},
        [
            target(f'sum(kube_pod_container_resource_requests{{{ns_node}, resource="cpu"}}) / $sku_cpu_cores', "CPU", instant=True),
            target(f'sum(kube_pod_container_resource_requests{{{ns_node}, resource="memory"}}) / ($sku_memory_value * $memory_unit)', "Memory", instant=True),
            target(f'sum(kube_pod_container_resource_requests{{{ns_node}, resource="ephemeral-storage"}}) / ($sku_ephemeral_value * $ephemeral_unit)', "Ephemeral", instant=True),
        ],
        unit="percentunit", decimals=1, color_mode="value", text_mode="value_and_name",
        graph_mode="area", orientation="horizontal",
        thresholds={"mode": "absolute", "steps": [
            {"color": "#73BF69", "value": None},
            {"color": "#FF9830", "value": 0.75},
            {"color": "#FF4040", "value": 1.0}]}
    ))

    # Pod count
    panels.append(stat_panel(
        "Total Running Pods",
        "Number of running pods in the selected namespace",
        {"h": 4, "w": 6, "x": 18, "y": y},
        [target(f'count(kube_pod_info{{{ns_node}}})', "Pods", instant=True)],
        color_mode="value", text_mode="value", graph_mode="area",
        thresholds={"mode": "absolute", "steps": [
            {"color": "#5794F2", "value": None}]}
    ))
    y += 4

    # Pod resource table
    panels.append({
        "id": next_id(), "title": "All Pods - Resource Requests and Limits",
        "description": "Sortable table of all pods showing CPU (cores), memory, and ephemeral storage requests and limits. The footer row shows the sum.",
        "type": "table", "datasource": ds(),
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": y},
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Pod"},
                 "properties": [{"id": "custom.width", "value": 300}]},
                {"matcher": {"id": "byRegexp", "options": ".*CPU.*"},
                 "properties": [{"id": "unit", "value": "short"}, {"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 4},
                        {"color": "#FF4040", "value": 8}]}}]},
                {"matcher": {"id": "byRegexp", "options": ".*Memory.*"},
                 "properties": [{"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 64},
                        {"color": "#FF4040", "value": 128}]}}]},
            ]},
        "options": {"showHeader": True,
            "sortBy": [{"displayName": "CPU Request", "desc": True}],
            "footer": {"show": True, "reducer": ["sum"],
                "fields": ["CPU Request", "CPU Limit", "Memory Request", "Memory Limit"]}},
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {"excludeByName": {"Time": True}}}
        ],
        "targets": assign_refs([
            target(f'sum by (pod) (kube_pod_container_resource_requests{{{ns_node}, resource="cpu"}})', "CPU Request", fmt="table"),
            target(f'sum by (pod) (kube_pod_container_resource_limits{{{ns_node}, resource="cpu"}})', "CPU Limit", fmt="table"),
            target(f'sum by (pod) (kube_pod_container_resource_requests{{{ns_node}, resource="memory"}}) / $memory_unit', "Memory Request", fmt="table"),
            target(f'sum by (pod) (kube_pod_container_resource_limits{{{ns_node}, resource="memory"}}) / $memory_unit', "Memory Limit", fmt="table"),
        ])
    })
    y += 8

    # ============================================================
    # RESOURCE DIMENSION ROWS
    # ============================================================
    dimensions = [
        {
            "label": "CPU",
            "resource": "cpu",
            "unit_var": "",  # no conversion needed
            "sku_var": "$sku_cpu_cores",
            "axis": "CPU Cores",
            "grafana_unit": "short",
            "req_color": "#5794F2",
            "lim_color": "#FF9830",
            "divisor_expr": "",
        },
        {
            "label": "Memory",
            "resource": "memory",
            "unit_var": "$memory_unit",
            "sku_var": "$sku_memory_value",
            "axis": "Memory (selected unit)",
            "grafana_unit": "short",
            "req_color": "#8F3BB8",
            "lim_color": "#F2CC0C",
            "divisor_expr": "$memory_unit",
        },
        {
            "label": "Ephemeral Storage",
            "resource": "ephemeral-storage",
            "unit_var": "$ephemeral_unit",
            "sku_var": "$sku_ephemeral_value",
            "axis": "Ephemeral Storage (selected unit)",
            "grafana_unit": "short",
            "req_color": "#56A64B",
            "lim_color": "#E02F44",
            "divisor_expr": "$ephemeral_unit",
        },
    ]

    for dim in dimensions:
        panels.append(row(f"{dim['label']} - Resource Analysis", y)); y += 1
        r = dim["resource"]
        ns_node_r = f'namespace="$namespace", node=~"$node", resource="{r}"'
        div = f" / {dim['divisor_expr']}" if dim['divisor_expr'] else ""

        # Bar chart: Requests vs Limits per pod
        panels.append(barchart_panel(
            f"{dim['label']} - Requests vs Limits per Pod",
            f"Grouped bar chart showing {dim['label'].lower()} requests and limits for each running pod",
            {"h": 10, "w": 12, "x": 0, "y": y},
            [
                target(f'sum by (pod) (kube_pod_container_resource_requests{{{ns_node_r}}}){div}', "{{pod}} Request", fmt="table"),
                target(f'sum by (pod) (kube_pod_container_resource_limits{{{ns_node_r}}}){div}', "{{pod}} Limit", fmt="table"),
            ],
            axis_label=dim["axis"], unit=dim["grafana_unit"],
            req_color=dim["req_color"], lim_color=dim["lim_color"]
        ))

        # Gauge: % of SKU consumed
        if dim["divisor_expr"]:
            gauge_expr = f'sum(kube_pod_container_resource_requests{{{ns_node_r}}}){div} / {dim["sku_var"]}'
        else:
            gauge_expr = f'sum(kube_pod_container_resource_requests{{{ns_node_r}}}) / {dim["sku_var"]}'
        panels.append(gauge_panel(
            f"{dim['label']} - Capacity vs SKU",
            f"Gauge showing what percentage of the configured {dim['label']} SKU capacity is consumed by total requests",
            {"h": 5, "w": 6, "x": 12, "y": y},
            [target(gauge_expr, f"{dim['label']} Utilization", instant=True)]
        ))

        # Stat: absolute totals
        panels.append(stat_panel(
            f"{dim['label']} - Absolute Totals",
            f"Total {dim['label'].lower()} requests, limits, and configured SKU capacity",
            {"h": 5, "w": 6, "x": 18, "y": y},
            [
                target(f'sum(kube_pod_container_resource_requests{{{ns_node_r}}}){div}', "Total Requests", instant=True),
                target(f'sum(kube_pod_container_resource_limits{{{ns_node_r}}}){div}', "Total Limits", instant=True),
                target(f'vector({dim["sku_var"]})', "SKU Capacity", instant=True),
            ],
            unit=dim["grafana_unit"], decimals=1, color_mode="value",
            text_mode="value_and_name", orientation="horizontal",
            thresholds={"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None}, {"color": "#FF4040", "value": 1}]}
        ))
        y += 5

        # Time series: aggregate over time with SKU threshold
        panels.append(timeseries_panel(
            f"{dim['label']} - Aggregate Requests and Limits Over Time",
            f"Historical trend of total {dim['label'].lower()} requests and limits vs the configured SKU threshold (red dashed line)",
            {"h": 8, "w": 12, "x": 12, "y": y},
            [
                target(f'sum(kube_pod_container_resource_requests{{{ns_node_r}}}){div}', "Total Requests"),
                target(f'sum(kube_pod_container_resource_limits{{{ns_node_r}}}){div}', "Total Limits"),
                target(f'vector({dim["sku_var"]})', "SKU Capacity"),
            ],
            axis_label=dim["axis"], unit=dim["grafana_unit"],
            req_color=dim["req_color"], lim_color=dim["lim_color"]
        ))

        # Histogram
        panels.append({
            "id": next_id(),
            "title": f"{dim['label']} - Request Size Distribution",
            "description": f"Histogram showing the distribution of per-pod {dim['label'].lower()} request sizes",
            "type": "histogram", "datasource": ds(),
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": y},
            "fieldConfig": {"defaults": {"unit": dim["grafana_unit"],
                "color": {"mode": "palette-classic"},
                "custom": {"fillOpacity": 80, "gradientMode": "scheme", "lineWidth": 1}},
                "overrides": []},
            "options": {"bucketSize": 1 if r == "cpu" else 8,
                "combine": False, "fillOpacity": 80, "gradientMode": "scheme",
                "legend": {"displayMode": "list", "placement": "bottom"},
                "tooltip": {"mode": "multi"}},
            "targets": assign_refs([
                target(f'sum by (pod) (kube_pod_container_resource_requests{{{ns_node_r}}}){div}',
                       "{{pod}}", fmt="table")
            ])
        })
        y += 8

        # Per-pod time series: actual usage vs requests vs limits
        panels.append(per_pod_ts_panel(
            f"{dim['label']} - Per-Pod Usage vs Requests vs Limits",
            f"Each pod's actual {dim['label'].lower()} usage (solid line) compared to its request (dashed) and limit (dotted). "
            f"Pods where the solid line exceeds the dashed/dotted line are over-consuming.",
            {"h": 10, "w": 24, "x": 0, "y": y},
            resource=r, divisor_expr=dim["divisor_expr"] or "1",
            axis_label=dim["axis"], unit=dim["grafana_unit"]
        ))
        y += 10

        # Abusing pods table
        panels.append(abusing_pods_panel(
            f"{dim['label']} - Pods Exceeding Their Allocations",
            f"Pods where actual {dim['label'].lower()} usage exceeds their configured request or limit. "
            f"These pods are consuming more than allocated and may cause resource contention.",
            {"h": 6, "w": 24, "x": 0, "y": y},
            resource=r, divisor_expr=dim["divisor_expr"] or "1"
        ))
        y += 6

    # --- Build full dashboard ---
    dashboard = {
        "__inputs": [],
        "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "9.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"}
        ],
        "id": None,
        "uid": "k8s-sku-violation-v2",
        "title": "K8s Pod Resources vs SKU Capacity",
        "description": "Monitors Kubernetes pod resource requests, limits, and actual usage against configurable SKU capacity with violation detection. Units are configurable per resource type.",
        "tags": ["kubernetes", "sku", "capacity", "resources", "violations"],
        "style": "dark",
        "timezone": "browser",
        "editable": True,
        "graphTooltip": 1,
        "fiscalYearStartMonth": 0,
        "liveNow": False,
        "refresh": "30s",
        "schemaVersion": 38,
        "version": 2,
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {},
        "annotations": {"list": [{
            "builtIn": 1,
            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True, "hide": True,
            "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts", "type": "dashboard"
        }]},
        "templating": {"list": [
            {
                "name": "datasource", "type": "datasource", "label": "Prometheus Data Source",
                "query": "prometheus", "current": {}, "hide": 0,
                "includeAll": False, "multi": False, "options": [],
                "refresh": 1, "regex": "", "skipUrlSync": False
            },
            {
                "name": "namespace", "type": "query", "label": "Namespace",
                "datasource": ds(),
                "definition": "label_values(kube_pod_info, namespace)",
                "query": {"query": "label_values(kube_pod_info, namespace)", "refId": "ns"},
                "current": {}, "hide": 0, "includeAll": False, "multi": False,
                "options": [], "refresh": 2, "regex": "", "sort": 1, "skipUrlSync": False
            },
            {
                "name": "node", "type": "query", "label": "Node",
                "datasource": ds(),
                "definition": 'label_values(kube_pod_info{namespace="$namespace"}, node)',
                "query": {"query": 'label_values(kube_pod_info{namespace="$namespace"}, node)', "refId": "nd"},
                "current": {}, "hide": 0, "includeAll": True, "multi": False,
                "options": [], "refresh": 2, "regex": "", "sort": 1, "skipUrlSync": False
            },
            # --- SKU capacity inputs ---
            {
                "name": "sku_cpu_cores", "type": "textbox",
                "label": "SKU: Total CPU (cores)",
                "current": {"selected": False, "text": "128", "value": "128"},
                "hide": 0,
                "options": [{"selected": True, "text": "128", "value": "128"}],
                "query": "128", "skipUrlSync": False
            },
            {
                "name": "sku_memory_value", "type": "textbox",
                "label": "SKU: Total Memory (in selected unit below)",
                "current": {"selected": False, "text": "22528", "value": "22528"},
                "hide": 0,
                "options": [{"selected": True, "text": "22528", "value": "22528"}],
                "query": "22528", "skipUrlSync": False,
                "description": "Enter the SKU memory capacity in the same unit as the Memory Unit selector"
            },
            {
                "name": "memory_unit", "type": "custom",
                "label": "Memory Display Unit",
                "current": {"selected": True, "text": "GiB (binary, 2^30 bytes)", "value": "1073741824"},
                "hide": 0, "includeAll": False, "multi": False,
                "options": [
                    {"selected": True, "text": "GiB (binary, 2^30 bytes)", "value": "1073741824"},
                    {"selected": False, "text": "MiB (binary, 2^20 bytes)", "value": "1048576"},
                    {"selected": False, "text": "TiB (binary, 2^40 bytes)", "value": "1099511627776"},
                    {"selected": False, "text": "GB (decimal, 10^9 bytes)", "value": "1000000000"},
                    {"selected": False, "text": "MB (decimal, 10^6 bytes)", "value": "1000000"},
                    {"selected": False, "text": "TB (decimal, 10^12 bytes)", "value": "1000000000000"},
                    {"selected": False, "text": "Bytes (raw)", "value": "1"},
                ],
                "query": "GiB (binary\\, 2^30 bytes) : 1073741824, MiB (binary\\, 2^20 bytes) : 1048576, TiB (binary\\, 2^40 bytes) : 1099511627776, GB (decimal\\, 10^9 bytes) : 1000000000, MB (decimal\\, 10^6 bytes) : 1000000, TB (decimal\\, 10^12 bytes) : 1000000000000, Bytes (raw) : 1",
                "skipUrlSync": False,
                "description": "Choose the unit for memory display. SKU Memory value must be entered in this same unit."
            },
            {
                "name": "sku_ephemeral_value", "type": "textbox",
                "label": "SKU: Total Ephemeral Storage (in selected unit below)",
                "current": {"selected": False, "text": "10240", "value": "10240"},
                "hide": 0,
                "options": [{"selected": True, "text": "10240", "value": "10240"}],
                "query": "10240", "skipUrlSync": False,
                "description": "Enter the SKU ephemeral storage capacity in the same unit as the Ephemeral Unit selector"
            },
            {
                "name": "ephemeral_unit", "type": "custom",
                "label": "Ephemeral Storage Display Unit",
                "current": {"selected": True, "text": "GiB (binary, 2^30 bytes)", "value": "1073741824"},
                "hide": 0, "includeAll": False, "multi": False,
                "options": [
                    {"selected": True, "text": "GiB (binary, 2^30 bytes)", "value": "1073741824"},
                    {"selected": False, "text": "MiB (binary, 2^20 bytes)", "value": "1048576"},
                    {"selected": False, "text": "TiB (binary, 2^40 bytes)", "value": "1099511627776"},
                    {"selected": False, "text": "GB (decimal, 10^9 bytes)", "value": "1000000000"},
                    {"selected": False, "text": "MB (decimal, 10^6 bytes)", "value": "1000000"},
                    {"selected": False, "text": "TB (decimal, 10^12 bytes)", "value": "1000000000000"},
                    {"selected": False, "text": "Bytes (raw)", "value": "1"},
                ],
                "query": "GiB (binary\\, 2^30 bytes) : 1073741824, MiB (binary\\, 2^20 bytes) : 1048576, TiB (binary\\, 2^40 bytes) : 1099511627776, GB (decimal\\, 10^9 bytes) : 1000000000, MB (decimal\\, 10^6 bytes) : 1000000, TB (decimal\\, 10^12 bytes) : 1000000000000, Bytes (raw) : 1",
                "skipUrlSync": False,
                "description": "Choose the unit for ephemeral storage display. SKU Ephemeral value must be entered in this same unit."
            },
        ]},
        "panels": panels
    }
    return dashboard


if __name__ == "__main__":
    import sys
    out = "k8s-sku-dashboard.json"
    if len(sys.argv) > 1:
        out = sys.argv[1]
    dashboard = build_dashboard()
    with open(out, "w") as f:
        json.dump(dashboard, f, indent=4)
    panel_count = len(dashboard["panels"])
    var_count = len(dashboard["templating"]["list"])
    print(f"Generated {out}: {panel_count} panels, {var_count} template variables")
    for p in dashboard["panels"]:
        ptype = p["type"]
        title = p.get("title", "")
        print(f"  [{ptype:12s}] {title}")
