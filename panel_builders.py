#!/usr/bin/env python3
"""Shared Grafana panel builder functions for BMaaS Monitoring Dashboard Suite.

v4 OVERHAUL:
- All devices_* metrics → nodes_* (devices metrics not showing data)
- gauge() REMOVED — user does not want gauges anywhere
- nv_link_switches_* → gpu_nvlink_* (NVLink switch metrics showing 0)
- Leak detection REMOVED (not available)
- Node filter regex: /skt-dgx.*/ for GPU-only focus
- Dashboards 05/06 deleted — merged into 00
- Reverse sort legends on all time series
- Dashboard links include folder prefix
"""

_id = 0

def nid():
    global _id; _id += 1; return _id

def reset_ids():
    global _id; _id = 0

# ── Datasource: "Mimir BCM Metrics" ──
DS_NAME = "Mimir BCM Metrics"

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

# ── Legends — always reverse sorted ──
LEGEND_R = {"displayMode": "table", "placement": "right",
            "calcs": ["lastNotNull"], "sortBy": "Last *", "sortDesc": True}
LEGEND_F = {"displayMode": "table", "placement": "right",
            "calcs": ["min","max","mean","lastNotNull"],
            "sortBy": "Last *", "sortDesc": True}

# ── Professional palette ──
C_OK  = "#56A64B"; C_WR = "#E0A939"; C_FL = "#C04040"; C_UK = "#8F8F8F"
C_P0  = "#C04040"; C_P1 = "#E0663E"; C_P2 = "#E0A939"; C_P3 = "#7EB26D"
C_BL  = "#3274D9"; C_PU = "#8F3BB8"; C_TL = "#6ED0E0"; C_OR = "#EF843C"
C_YL  = "#F2CC0C"; C_GN = "#73BF69"; C_DK = "#1F1D2B"

# ── Filter shorthands using REAL labels ──
# entity = DGX hostname (skt-dgx filtered via template variable)
E  = 'entity=~"$node"'
CL = 'cluster=~"$cluster"'
EC = E + ',' + CL  # entity + cluster combined filter

# ── Dashboard UIDs — V6 (5 dashboards only — 05/06 deleted) ──
UIDS = {
    "00": "bmaas-00-fleet-overview-v6",
    "01": "bmaas-01-gpu-health-v6",
    "02": "bmaas-02-infra-health-v6",
    "03": "bmaas-03-network-fabric-v6",
    "04": "bmaas-04-workload-perf-v6",
}

# Folder name in Grafana where dashboards are imported
DASHBOARD_FOLDER = "BMaaS QA SKT"

def dashboard_link(uid, title):
    return f"/d/{uid}?orgId=1&var-datasource=${{datasource}}&var-node=${{node}}&var-cluster=${{cluster}}"

# ── GPU index helper ──
GPU_COUNT = 8

def gpu_metric(base, gpu_idx):
    return f"gpu{gpu_idx}_{base}"

def gpu_targets_all(base, unit_label=""):
    return [tgt(f'{gpu_metric(base, i)}{{{EC}}}', f'GPU{i}') for i in range(GPU_COUNT)]

# ── PANEL BUILDERS ──

def row(title, y, collapsed=False):
    return {"type":"row","title":title,"collapsed":collapsed,
            "gridPos":{"h":1,"w":24,"x":0,"y":y},"id":nid(),"panels":[]}

def stat(title, desc, gp, targets, unit="none", decimals=0,
         thresholds=None, color_mode="background", text_mode="value_and_name",
         graph_mode="none", mappings=None, orientation="auto"):
    """Stat panel with value_and_name to show clear labels."""
    return {"id":nid(),"title":title,"description":desc,"type":"stat",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"unit":unit,"decimals":decimals,
            "thresholds":thresholds or {"mode":"absolute","steps":[{"color":C_OK,"value":None}]},
            "mappings":mappings or [],"noValue":"N/A"},"overrides":[]},
        "options":{"reduceOptions":{"calcs":["lastNotNull"],"fields":"","values":False},
            "orientation":orientation,"textMode":text_mode,
            "colorMode":color_mode,"graphMode":graph_mode,"justifyMode":"center"},
        "targets":refs(targets)}

def ts(title, desc, gp, targets, axis, unit="short", overrides=None, stacking=None):
    custom = {"lineWidth":2,"fillOpacity":10,"gradientMode":"none",
              "axisLabel":axis,"drawStyle":"line","pointSize":4,
              "showPoints":"never","spanNulls":True}
    if stacking:
        custom["stacking"] = {"mode":stacking}; custom["fillOpacity"]=60; custom["lineWidth"]=0
    return {"id":nid(),"title":title,"description":desc,"type":"timeseries",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"unit":unit,"custom":custom},"overrides":overrides or []},
        "options":{"legend":LEGEND_F,"tooltip":{"mode":"multi","sort":"desc"}},
        "targets":refs(targets)}

def tbl(title, desc, gp, targets, transforms=None, overrides=None, sort=None):
    return {"id":nid(),"title":title,"description":desc,"type":"table",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"custom":{"align":"auto","displayMode":"auto","filterable":True}},
            "overrides":overrides or []},
        "options":{"showHeader":True,"sortBy":sort or []},
        "transformations":transforms or [],"targets":refs(targets)}

def piechart(title, desc, gp, targets, legend_placement="right"):
    return {"id":nid(),"title":title,"description":desc,"type":"piechart",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"unit":"none","decimals":0},"overrides":[]},
        "options":{"reduceOptions":{"calcs":["lastNotNull"],"fields":"","values":False},
            "pieType":"donut","tooltip":{"mode":"multi"},
            "legend":{"displayMode":"table","placement":legend_placement,
                       "calcs":["lastNotNull"]}},
        "targets":refs(targets)}

