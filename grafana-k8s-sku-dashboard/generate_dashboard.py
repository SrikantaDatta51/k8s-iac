#!/usr/bin/env python3
"""Generate the K8s SKU Violation Grafana Dashboard JSON - v4.
Fixes: GPU uses kube-state-metrics + Run.ai fallback, ephemeral uses
kube_pod_container_resource_requests{resource="ephemeral-storage"},
bar charts replaced with clean tables + heatmaps.
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

def heatmap_table(title, desc, gp, req_expr, lim_expr, req_label, lim_label):
    """Table with gradient-gauge columns instead of rainbow bar chart."""
    return {
        "id": nid(), "title": title, "description": desc, "type": "table",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Pod"},
                 "properties": [{"id": "custom.width", "value": 300}]},
                {"matcher": {"id": "byName", "options": "Node"},
                 "properties": [{"id": "custom.width", "value": 200}]},
                {"matcher": {"id": "byName", "options": "Namespace"},
                 "properties": [{"id": "custom.width", "value": 150}]},
                {"matcher": {"id": "byName", "options": req_label},
                 "properties": [{"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "percentage", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 60},
                        {"color": "#FF4040", "value": 85}]}}]},
                {"matcher": {"id": "byName", "options": lim_label},
                 "properties": [{"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "percentage", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 60},
                        {"color": "#FF4040", "value": 85}]}}]},
            ]},
        "options": {"showHeader": True, "sortBy": [{"displayName": req_label, "desc": True}],
            "footer": {"show": True, "reducer": ["sum"], "fields": [req_label, lim_label]}},
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True},
                "renameByName": {"pod": "Pod", "namespace": "Namespace", "node": "Node",
                    "Value #A": req_label, "Value #B": lim_label}}}
        ],
        "targets": refs([
            tgt(req_expr, "", fmt="table"),
            tgt(lim_expr, "", fmt="table"),
        ])
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
        {"matcher": {"id": "byRegexp", "options": ".*Request.*|.*Reserved.*"},
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

def per_pod_ts(title, desc, gp, usage_expr, req_expr, lim_expr, axis_label, unit="short"):
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
        "targets": refs([tgt(usage_expr, "{{pod}} Actual"),
                         tgt(req_expr, "{{pod}} Request"),
                         tgt(lim_expr, "{{pod}} Limit")])
    }

def node_stacked(title, desc, gp, expr, axis_label):
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

def abusing_table(title, desc, gp, usage_expr, req_expr, lim_expr):
    return {
        "id": nid(), "title": title, "description": desc, "type": "table",
        "datasource": ds(), "gridPos": gp,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Excess Over Request"},
                 "properties": [{"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 0.01},
                        {"color": "#FF4040", "value": 1}]}}]},
                {"matcher": {"id": "byName", "options": "Excess Over Limit"},
                 "properties": [{"id": "decimals", "value": 2},
                    {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None},
                        {"color": "#FF9830", "value": 0.01},
                        {"color": "#FF4040", "value": 1}]}}]}
            ]},
        "options": {"showHeader": True, "sortBy": [{"displayName": "Excess Over Request", "desc": True}],
            "footer": {"show": False}},
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True},
                "renameByName": {"pod": "Pod", "namespace": "Namespace", "node": "Node",
                    "Value #A": "Excess Over Request", "Value #B": "Excess Over Limit"}}}
        ],
        "targets": refs([
            tgt(f'({usage_expr} - {req_expr}) > 0', "", fmt="table"),
            tgt(f'({usage_expr} - {lim_expr}) > 0', "", fmt="table"),
        ])
    }


# ===================================================================
# Dimension Definitions
# ===================================================================
# Each dimension defines its metric expressions and display properties.
# GPU metrics: kube_pod_container_resource_requests{resource="nvidia.com/gpu"}
#   is the standard kube-state-metrics metric for GPU allocation.
#   For actual usage: DCGM (DCGM_FI_DEV_GPU_UTIL) or Run.ai (runai_gpu_utilization).
#   We use kube-state-metrics for requests/limits and provide DCGM for usage.
# Ephemeral: kube_pod_container_resource_requests{resource="ephemeral-storage"}
#   and kube_pod_container_resource_limits{resource="ephemeral-storage"}.
# ===================================================================

def dim_exprs(resource, divisor):
    """Generate standard PromQL expressions for a kube-state-metrics resource."""
    by_pod = 'pod, namespace, node'
    f = NSND
    return {
        "req_pod": f'sum by ({by_pod}) (kube_pod_container_resource_requests{{{f}, resource="{resource}"}}){divisor}',
        "lim_pod": f'sum by ({by_pod}) (kube_pod_container_resource_limits{{{f}, resource="{resource}"}}){divisor}',
        "req_total": f'sum(kube_pod_container_resource_requests{{{f}, resource="{resource}"}}){divisor}',
        "lim_total": f'sum(kube_pod_container_resource_limits{{{f}, resource="{resource}"}}){divisor}',
        "req_by_node": f'sum by (node) (kube_pod_container_resource_requests{{{NS}, resource="{resource}"}}){divisor}',
    }


def build():
    panels = []
    y = 0

    ok_viol_map = [{"type": "value", "options": {
        "0": {"text": "WITHIN LIMITS", "color": "#73BF69", "index": 0},
        "1": {"text": "EXCEEDS SKU", "color": "#FF4040", "index": 1}}}]

    # All 5 dimensions with their expressions
    dimensions = []

    # 1. GPU Count
    gpu = dim_exprs("nvidia.com/gpu", "")
    gpu["label"] = "GPU"
    gpu["sku_var"] = "$sku_gpu_count"
    gpu["axis"] = "GPU Count"
    gpu["usage_pod"] = f'sum by (pod, namespace, node) (DCGM_FI_DEV_GPU_UTIL{{{NSND}}}) / 100'
    gpu["usage_total"] = f'sum(DCGM_FI_DEV_GPU_UTIL{{{NSND}}}) / 100'
    gpu["req_color"] = "#B877D9"
    gpu["lim_color"] = "#FF9830"
    dimensions.append(gpu)

    # 2. vCPU
    cpu = dim_exprs("cpu", "")
    cpu["label"] = "vCPU"
    cpu["sku_var"] = "$sku_cpu_cores"
    cpu["axis"] = "vCPU Cores"
    cpu["usage_pod"] = f'sum by (pod, namespace, node) (rate(container_cpu_usage_seconds_total{{{NSND}}}[5m]))'
    cpu["usage_total"] = f'sum(rate(container_cpu_usage_seconds_total{{{NSND}}}[5m]))'
    cpu["req_color"] = "#5794F2"
    cpu["lim_color"] = "#FF9830"
    dimensions.append(cpu)

    # 3. Memory
    mem = dim_exprs("memory", " / $memory_unit")
    mem["label"] = "Memory"
    mem["sku_var"] = "$sku_memory_value"
    mem["axis"] = "Memory (selected unit)"
    mem["usage_pod"] = f'sum by (pod, namespace, node) (container_memory_working_set_bytes{{{NSND}}}) / $memory_unit'
    mem["usage_total"] = f'sum(container_memory_working_set_bytes{{{NSND}}}) / $memory_unit'
    mem["req_color"] = "#8F3BB8"
    mem["lim_color"] = "#F2CC0C"
    dimensions.append(mem)

    # 4. VRAM (GPU Memory)
    vram = dim_exprs("nvidia.com/gpu", "")  # requests are GPU count, not VRAM
    vram["label"] = "VRAM (GPU Memory)"
    vram["sku_var"] = "$sku_vram_gib"
    vram["axis"] = "VRAM (GiB)"
    # Override with DCGM metrics for VRAM
    vram["req_pod"] = f'sum by (pod, namespace, node) (DCGM_FI_DEV_FB_USED{{{NSND}}}) / 1024'
    vram["lim_pod"] = f'sum by (pod, namespace, node) (DCGM_FI_DEV_FB_USED{{{NSND}}} + DCGM_FI_DEV_FB_FREE{{{NSND}}}) / 1024'
    vram["req_total"] = f'sum(DCGM_FI_DEV_FB_USED{{{NSND}}}) / 1024'
    vram["lim_total"] = f'sum(DCGM_FI_DEV_FB_USED{{{NSND}}} + DCGM_FI_DEV_FB_FREE{{{NSND}}}) / 1024'
    vram["req_by_node"] = f'sum by (node) (DCGM_FI_DEV_FB_USED{{{NS}}}) / 1024'
    vram["usage_pod"] = vram["req_pod"]
    vram["usage_total"] = vram["req_total"]
    vram["req_color"] = "#F2CC0C"
    vram["lim_color"] = "#FF9830"
    dimensions.append(vram)

    # 5. Local Storage (Ephemeral)
    eph = dim_exprs("ephemeral-storage", " / $storage_unit")
    eph["label"] = "Local Storage (Ephemeral)"
    eph["sku_var"] = "$sku_storage_value"
    eph["axis"] = "Storage (selected unit)"
    eph["usage_pod"] = f'sum by (pod, namespace, node) (container_fs_usage_bytes{{{NSND}}}) / $storage_unit'
    eph["usage_total"] = f'sum(container_fs_usage_bytes{{{NSND}}}) / $storage_unit'
    eph["req_color"] = "#56A64B"
    eph["lim_color"] = "#E02F44"
    dimensions.append(eph)

    # ================================================================
    # ROW 1: SKU Violation Summary
    # ================================================================
    panels.append(row_panel("SKU Violation Summary", y)); y += 1

    for i, d in enumerate(dimensions):
        # Calculate violation expression
        if d["label"] == "VRAM (GPU Memory)":
            viol = f'clamp_max(ceil({d["req_total"]} / {d["sku_var"]}), 1)'
        elif d["label"] == "Memory":
            viol = f'clamp_max(ceil(sum(kube_pod_container_resource_requests{{{NSND}, resource="memory"}}) / ($sku_memory_value * $memory_unit)), 1)'
        elif d["label"] == "Local Storage (Ephemeral)":
            viol = f'clamp_max(ceil(sum(kube_pod_container_resource_requests{{{NSND}, resource="ephemeral-storage"}}) / ($sku_storage_value * $storage_unit)), 1)'
        else:
            res_name = "nvidia.com/gpu" if d["label"] == "GPU" else "cpu"
            viol = f'clamp_max(ceil(sum(kube_pod_container_resource_requests{{{NSND}, resource="{res_name}"}}) / {d["sku_var"]}), 1)'
        
        w = 5 if i < 4 else 4
        x = i * 5 if i < 4 else 20
        panels.append(stat_p(
            f"{d['label']} - SKU Status",
            f"Whether total {d['label']} requests exceed the configured SKU capacity. "
            f"EXCEEDS SKU = sum of pod reservations > SKU value you entered.",
            {"h": 4, "w": w, "x": x, "y": y},
            [tgt(viol, d["label"], instant=True)],
            mappings=ok_viol_map
        ))
    y += 4

    # --- Violation reason: absolute totals vs SKU ---
    panels.append(stat_p(
        "Resource Reservation Totals vs SKU Capacity (why violation occurs)",
        "Shows the total reserved amount for each resource alongside its SKU capacity. "
        "If Reserved > SKU, that resource is in violation. Compare these numbers directly.",
        {"h": 4, "w": 24, "x": 0, "y": y},
        [
            tgt(f'sum(kube_pod_container_resource_requests{{{NSND}, resource="nvidia.com/gpu"}})', "GPU Reserved", instant=True),
            tgt(f'vector($sku_gpu_count)', "GPU SKU Cap", instant=True),
            tgt(f'sum(kube_pod_container_resource_requests{{{NSND}, resource="cpu"}})', "vCPU Reserved", instant=True),
            tgt(f'vector($sku_cpu_cores)', "vCPU SKU Cap", instant=True),
            tgt(f'sum(kube_pod_container_resource_requests{{{NSND}, resource="memory"}}) / $memory_unit', "Mem Reserved", instant=True),
            tgt(f'vector($sku_memory_value)', "Mem SKU Cap", instant=True),
        ],
        decimals=1, color_mode="value", text_mode="value_and_name", orient="horizontal",
        thresholds={"mode": "absolute", "steps": [{"color": "#73BF69", "value": None}]}
    ))
    y += 4

    # ================================================================
    # ROW 2: Reservation vs Utilization
    # ================================================================
    panels.append(row_panel("SKU Capacity - Reservation vs Actual Utilization", y)); y += 1

    for i, d in enumerate(dimensions):
        if d["label"] == "Memory":
            sku_full = f'($sku_memory_value * $memory_unit)'
            req_pct = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="memory"}}) / {sku_full}'
            use_pct = f'sum(container_memory_working_set_bytes{{{NSND}}}) / {sku_full}'
        elif d["label"] == "Local Storage (Ephemeral)":
            sku_full = f'($sku_storage_value * $storage_unit)'
            req_pct = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="ephemeral-storage"}}) / {sku_full}'
            use_pct = f'sum(container_fs_usage_bytes{{{NSND}}}) / {sku_full}'
        elif d["label"] == "VRAM (GPU Memory)":
            req_pct = f'{d["req_total"]} / {d["sku_var"]}'
            use_pct = req_pct
        else:
            req_pct = f'{d["req_total"]} / {d["sku_var"]}'
            use_pct = f'{d["usage_total"]} / {d["sku_var"]}'

        w = 5 if i < 4 else 4
        x = i * 5 if i < 4 else 20
        panels.append({
            "id": nid(), "title": f"{d['label']} - Reserved vs Used",
            "description": f"Reserved = % of SKU claimed by pod requests. Used = actual utilization.",
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
                tgt(req_pct, "Reserved", instant=True),
                tgt(use_pct, "Actual Used", instant=True),
            ])
        })
    y += 5

    # Pod count
    panels.append(stat_p(
        "Running Pods (selected scope)", "Total pods in selected namespace(s) / node(s)",
        {"h": 3, "w": 6, "x": 0, "y": y},
        [tgt(f'count(kube_pod_info{{{NSND}}})', "Pods", instant=True)],
        color_mode="value", text_mode="value", graph_mode="area",
        thresholds={"mode": "absolute", "steps": [{"color": "#5794F2", "value": None}]}
    ))
    y += 3

    # ================================================================
    # All Pods Table
    # ================================================================
    rename = {"Value #A": "GPU Req", "Value #B": "GPU Lim",
              "Value #C": "vCPU Req", "Value #D": "vCPU Lim",
              "Value #E": "Mem Req", "Value #F": "Mem Lim",
              "Value #G": "Eph Req", "Value #H": "Eph Lim",
              "pod": "Pod", "namespace": "Namespace", "node": "Node"}
    panels.append({
        "id": nid(), "title": "All Pods - Resource Requests and Limits",
        "description": "Every pod in scope with named columns. GPU=count, vCPU=cores, Memory/Ephemeral=selected unit.",
        "type": "table", "datasource": ds(),
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": y},
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "displayMode": "auto", "filterable": True}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "Pod"}, "properties": [{"id": "custom.width", "value": 280}]},
                {"matcher": {"id": "byName", "options": "Namespace"}, "properties": [{"id": "custom.width", "value": 140}]},
                {"matcher": {"id": "byName", "options": "Node"}, "properties": [{"id": "custom.width", "value": 180}]},
                {"matcher": {"id": "byRegexp", "options": "GPU.*"},
                 "properties": [{"id": "decimals", "value": 0}, {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None}, {"color": "#FF4040", "value": 1}]}}]},
                {"matcher": {"id": "byRegexp", "options": "vCPU.*"},
                 "properties": [{"id": "decimals", "value": 2}, {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None}, {"color": "#FF9830", "value": 4}, {"color": "#FF4040", "value": 8}]}}]},
                {"matcher": {"id": "byRegexp", "options": "Mem.*|Eph.*"},
                 "properties": [{"id": "decimals", "value": 2}, {"id": "custom.displayMode", "value": "gradient-gauge"},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                        {"color": "#73BF69", "value": None}, {"color": "#FF9830", "value": 64}, {"color": "#FF4040", "value": 128}]}}]},
            ]},
        "options": {"showHeader": True, "sortBy": [{"displayName": "vCPU Req", "desc": True}],
            "footer": {"show": True, "reducer": ["sum"],
                "fields": ["GPU Req", "GPU Lim", "vCPU Req", "vCPU Lim", "Mem Req", "Mem Lim", "Eph Req", "Eph Lim"]}},
        "transformations": [
            {"id": "merge", "options": {}},
            {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True},
                "renameByName": rename}}
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
    # PER-DIMENSION ANALYSIS ROWS
    # ================================================================
    for d in dimensions:
        panels.append(row_panel(f"{d['label']} - Resource Analysis", y)); y += 1

        # 1. Heatmap table (request + limit per pod, gradient gauges) - replaces rainbow bar chart
        panels.append(heatmap_table(
            f"{d['label']} - Request and Limit per Pod",
            f"Each pod's {d['label']} request and limit shown as gradient gauges. Sorted by highest request. Footer = sum total.",
            {"h": 8, "w": 12, "x": 0, "y": y},
            d["req_pod"], d["lim_pod"],
            f"{d['label']} Request", f"{d['label']} Limit"
        ))

        # 2. Gauge: SKU capacity used
        if d["label"] == "Memory":
            gauge_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="memory"}}) / ($sku_memory_value * $memory_unit)'
        elif d["label"] == "Local Storage (Ephemeral)":
            gauge_expr = f'sum(kube_pod_container_resource_requests{{{NSND}, resource="ephemeral-storage"}}) / ($sku_storage_value * $storage_unit)'
        else:
            gauge_expr = f'{d["req_total"]} / {d["sku_var"]}'
        panels.append(gauge_p(
            f"{d['label']} - SKU Capacity Used",
            f"% of configured {d['label']} SKU consumed by total pod requests",
            {"h": 4, "w": 6, "x": 12, "y": y},
            [tgt(gauge_expr, d["label"], instant=True)]
        ))

        # 3. Absolute totals
        panels.append(stat_p(
            f"{d['label']} - Absolute Totals",
            f"Total {d['label']} reserved, limits, and SKU capacity",
            {"h": 4, "w": 6, "x": 18, "y": y},
            [tgt(d["req_total"], "Total Reserved", instant=True),
             tgt(d["lim_total"], "Total Limits", instant=True),
             tgt(f'vector({d["sku_var"]})', "SKU Capacity", instant=True)],
            decimals=1, color_mode="value", text_mode="value_and_name", orient="horizontal",
            thresholds={"mode": "absolute", "steps": [{"color": "#73BF69", "value": None}]}
        ))
        y += 4

        # 4. Time series: aggregate reservation + limits + SKU threshold
        panels.append(ts_panel(
            f"{d['label']} - Aggregate Reservation and Limits Over Time",
            f"Total {d['label']} requests + limits over time. Red dashed = SKU capacity.",
            {"h": 8, "w": 12, "x": 0, "y": y + 4},
            [tgt(d["req_total"], "Total Reserved"),
             tgt(d["lim_total"], "Total Limits"),
             tgt(f'vector({d["sku_var"]})', "SKU Capacity")],
            axis_label=d["axis"],
            req_color=d["req_color"], lim_color=d["lim_color"]
        ))

        # 5. Node stacked reservation
        panels.append(node_stacked(
            f"{d['label']} - Reservation by Node (Stacked)",
            f"How {d['label']} reservations distribute across nodes. Each color = a node.",
            {"h": 8, "w": 12, "x": 12, "y": y + 4},
            d["req_by_node"], d["axis"]
        ))
        y += 12

        # 6. Per-pod actual vs request vs limit time series
        panels.append(per_pod_ts(
            f"{d['label']} - Per-Pod Actual Usage vs Requests vs Limits",
            f"Solid = actual usage, Dashed = request, Dotted red = limit. "
            f"When actual exceeds request, the pod is over-consuming vs its reservation.",
            {"h": 10, "w": 24, "x": 0, "y": y},
            d["usage_pod"], d["req_pod"], d["lim_pod"],
            axis_label=d["axis"]
        ))
        y += 10

        # 7. Abusing pods table
        panels.append(abusing_table(
            f"{d['label']} - Pods Exceeding Allocations",
            f"Pods whose actual {d['label']} usage exceeds their request or limit.",
            {"h": 6, "w": 24, "x": 0, "y": y},
            d["usage_pod"], d["req_pod"], d["lim_pod"]
        ))
        y += 6

    # ================================================================
    # TEMPLATING
    # ================================================================
    def unit_dd(name, label, desc, default_text, default_val):
        opts = [
            ("GiB (2^30 bytes)", "1073741824"),
            ("MiB (2^20 bytes)", "1048576"),
            ("TiB (2^40 bytes)", "1099511627776"),
            ("GB (10^9 bytes)", "1000000000"),
            ("MB (10^6 bytes)", "1000000"),
            ("TB (10^12 bytes)", "1000000000000"),
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
        {"name": "sku_gpu_count", "type": "textbox", "label": "SKU: GPU Count",
         "current": {"text": "8", "value": "8"}, "hide": 0,
         "options": [{"selected": True, "text": "8", "value": "8"}],
         "query": "8", "skipUrlSync": False,
         "description": "Total GPUs in the SKU (e.g. 8 for A100x8 node)"},
        {"name": "sku_cpu_cores", "type": "textbox", "label": "SKU: vCPU Cores",
         "current": {"text": "128", "value": "128"}, "hide": 0,
         "options": [{"selected": True, "text": "128", "value": "128"}],
         "query": "128", "skipUrlSync": False},
        {"name": "sku_memory_value", "type": "textbox",
         "label": "SKU: Memory (in unit below)",
         "current": {"text": "22528", "value": "22528"}, "hide": 0,
         "options": [{"selected": True, "text": "22528", "value": "22528"}],
         "query": "22528", "skipUrlSync": False,
         "description": "Total memory in the same unit as Memory Unit dropdown (22528 GiB = 22 TiB)"},
        unit_dd("memory_unit", "Memory Unit",
                "Unit for memory. SKU memory value must be in this unit.",
                "GiB (2^30 bytes)", "1073741824"),
        {"name": "sku_vram_gib", "type": "textbox", "label": "SKU: VRAM (GiB)",
         "current": {"text": "640", "value": "640"}, "hide": 0,
         "options": [{"selected": True, "text": "640", "value": "640"}],
         "query": "640", "skipUrlSync": False,
         "description": "Total GPU VRAM in GiB (640 GiB = 8x A100 80GB)"},
        {"name": "sku_storage_value", "type": "textbox",
         "label": "SKU: Local Storage (in unit below)",
         "current": {"text": "10", "value": "10"}, "hide": 0,
         "options": [{"selected": True, "text": "10", "value": "10"}],
         "query": "10", "skipUrlSync": False,
         "description": "Total local/ephemeral storage in the unit selected below"},
        unit_dd("storage_unit", "Storage Unit",
                "Unit for local storage. SKU value must be in this unit.",
                "TB (10^12 bytes)", "1000000000000"),
    ]}

    return {
        "__inputs": [], "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "9.0.0"},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0"}],
        "id": None, "uid": "k8s-sku-violation-v4",
        "title": "K8s Pod Resources vs SKU Capacity",
        "description": "Monitors K8s pod GPU, vCPU, Memory, VRAM, and Local Storage against configurable SKU capacity.",
        "tags": ["kubernetes", "sku", "capacity", "gpu", "resources"],
        "style": "dark", "timezone": "browser", "editable": True,
        "graphTooltip": 1, "fiscalYearStartMonth": 0, "liveNow": False,
        "refresh": "30s", "schemaVersion": 38, "version": 4,
        "time": {"from": "now-1h", "to": "now"}, "timepicker": {},
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
            "name": "Annotations & Alerts", "type": "dashboard"}]},
        "templating": templating,
        "panels": panels
    }


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
