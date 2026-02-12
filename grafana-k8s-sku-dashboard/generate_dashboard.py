#!/usr/bin/env python3
"""Generate the K8s SKU Violation Grafana Dashboard JSON - v3.
Fixes: GPU+VRAM dimensions, multi-select namespace/node, table column naming,
unit refresh, violation explanations, reservation vs utilization, node-centric views.
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

# Common filter string — uses regex match for multi-select support
NS = 'namespace=~"$namespace"'
ND = 'node=~"$node"'
NSND = f'{NS}, {ND}'

def row_panel(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}

def stat_p(title, desc, gp, targets, unit="none", decimals=0,
           thresholds=None, mappings=None, color_mode="background",
           text_mode="auto", graph_mode="none", orient="auto"):
    return {
        "id": nid(), "title": title, "description": desc, "type": "stat",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals,
            "thresholds": thresholds or {"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None}, {"color": "#FF4040", "value": 1}]},
            "mappings": mappings or []}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": orient, "textMode": text_mode,
            "colorMode": color_mode, "graphMode": graph_mode, "justifyMode": "center"},
        "targets": refs(targets)
    }

def gauge_p(title, desc, gp, targets, unit="percentunit"):
    return {
        "id": nid(), "title": title, "description": desc, "type": "gauge",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 1, "min": 0, "max": 1,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "#73BF69", "value": None},
                {"color": "#FF9830", "value": 0.75},
                {"color": "#FF4040", "value": 1}]}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
            "showThresholdLabels": True, "showThresholdMarkers": True},
        "targets": refs(targets)
    }

def barchart_p(title, desc, gp, targets, axis_label, unit="short",
               req_color="#5794F2", lim_color="#FF9830"):
    return {
        "id": nid(), "title": title, "description": desc, "type": "barchart",
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
        "targets": refs(targets)
    }

def ts_panel(title, desc, gp, targets, axis_label, unit="short",
             sku_name="SKU Capacity", req_color="#5794F2", lim_color="#FF9830"):
    overrides = [
        {"matcher": {"id": "byName", "options": sku_name},
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
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 2, "fillOpacity": 15, "gradientMode": "scheme",
                "axisLabel": axis_label, "drawStyle": "line", "pointSize": 5,
                "showPoints": "auto", "spanNulls": True}},
            "overrides": overrides},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs(targets)
    }

def per_pod_ts(title, desc, gp, resource, divisor, axis_label, unit="short"):
    f = f'{NSND}'
    if resource == "cpu":
        usage = f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{f}}}[5m]))'
        req = f'sum by (pod) (kube_pod_container_resource_requests{{{f}, resource="cpu"}})'
        lim = f'sum by (pod) (kube_pod_container_resource_limits{{{f}, resource="cpu"}})'
    elif resource == "memory":
        usage = f'sum by (pod) (container_memory_working_set_bytes{{{f}}}) / {divisor}'
        req = f'sum by (pod) (kube_pod_container_resource_requests{{{f}, resource="memory"}}) / {divisor}'
        lim = f'sum by (pod) (kube_pod_container_resource_limits{{{f}, resource="memory"}}) / {divisor}'
    elif resource == "nvidia.com/gpu":
        usage = f'sum by (pod) (DCGM_FI_DEV_GPU_UTIL{{{f}}}) / 100'
        req = f'sum by (pod) (kube_pod_container_resource_requests{{{f}, resource="nvidia.com/gpu"}})'
        lim = f'sum by (pod) (kube_pod_container_resource_limits{{{f}, resource="nvidia.com/gpu"}})'
    elif resource == "vram":
        usage = f'sum by (pod) (DCGM_FI_DEV_FB_USED{{{f}}}) / 1024'
        req = f'sum by (pod) (DCGM_FI_DEV_FB_USED{{{f}}} + DCGM_FI_DEV_FB_FREE{{{f}}}) / 1024'
        lim = req
    else:  # ephemeral-storage
        usage = f'sum by (pod) (container_fs_usage_bytes{{{f}}}) / {divisor}'
        req = f'sum by (pod) (kube_pod_container_resource_requests{{{f}, resource="ephemeral-storage"}}) / {divisor}'
        lim = f'sum by (pod) (kube_pod_container_resource_limits{{{f}, resource="ephemeral-storage"}}) / {divisor}'
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
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": unit,
            "custom": {"lineWidth": 1, "fillOpacity": 10, "gradientMode": "scheme",
                "axisLabel": axis_label, "drawStyle": "line", "pointSize": 3,
                "showPoints": "never", "spanNulls": True}},
            "overrides": overrides},
        "options": {"legend": {"displayMode": "table", "placement": "right",
                               "calcs": ["lastNotNull", "max"]},
            "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs([tgt(usage, "{{pod}} Actual"), tgt(req, "{{pod}} Request"), tgt(lim, "{{pod}} Limit")])
    }

def heatmap_panel(title, desc, gp, resource, divisor, axis_label):
    """Heatmap of resource usage per node."""
    if resource == "cpu":
        expr = f'sum by (node) (kube_pod_container_resource_requests{{{NS}, resource="cpu"}})'
    elif resource == "memory":
        expr = f'sum by (node) (kube_pod_container_resource_requests{{{NS}, resource="memory"}}) / {divisor}'
    elif resource == "nvidia.com/gpu":
        expr = f'sum by (node) (kube_pod_container_resource_requests{{{NS}, resource="nvidia.com/gpu"}})'
    elif resource == "vram":
        expr = f'sum by (node) (DCGM_FI_DEV_FB_USED{{{NS}}}) / 1024'
    else:
        expr = f'sum by (node) (kube_pod_container_resource_requests{{{NS}, resource="ephemeral-storage"}}) / {divisor}'
    return {
        "id": nid(), "title": title, "description": desc, "type": "timeseries",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"unit": "short",
            "custom": {"lineWidth": 0, "fillOpacity": 80, "gradientMode": "scheme",
                "axisLabel": axis_label, "drawStyle": "bars", "pointSize": 5,
                "stacking": {"mode": "normal"}, "showPoints": "never"}},
            "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right",
                               "calcs": ["lastNotNull", "max"]},
            "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": refs([tgt(expr, "{{node}}")])
    }

def abusing_table(title, desc, gp, resource, divisor):
    f = NSND
    if resource == "cpu":
        usage = f'sum by (pod, namespace, node) (rate(container_cpu_usage_seconds_total{{{f}}}[5m]))'
        req = f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{f}, resource="cpu"}})'
        lim = f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{f}, resource="cpu"}})'
    elif resource == "nvidia.com/gpu":
        usage = f'sum by (pod, namespace, node) (DCGM_FI_DEV_GPU_UTIL{{{f}}}) / 100'
        req = f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{f}, resource="nvidia.com/gpu"}})'
        lim = req
    elif resource == "vram":
        usage = f'sum by (pod, namespace, node) (DCGM_FI_DEV_FB_USED{{{f}}}) / 1024'
        req = f'sum by (pod, namespace, node) (DCGM_FI_DEV_FB_USED{{{f}}} + DCGM_FI_DEV_FB_FREE{{{f}}}) / 1024'
        lim = req
    elif resource == "memory":
        usage = f'sum by (pod, namespace, node) (container_memory_working_set_bytes{{{f}}}) / {divisor}'
        req = f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{f}, resource="memory"}}) / {divisor}'
        lim = f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{f}, resource="memory"}}) / {divisor}'
    else:
        usage = f'sum by (pod, namespace, node) (container_fs_usage_bytes{{{f}}}) / {divisor}'
        req = f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{f}, resource="ephemeral-storage"}}) / {divisor}'
        lim = f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{f}, resource="ephemeral-storage"}}) / {divisor}'
    return {
        "id": nid(), "title": title, "description": desc, "type": "table",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Excess Over Request"},
                 "properties": [{"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 0.01},
                        {"color": "#FF4040", "value": 1}]}}]},
                {"matcher": {"id": "byName", "options": "Excess Over Limit"},
                 "properties": [{"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 0.01},
                        {"color": "#FF4040", "value": 1}]}}]}
            ]},
        "options": {"showHeader": True, "sortBy": [{"displayName": "Excess Over Request", "desc": True}],
            "footer": {"show": False}},
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {"excludeByName": {"Time": True},
                "renameByName": {"Value #A": "Excess Over Request", "Value #B": "Excess Over Limit"}}}
        ],
        "targets": refs([
            tgt(f'({usage} - {req}) > 0', "Excess Over Request", fmt="table"),
            tgt(f'({usage} - {lim}) > 0', "Excess Over Limit", fmt="table"),
        ])
    }


def build():
    panels = []
    y = 0

    # ================================================================
    # VIOLATION SUMMARY ROW
    # ================================================================
    panels.append(row_panel("SKU Violation Summary", y)); y += 1

    # --- Violation detail text panel ---
    # Build a panel per resource showing percentage and reason
    resources_sku = [
        ("GPU",       "nvidia.com/gpu",    "$sku_gpu_count",  "",             "#B877D9"),
        ("vCPU",      "cpu",               "$sku_cpu_cores",  "",             "#5794F2"),
        ("Memory",    "memory",            "($sku_memory_value * $memory_unit)", "$memory_unit", "#8F3BB8"),
        ("VRAM",      "vram",              "($sku_vram_gib * 1073741824)",    "1073741824",   "#F2CC0C"),
        ("Local Storage", "ephemeral-storage", "($sku_storage_value * $storage_unit)", "$storage_unit", "#56A64B"),
    ]

    ok_viol_map = [{"type": "value", "options": {
        "0": {"text": "WITHIN LIMITS", "color": "#73BF69", "index": 0},
        "1": {"text": "EXCEEDS SKU", "color": "#FF4040", "index": 1}}}]

    # Status indicators (5 across)
    for i, (label, res, sku, div, color) in enumerate(resources_sku):
        if res == "vram":
            req_expr = f'sum(DCGM_FI_DEV_FB_USED{{{NSND}}}) / 1024'
            sku_expr = "$sku_vram_gib"
        elif res == "nvidia.com/gpu":
            req_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{res}"}})'
            sku_expr = sku
        elif div:
            req_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{res}"}}) / {div}'
            sku_expr = sku.replace(f" * {div}", "").strip("()")
        else:
            req_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{res}"}})'
            sku_expr = sku

        viol_expr = f'clamp_max(ceil({req_expr} / {sku}), 1)' if res != "vram" else f'clamp_max(ceil({req_expr} / $sku_vram_gib), 1)'
        w = 4 if i < 4 else 8
        panels.append(stat_p(
            f"{label} SKU Status", f"Whether total {label} requests/usage exceed the configured SKU. "
            f"EXCEEDS SKU means the sum of all pod {label} reservations is larger than the SKU capacity you entered.",
            {"h": 4, "w": w, "x": (i * 4) if i < 4 else 16, "y": y},
            [tgt(viol_expr, label, instant=True)],
            mappings=ok_viol_map
        ))

    y += 4

    # --- Reservation vs Utilization gauges ---
    panels.append(row_panel("SKU Capacity - Reservation vs Actual Utilization", y)); y += 1

    for i, (label, res, sku, div, color) in enumerate(resources_sku):
        if res == "vram":
            res_expr = f'sum(DCGM_FI_DEV_FB_USED{{{NSND}}}) / 1024 / $sku_vram_gib'
            req_expr = res_expr  # VRAM: reservation = usage for GPU mem
            usage_expr = res_expr
        elif res == "nvidia.com/gpu":
            req_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{res}"}}) / {sku}'
            usage_expr = f'sum(DCGM_FI_DEV_GPU_UTIL{{{NSND}}}) / 100 / {sku}'
        elif res == "cpu":
            req_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{res}"}}) / {sku}'
            usage_expr = f'sum(rate(container_cpu_usage_seconds_total{{{NSND}}}[5m])) / {sku}'
        elif res == "memory":
            req_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{res}"}}) / {sku}'
            usage_expr = f'sum(container_memory_working_set_bytes{{{NSND}}}) / {sku}'
        else:
            req_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{res}"}}) / {sku}'
            usage_expr = f'sum(container_fs_usage_bytes{{{NSND}}}) / {sku}'

        # Two gauges side by side: reservation + utilization
        x_base = i * 5  # 5 wide each, 5 resources = 25, use 4+4+... let me calc
        # 24 / 5 = 4.8, use w=4 for first 4, w=8 for last
        w = 4
        if i == 4: w = 8
        x = i * 4 if i < 4 else 16

        panels.append({
            "id": nid(), "title": f"{label} - Reserved vs Used",
            "description": f"Left: percentage of {label} SKU reserved by pod requests. Right: actual {label} utilization vs SKU.",
            "type": "gauge", "datasource": ds(),
            "gridPos": {"h": 5, "w": w, "x": x, "y": y},
            "fieldConfig": {"defaults": {"unit": "percentunit", "decimals": 1, "min": 0, "max": 1.5,
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": "#73BF69", "value": None},
                    {"color": "#FF9830", "value": 0.75},
                    {"color": "#FF4040", "value": 1}]}}, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]},
                "showThresholdLabels": True, "showThresholdMarkers": True},
            "targets": refs([
                tgt(req_expr, f"Reserved", instant=True),
                tgt(usage_expr, f"Actual Used", instant=True),
            ])
        })
    y += 5

    # --- Pod count + violation reason text ---
    panels.append(stat_p(
        "Running Pods (selected scope)", "Count of pods in selected namespace(s) and node(s)",
        {"h": 3, "w": 6, "x": 0, "y": y},
        [tgt(f'count(kube_pod_info{{{NSND}}})', "Pods", instant=True)],
        color_mode="value", text_mode="value", graph_mode="area",
        thresholds={"mode": "absolute", "steps": [{"color": "#5794F2", "value": None}]}
    ))

    # Violation reason panel — shows actual values vs SKU
    panels.append(stat_p(
        "Resource Totals vs SKU Capacity",
        "Shows the absolute total reserved for each resource alongside the SKU capacity. "
        "If reserved > SKU, the resource is in violation.",
        {"h": 3, "w": 18, "x": 6, "y": y},
        [
            tgt(f'sum(kube_pod_container_resource_requests{{{NSND}, resource="nvidia.com/gpu"}})', "GPU Reserved", instant=True),
            tgt(f'vector($sku_gpu_count)', "GPU SKU", instant=True),
            tgt(f'sum(kube_pod_container_resource_requests{{{NSND}, resource="cpu"}})', "vCPU Reserved", instant=True),
            tgt(f'vector($sku_cpu_cores)', "vCPU SKU", instant=True),
            tgt(f'sum(kube_pod_container_resource_requests{{{NSND}, resource="memory"}}) / $memory_unit', "Mem Reserved", instant=True),
            tgt(f'vector($sku_memory_value)', "Mem SKU", instant=True),
        ],
        decimals=1, color_mode="value", text_mode="value_and_name", orient="horizontal",
        thresholds={"mode": "absolute", "steps": [{"color": "#73BF69", "value": None}]}
    ))
    y += 3

    # --- All pods table with NAMED columns ---
    rename_map = {
        "Value #A": "GPU Request", "Value #B": "GPU Limit",
        "Value #C": "vCPU Request", "Value #D": "vCPU Limit",
        "Value #E": "Memory Request", "Value #F": "Memory Limit",
        "Value #G": "Ephemeral Request", "Value #H": "Ephemeral Limit",
    }
    panels.append({
        "id": nid(), "title": "All Pods - Resource Requests and Limits",
        "description": "Complete table of ALL pods in selected scope with named columns for each resource request and limit.",
        "type": "table", "datasource": ds(),
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": y},
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "pod"},
                 "properties": [{"id": "custom.width", "value": 280}, {"id": "displayName", "value": "Pod"}]},
                {"matcher": {"id": "byName", "options": "namespace"},
                 "properties": [{"id": "custom.width", "value": 150}, {"id": "displayName", "value": "Namespace"}]},
                {"matcher": {"id": "byName", "options": "node"},
                 "properties": [{"id": "custom.width", "value": 180}, {"id": "displayName", "value": "Node"}]},
                {"matcher": {"id": "byRegexp", "options": ".*GPU.*"},
                 "properties": [{"id": "decimals", "value": 0},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None}, {"color": "#FF4040", "value": 1}]}}]},
                {"matcher": {"id": "byRegexp", "options": ".*vCPU.*"},
                 "properties": [{"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None}, {"color": "#FF9830", "value": 4}, {"color": "#FF4040", "value": 8}]}}]},
                {"matcher": {"id": "byRegexp", "options": ".*Memory.*"},
                 "properties": [{"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None}, {"color": "#FF9830", "value": 64}, {"color": "#FF4040", "value": 128}]}}]},
            ]},
        "options": {"showHeader": True,
            "sortBy": [{"displayName": "vCPU Request", "desc": True}],
            "footer": {"show": True, "reducer": ["sum"],
                "fields": ["GPU Request", "GPU Limit", "vCPU Request", "vCPU Limit", "Memory Request", "Memory Limit"]}},
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True},
                "renameByName": rename_map
            }}
        ],
        "targets": refs([
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{NSND}, resource="nvidia.com/gpu"}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{NSND}, resource="nvidia.com/gpu"}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{NSND}, resource="cpu"}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{NSND}, resource="cpu"}})', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{NSND}, resource="memory"}}) / $memory_unit', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{NSND}, resource="memory"}}) / $memory_unit', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_requests{{{NSND}, resource="ephemeral-storage"}}) / $storage_unit', "", fmt="table"),
            tgt(f'sum by (pod, namespace, node) (kube_pod_container_resource_limits{{{NSND}, resource="ephemeral-storage"}}) / $storage_unit', "", fmt="table"),
        ])
    })
    y += 8

    # ================================================================
    # PER-DIMENSION ROWS
    # ================================================================
    dims = [
        {"label": "GPU Count",       "resource": "nvidia.com/gpu",    "unit_var": "",               "sku_var": "$sku_gpu_count",
         "axis": "GPUs",            "divisor": "1",                  "gunit": "short",
         "req_color": "#B877D9",    "lim_color": "#FF9830"},
        {"label": "vCPU",            "resource": "cpu",               "unit_var": "",               "sku_var": "$sku_cpu_cores",
         "axis": "vCPU Cores",     "divisor": "1",                  "gunit": "short",
         "req_color": "#5794F2",    "lim_color": "#FF9830"},
        {"label": "Memory",          "resource": "memory",            "unit_var": "$memory_unit",   "sku_var": "$sku_memory_value",
         "axis": "Memory (selected unit)", "divisor": "$memory_unit", "gunit": "short",
         "req_color": "#8F3BB8",    "lim_color": "#F2CC0C"},
        {"label": "VRAM (GPU Memory)", "resource": "vram",            "unit_var": "",               "sku_var": "$sku_vram_gib",
         "axis": "VRAM (GiB)",     "divisor": "1073741824",         "gunit": "short",
         "req_color": "#F2CC0C",    "lim_color": "#FF9830"},
        {"label": "Local Storage",   "resource": "ephemeral-storage", "unit_var": "$storage_unit",  "sku_var": "$sku_storage_value",
         "axis": "Storage (selected unit)", "divisor": "$storage_unit", "gunit": "short",
         "req_color": "#56A64B",    "lim_color": "#E02F44"},
    ]

    for dim in dims:
        panels.append(row_panel(f"{dim['label']} - Resource Analysis", y)); y += 1
        r = dim["resource"]
        div = dim["divisor"]
        divs = f" / {div}" if div and div != "1" else ""

        if r == "vram":
            # VRAM uses DCGM metrics
            req_expr_pod = f'sum by (pod) (DCGM_FI_DEV_FB_USED{{{NSND}}}) / 1024'
            lim_expr_pod = f'sum by (pod) (DCGM_FI_DEV_FB_USED{{{NSND}}} + DCGM_FI_DEV_FB_FREE{{{NSND}}}) / 1024'
            req_expr_total = f'sum(DCGM_FI_DEV_FB_USED{{{NSND}}}) / 1024'
            lim_expr_total = f'sum(DCGM_FI_DEV_FB_USED{{{NSND}}} + DCGM_FI_DEV_FB_FREE{{{NSND}}}) / 1024'
            sku_total = dim["sku_var"]
        else:
            req_expr_pod = f'sum by (pod) (kube_pod_container_resource_requests{{{NSND}, resource="{r}"}}){divs}'
            lim_expr_pod = f'sum by (pod) (kube_pod_container_resource_limits{{{NSND}, resource="{r}"}}){divs}'
            req_expr_total = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="{r}"}}){divs}'
            lim_expr_total = f'sum(kube_pod_container_resource_limits{{{NSND}, resource="{r}"}}){divs}'
            sku_total = dim["sku_var"]

        # Bar chart
        panels.append(barchart_p(
            f"{dim['label']} - Requests vs Limits per Pod",
            f"Each pod's {dim['label']} request (blue) and limit (orange) side by side",
            {"h": 10, "w": 12, "x": 0, "y": y},
            [tgt(req_expr_pod, "{{pod}} Request", fmt="table"),
             tgt(lim_expr_pod, "{{pod}} Limit", fmt="table")],
            axis_label=dim["axis"], unit=dim["gunit"],
            req_color=dim["req_color"], lim_color=dim["lim_color"]
        ))

        # Gauge
        gauge_expr = f'{req_expr_total} / {sku_total}'
        panels.append(gauge_p(
            f"{dim['label']} - SKU Capacity Used",
            f"What percentage of the configured {dim['label']} SKU is consumed by pod requests",
            {"h": 5, "w": 6, "x": 12, "y": y},
            [tgt(gauge_expr, f"{dim['label']}", instant=True)]
        ))

        # Absolute totals
        panels.append(stat_p(
            f"{dim['label']} - Absolute Totals",
            f"Total {dim['label']} requests, limits, and SKU capacity side by side",
            {"h": 5, "w": 6, "x": 18, "y": y},
            [tgt(req_expr_total, "Total Reserved", instant=True),
             tgt(lim_expr_total, "Total Limits", instant=True),
             tgt(f'vector({sku_total})', "SKU Capacity", instant=True)],
            decimals=1, color_mode="value", text_mode="value_and_name", orient="horizontal",
            thresholds={"mode": "absolute", "steps": [{"color": "#73BF69", "value": None}]}
        ))
        y += 5

        # Aggregate time series with SKU line
        panels.append(ts_panel(
            f"{dim['label']} - Aggregate Reservation and Limits Over Time",
            f"Total {dim['label']} requests + limits over time. Red dashed line = SKU capacity threshold.",
            {"h": 8, "w": 12, "x": 0, "y": y},
            [tgt(req_expr_total, "Total Requests"),
             tgt(lim_expr_total, "Total Limits"),
             tgt(f'vector({sku_total})', "SKU Capacity")],
            axis_label=dim["axis"], unit=dim["gunit"],
            req_color=dim["req_color"], lim_color=dim["lim_color"]
        ))

        # Heatmap per node
        panels.append(heatmap_panel(
            f"{dim['label']} - Reservation by Node (Stacked)",
            f"How {dim['label']} reservations are distributed across nodes. Helps identify hotspots.",
            {"h": 8, "w": 12, "x": 12, "y": y},
            resource=r, divisor=div, axis_label=dim["axis"]
        ))
        y += 8

        # Per-pod time series
        panels.append(per_pod_ts(
            f"{dim['label']} - Per-Pod Actual Usage vs Requests vs Limits",
            f"Solid = actual usage, Dashed = request, Dotted = limit. "
            f"When solid exceeds dashed, the pod uses more than requested. When solid exceeds dotted, the pod exceeds its limit.",
            {"h": 10, "w": 24, "x": 0, "y": y},
            resource=r, divisor=div, axis_label=dim["axis"], unit=dim["gunit"]
        ))
        y += 10

        # Abusing pods table
        panels.append(abusing_table(
            f"{dim['label']} - Pods Exceeding Allocations",
            f"Pods where actual {dim['label']} usage exceeds their request or limit. "
            f"Positive values mean the pod is consuming more than allocated.",
            {"h": 6, "w": 24, "x": 0, "y": y},
            resource=r, divisor=div
        ))
        y += 6

    # ================================================================
    # TEMPLATING
    # ================================================================
    def unit_dropdown(name, label, desc, default_text, default_val):
        opts = [
            ("GiB (binary, 2^30 bytes)", "1073741824"),
            ("MiB (binary, 2^20 bytes)", "1048576"),
            ("TiB (binary, 2^40 bytes)", "1099511627776"),
            ("GB (decimal, 10^9 bytes)", "1000000000"),
            ("MB (decimal, 10^6 bytes)", "1000000"),
            ("TB (decimal, 10^12 bytes)", "1000000000000"),
            ("Bytes (raw)", "1"),
        ]
        return {
            "name": name, "type": "custom", "label": label,
            "current": {"selected": True, "text": default_text, "value": default_val},
            "hide": 0, "includeAll": False, "multi": False,
            "options": [{"selected": t == default_text, "text": t, "value": v} for t, v in opts],
            "query": ", ".join([f"{t.replace(',', '\\,')} : {v}" for t, v in opts]),
            "skipUrlSync": False, "description": desc
        }

    templating = {"list": [
        {"name": "datasource", "type": "datasource", "label": "Prometheus Data Source",
         "query": "prometheus", "current": {}, "hide": 0,
         "includeAll": False, "multi": False, "options": [],
         "refresh": 1, "regex": "", "skipUrlSync": False},
        {"name": "namespace", "type": "query", "label": "Namespace",
         "datasource": ds(),
         "definition": "label_values(kube_pod_info, namespace)",
         "query": {"query": "label_values(kube_pod_info, namespace)", "refId": "ns"},
         "current": {}, "hide": 0,
         "includeAll": True, "multi": True,
         "options": [], "refresh": 2, "regex": "", "sort": 1, "skipUrlSync": False},
        {"name": "node", "type": "query", "label": "Node",
         "datasource": ds(),
         "definition": 'label_values(kube_pod_info{namespace=~"$namespace"}, node)',
         "query": {"query": 'label_values(kube_pod_info{namespace=~"$namespace"}, node)', "refId": "nd"},
         "current": {}, "hide": 0,
         "includeAll": True, "multi": True,
         "options": [], "refresh": 2, "regex": "", "sort": 1, "skipUrlSync": False},
        # --- SKU inputs ---
        {"name": "sku_gpu_count", "type": "textbox", "label": "SKU: GPU Count (per node)",
         "current": {"text": "8", "value": "8"}, "hide": 0,
         "options": [{"selected": True, "text": "8", "value": "8"}],
         "query": "8", "skipUrlSync": False,
         "description": "Total number of GPUs available in the SKU (e.g. 8 for A100x8)"},
        {"name": "sku_cpu_cores", "type": "textbox", "label": "SKU: vCPU Cores",
         "current": {"text": "128", "value": "128"}, "hide": 0,
         "options": [{"selected": True, "text": "128", "value": "128"}],
         "query": "128", "skipUrlSync": False,
         "description": "Total vCPU cores in the SKU"},
        {"name": "sku_memory_value", "type": "textbox",
         "label": "SKU: Memory (in unit selected below)",
         "current": {"text": "22528", "value": "22528"}, "hide": 0,
         "options": [{"selected": True, "text": "22528", "value": "22528"}],
         "query": "22528", "skipUrlSync": False,
         "description": "Total memory in the same unit as the Memory Unit dropdown (default: 22528 GiB = 22 TiB)"},
        unit_dropdown("memory_unit", "Memory Display Unit",
                      "Unit for memory values. SKU memory value must be in this same unit.", 
                      "GiB (binary, 2^30 bytes)", "1073741824"),
        {"name": "sku_vram_gib", "type": "textbox", "label": "SKU: VRAM / GPU Memory (GiB)",
         "current": {"text": "640", "value": "640"}, "hide": 0,
         "options": [{"selected": True, "text": "640", "value": "640"}],
         "query": "640", "skipUrlSync": False,
         "description": "Total GPU VRAM in GiB (e.g. 640 GiB for 8x A100 80GB)"},
        {"name": "sku_storage_value", "type": "textbox",
         "label": "SKU: Local Storage (in unit selected below)",
         "current": {"text": "10240", "value": "10240"}, "hide": 0,
         "options": [{"selected": True, "text": "10240", "value": "10240"}],
         "query": "10240", "skipUrlSync": False,
         "description": "Total local/ephemeral storage in the same unit as the Storage Unit dropdown"},
        unit_dropdown("storage_unit", "Storage Display Unit",
                      "Unit for local/ephemeral storage values. SKU value must be in this same unit.",
                      "GiB (binary, 2^30 bytes)", "1073741824"),
    ]}

    dashboard = {
        "__inputs": [], "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "9.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"}],
        "id": None, "uid": "k8s-sku-violation-v3",
        "title": "K8s Pod Resources vs SKU Capacity",
        "description": "Monitors K8s pod resource requests, limits, and actual usage against configurable SKU capacity. "
                       "Covers GPU, vCPU, Memory, VRAM, and Local Storage with violation detection.",
        "tags": ["kubernetes", "sku", "capacity", "gpu", "resources", "violations"],
        "style": "dark", "timezone": "browser", "editable": True,
        "graphTooltip": 1, "fiscalYearStartMonth": 0, "liveNow": False,
        "refresh": "30s", "schemaVersion": 38, "version": 3,
        "time": {"from": "now-1h", "to": "now"}, "timepicker": {},
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts", "type": "dashboard"}]},
        "templating": templating,
        "panels": panels
    }
    return dashboard


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "k8s-sku-dashboard.json"
    d = build()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    pc = len(d["panels"])
    vc = len(d["templating"]["list"])
    print(f"Generated {out}: {pc} panels, {vc} template variables")
    for p in d["panels"]:
        print(f"  [{p['type']:12s}] {p.get('title', '')}")