def heatmap(title, desc, gp, targets):
    return {"id":nid(),"title":title,"description":desc,"type":"state-timeline",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"custom":{"lineWidth":0,"fillOpacity":80},
            "thresholds":{"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_WR,"value":1},
                {"color":C_FL,"value":2},{"color":C_UK,"value":3}]},
            "mappings":[
                {"type":"value","options":{"0":{"text":"PASS","color":C_OK}}},
                {"type":"value","options":{"1":{"text":"WARN","color":C_WR}}},
                {"type":"value","options":{"2":{"text":"FAIL","color":C_FL}}},
                {"type":"value","options":{"3":{"text":"UNK","color":C_UK}}}]},"overrides":[]},
        "options":{"showValue":"auto","mergeValues":True,"alignValue":"center",
            "rowHeight":0.85,"tooltip":{"mode":"multi"},
            "legend":{"displayMode":"list","placement":"bottom"}},
        "targets":refs(targets)}

def bargauge(title, desc, gp, targets, unit="none", orientation="horizontal",
             thresholds=None):
    return {"id":nid(),"title":title,"description":desc,"type":"bargauge",
        "datasource":ds(),"gridPos":gp,
        "fieldConfig":{"defaults":{"unit":unit,"decimals":0,
            "thresholds":thresholds or {"mode":"absolute","steps":[
                {"color":C_OK,"value":None},{"color":C_WR,"value":50},
                {"color":C_FL,"value":80}]},
            "noValue":"N/A"},"overrides":[]},
        "options":{"reduceOptions":{"calcs":["lastNotNull"],"fields":"","values":False},
            "orientation":orientation,"displayMode":"gradient",
            "showUnfilled":True},
        "targets":refs(targets)}

def text_panel(title, content, gp):
    return {"id":nid(),"title":title,"type":"text",
        "gridPos":gp,
        "options":{"mode":"markdown","content":content}}

# ── DASHBOARD WRAPPER ──

def wrap_dashboard(uid, title, description, tags, panels, templating,
                   time_from="now-6h", refresh="30s", links=None):
    d = {
        "__inputs":[],"__requires":[
            {"type":"grafana","id":"grafana","name":"Grafana","version":"9.0.0"},
            {"type":"datasource","id":"prometheus","name":"Prometheus","version":"1.0.0"}],
        "id":None,"uid":uid,
        "title":title,"description":description,
        "tags":tags,
        "style":"dark","timezone":"browser","editable":True,
        "graphTooltip":1,"fiscalYearStartMonth":0,"liveNow":False,
        "refresh":refresh,"schemaVersion":38,"version":1,
        "time":{"from":time_from,"to":"now"},"timepicker":{},
        "annotations":{"list":[{"builtIn":1,"datasource":{"type":"grafana","uid":"-- Grafana --"},
            "enable":True,"hide":True,"iconColor":"rgba(0, 211, 255, 1)",
            "name":"Annotations & Alerts","type":"dashboard"}]},
        "templating":templating,"panels":panels
    }
    if links:
        d["links"] = links
    return d

# ── STANDARD TEMPLATE VARIABLES ──
# Datasource = "Mimir BCM Metrics", cluster = "su56", node = entity regex /skt-dgx.*/

def standard_templating(extra_vars=None):
    vars_list = [
        {"name":"datasource","type":"datasource","label":"Data Source",
         "query":"prometheus",
         "current":{"text":"Mimir BCM Metrics","value":"Mimir BCM Metrics"},
         "hide":0,
         "includeAll":False,"multi":False,"options":[],"refresh":1,"regex":"","skipUrlSync":False},
        {"name":"cluster","type":"query","label":"Cluster",
         "datasource":ds(),
         "definition":"label_values(up, cluster)",
         "query":{"query":"label_values(up, cluster)","refId":"cl"},
         "current":{"text":"su56","value":"su56"},
         "hide":0,"includeAll":False,"multi":False,
         "options":[],"refresh":2,"regex":"","sort":1,"skipUrlSync":False},
        {"name":"node","type":"query","label":"Node (DGX)",
         "datasource":ds(),
         "definition":"label_values({cluster=~\"$cluster\"}, entity)",
         "query":{"query":"label_values({cluster=~\"$cluster\"}, entity)","refId":"nd"},
         "current":{},
         "hide":0,"includeAll":True,"multi":True,
         "allValue":"skt-dgx.*",
         "options":[],"refresh":2,"regex":"/skt-dgx.*/","sort":1,"skipUrlSync":False},
    ]
    if extra_vars:
        vars_list.extend(extra_vars)
    return {"list": vars_list}

# ── DASHBOARD NAV LINKS (5 dashboards only) ──

def sub_dashboard_links():
    return [
        {"title":"00 Executive Fleet Overview","type":"link","icon":"dashboard",
         "url":dashboard_link(UIDS["00"],"Executive"),"targetBlank":False},
        {"title":"01 GPU Health & Diagnostics","type":"link","icon":"dashboard",
         "url":dashboard_link(UIDS["01"],"GPU Health"),"targetBlank":False},
        {"title":"02 Infrastructure & Hardware","type":"link","icon":"dashboard",
         "url":dashboard_link(UIDS["02"],"Infrastructure"),"targetBlank":False},
        {"title":"03 Network Fabric","type":"link","icon":"dashboard",
         "url":dashboard_link(UIDS["03"],"Network"),"targetBlank":False},
        {"title":"04 Workload & Jobs","type":"link","icon":"dashboard",
         "url":dashboard_link(UIDS["04"],"Workload"),"targetBlank":False},
    ]
