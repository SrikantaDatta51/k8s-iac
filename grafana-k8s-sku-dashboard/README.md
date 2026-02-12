# K8s Pod Resources vs SKU Capacity — Grafana Dashboard (v3)

Monitors Kubernetes pod resource **requests, limits, and actual usage** against configurable **SKU capacity** with **violation detection**, covering **GPU, vCPU, Memory, VRAM, and Local Storage**.

## Prerequisites

- **Grafana** >= 9.x
- **Prometheus** with:
  - **kube-state-metrics** — `kube_pod_container_resource_requests`, `kube_pod_container_resource_limits`, `kube_pod_info`
  - **cAdvisor/kubelet** — `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `container_fs_usage_bytes`
  - **DCGM Exporter** (for GPU/VRAM) — `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_FB_USED`, `DCGM_FI_DEV_FB_FREE`

## Import

Grafana → Dashboards → Import → upload `k8s-sku-dashboard.json`

## Template Variables (10)

| Variable | Type | Purpose | Default |
|---|---|---|---|
| Prometheus Data Source | Datasource | Select Prometheus | — |
| **Namespace** | Query | **Multi-select**, includes "All" | All |
| **Node** | Query | **Multi-select**, includes "All" | All |
| SKU: GPU Count | Textbox | GPUs per node | `8` |
| SKU: vCPU Cores | Textbox | Total vCPUs | `128` |
| SKU: Memory | Textbox | In selected unit below | `22528` |
| **Memory Display Unit** | **Dropdown** | GiB/MiB/TiB/GB/MB/TB/Bytes | GiB |
| SKU: VRAM (GiB) | Textbox | GPU memory | `640` |
| SKU: Local Storage | Textbox | In selected unit below | `10240` |
| **Storage Display Unit** | **Dropdown** | GiB/MiB/TiB/GB/MB/TB/Bytes | GiB |

## Dashboard Layout (55 panels)

### SKU Violation Summary
- 5 status indicators: GPU, vCPU, Memory, VRAM, Local Storage (WITHIN LIMITS / EXCEEDS SKU)
- Violation descriptions showing why SKU is exceeded

### Reservation vs Actual Utilization
- 5 dual gauges showing reserved % and actual usage % per resource
- Pod count + resource totals vs SKU capacity table

### All Pods Table
- Named columns: GPU/vCPU/Memory/Ephemeral Request and Limit (no more Value#A/B/C)
- Shows pod, namespace, and node for cross-namespace visibility
- Sum footer row

### Per-Dimension Rows (GPU, vCPU, Memory, VRAM, Local Storage)
Each has 7 panels:
- Requests vs Limits per Pod (bar chart)
- SKU Capacity Used (gauge)
- Absolute Totals (stat)
- Aggregate Reservation Over Time with SKU threshold line (time series)
- **Reservation by Node — stacked** (heatmap-style, stacked bars per node)
- **Per-Pod Actual Usage vs Requests vs Limits** (solid=usage, dashed=request, dotted=limit)
- **Pods Exceeding Allocations** (table with named columns)

## Key Fixes in v3

| Issue | Fix |
|---|---|
| Namespace single-select only | Now **multi-select** with "All" option |
| Node single-select only | Now **multi-select** with "All" option |
| Table columns: Value#A, Value#B | Fixed via `renameByName` transformations |
| No GPU/VRAM dimension | Added GPU Count + VRAM (DCGM metrics) |
| Ephemeral storage empty | Uses `ephemeral-storage` resource + `container_fs_usage_bytes` |
| No reason for violation | Added "Resource Totals vs SKU" panel showing absolutes |
| No reservation vs utilization | Added dual gauges per resource |
| No per-node view | Added stacked node reservation panels |

## Regenerate

```bash
python3 generate_dashboard.py k8s-sku-dashboard.json
```
