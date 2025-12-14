# K8s Infrastructure as Code (KVM, GitOps, Self-Healing)

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
    - [Topology (Hub-Spoke)](#21-topology-hub-spoke)
    - [GitOps Flow](#22-gitops-flow)
3. [Repository Structure](#3-repository-structure)
4. [Core Features](#4-core-features)
    - [Proactive Management (Maintenance)](#41-proactive-management-maintenance)
    - [Reactive Management (Self-Healing)](#42-reactive-management-self-healing)
5. [Prerequisites](#5-prerequisites)
6. [Quick Start Guide](#6-quick-start-guide)
    - [Step 1: Provision VMs](#step-1-provision-vms)
    - [Step 2: Bootstrap Clusters](#step-2-bootstrap-clusters)
    - [Step 3: Deploy Management Suites](#step-3-deploy-management-suites)
7. [Operational Manual](#7-operational-manual)
    - [Accessing Velero UI](#accessing-velero-ui)
    - [Triggering Manual Maintenance](#triggering-manual-maintenance)
    - [Simulating Node Failure](#simulating-node-failure)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Executive Summary
This project provides a production-grade, on-premise Kubernetes infrastructure solution using **KVM** for virtualization and **GitOps** for configuration management. Unlike standard installers, this repo includes a sophisticated **Day-2 Operations Suite** pre-integrated.

**Key Capabilities**:
*   **Infrastructure**: Scripts to provision 9 VMs across 3 Clusters (Command, GPU, CPU) via `virsh/virt-install`.
*   **Proactive Maintenance**: A `proactive-maintenance` namespace running 10+ scheduled CronJobs to prevent rot (Etcd defrag, Cert audits, Log cleaning).
*   **Reactive Self-Healing**: A `reactive-maintenance` namespace using Medik8s (NHC/SNR) and Node Problem Detector to automatically reboot nodes upon detecting deeply embedded failures (Kernel deadlocks, Read-only filesystems).
*   **Observability**: Integrated Prometheus-ready metrics, Velero Backups, and GPU capacity reporting.

---

## 2. Architecture Overview

### 2.1 Topology (Hub-Spoke)
We utilize a multi-cluster architecture centered around a "Command" cluster that manages downstream fleets.

```mermaid
graph TD
    User([Operator]) -->|GitOps| Repo[Git Repository]
    Repo -->|Sync| Argo[ArgoCD (Command Cluster)]
    
    subgraph "Command Cluster - Hub"
        Argo
        Karmada[Karmada Control Plane]
        Gitea[Gitea Source]
    end
    
    subgraph "GPU Cluster - Spoke A"
        GPU_Worker[GPU Nodes]
        Proactive_A[Proactive Maintenance]
        Reactive_A[Reactive Self-Healing]
    end
    
    subgraph "CPU Cluster - Spoke B"
        CPU_Worker[CPU Nodes]
        Proactive_B[Proactive Maintenance]
        Reactive_B[Reactive Self-Healing]
    end
    
    Argo -->|Deploy| Command Cluster
    Argo -->|Deploy| GPU Cluster
    Argo -->|Deploy| CPU Cluster
```

### 2.2 GitOps Flow
1.  **Commit**: Changes are pushed to `main`.
2.  **ArgoCD**: Detects drift in `cluster-configs/`.
3.  **Sync**: Applies Helm charts (`proactive-management`, `reactive-management`) to target clusters.
4.  **Feedback**: Status reported back to ArgoCD UI.

---

## 3. Repository Structure

```tree
k8s-iac/
├── cluster-bootstrap/       # Scripts to install K8s (kubeadm/crio) inside VMs
├── cluster-configs/         # Manifests & Charts for Day-2 Ops
│   ├── command-cluster/     # Hub-specific apps (ArgoCD, Karmada)
│   ├── gpu-cluster/         # GPU-specific apps (Nvidia Plugin)
│   └── manifests/           # Shared manifests (Aliases, Users)
├── cp-paas-iac-reference/   # REFERENCE ARCHITECTURE (The Core Logic)
│   ├── charts/              # Custom Helm Charts
│   │   ├── proactive-management/  # Chart: CronJobs, Scripts, Velero
│   │   └── reactive-management/   # Chart: Medik8s, NPD, Policies
│   ├── components/          # Reusable component definitions
│   └── uber/                # Aggregator charts
├── docs/                    # Architecture Designs & Verification Docs
├── vm-provisioning/         # Scripts to create KVM VMs on Host
└── README.md                # This file
```

---

## 4. Core Features

### 4.1 Proactive Management (Maintenance)
*Located in: `cp-paas-iac-reference/charts/proactive-management`*

This suite runs scheduled tasks to prevent cluster degradation. It strictly follows a "Controller-Agent" pattern using K8s CronJobs.

| Service | Schedule | Function |
|---|---|---|
| **Etcd Snapshot** | Daily 01:00 | Backs up etcd to MinIO/S3. Retains 7 days. |
| **Etcd Defrag** | Daily 02:30 | Rolling defrag of etcd members to reclaim space. |
| **Node Cleaner** | Daily 04:00 | Prunes unused Docker images & cleans `/tmp`. |
| **Pod Hygiene** | Hourly `:00` | Deletes Evicted/Stuck pods and Zombies. |
| **Cert Audit** | Hourly `:30` | Alerts if PKI certs expire in <30 days. |
| **GPU Report** | Hourly `:15` | Logs aggregation of Allocatable vs Capacity GPUs. |
| **Velero UI** | Always On | Web Interface for Backup management (Port 3000). |

**Key Feature**: `maintenance-scripts.yaml`. All logic is versioned in bash scripts, not hidden in binary images. Parameters are exposed via Helm values.

### 4.2 Reactive Management (Self-Healing)
*Located in: `cp-paas-iac-reference/charts/reactive-management`*

This suite acts as the cluster's immune system.

**Components**:
1.  **Node Problem Detector (NPD)**: Scans kernel logs (`/dev/kmsg`) and systemd.
2.  **Node Health Check (NHC)**: Operator that defines "Unhealthy" criteria.
3.  **Self Node Remediation (SNR)**: Operator that reboots nodes safely.

**Scenarios Covered**:
*   **KernelDeadlock**: "task blocked for more than 120 seconds".
*   **ReadonlyFilesystem**: "Remounting filesystem read-only".
*   **CorruptOverlay2**: Docker storage corruption.
*   **Kubelet/Runtime Flapping**: Service restarts > 5 times.
*   **OOM Killers**: "Out of memory: Kill process".

---

## 5. Prerequisites

### Host System
*   **OS**: Ubuntu 22.04 LTS (recommended) or CentOS Stream 9.
*   **CPU**: VT-x/AMD-v enabled (Virtualization).
*   **RAM**: Minimum 32GB (64GB recommended for full 3-cluster topology).
*   **Disk**: 200GB+ NVMe.

### Tools
*   `virsh`, `virt-install`, `qemu-kvm`
*   `kubectl`, `helm`
*   `jq`

---

## 6. Quick Start Guide

### Step 1: Provision VMs
Create the virtual machines on your bare-metal Linux host.
```bash
cd vm-provisioning
# 1. Setup Network (NAT/Bridge)
sudo ./00-setup-host-net.sh

# 2. Create VMs
sudo ./02-provision-all.sh
# Check status
virsh list --all
```

### Step 2: Bootstrap Clusters
Log into the VMs and install Kubernetes.
```bash
# Example for one node (repeat or use automation)
scp cluster-bootstrap/install-prereqs.sh ubuntu@<VM_IP>:~
ssh ubuntu@<VM_IP> "sudo ./install-prereqs.sh"

# On Master Node
ssh ubuntu@<MASTER_IP> "sudo ./manage-cluster.sh init"
# (Copy the join command and run on workers)
```

### Step 3: Deploy Management Suites
Once clusters are Ready, install the operations stack.
```bash
# 1. Add Helm Repos (if using remote, or use local chart)
cd cp-paas-iac-reference/charts/proactive-management

# 2. Install Proactive (with Velero)
helm upgrade --install proactive . -n proactive-maintenance --create-namespace

# 3. Install Reactive (Medik8s)
cd ../reactive-management
helm upgrade --install reactive . -n reactive-maintenance --create-namespace
```

---

## 7. Operational Manual

### Accessing Velero UI
The Velero UI runs in `proactive-maintenance` namespace on port 3000.
```bash
# Forward Port
kubectl port-forward svc/velero-ui -n proactive-maintenance 8090:3000

# Access
# URL: http://localhost:8090
# User: admin
# Pass: admin
```

### Triggering Manual Maintenance
Don't wait for the schedule! You can trigger any proactive job manually.
```bash
# Example: Run GPU Capacity Report NOW
kubectl create job --from=cronjob/hourly-gpu-capacity manual-gpu-check -n proactive-maintenance

# View Result
kubectl logs job/manual-gpu-check -n proactive-maintenance
```

### Simulating Node Failure
To test the Self-Healing capabilities safely:

**1. Simulate Kernel Deadlock:**
```bash
# On a worker node
echo "kernel: task blocked for more than 120 seconds" > /dev/kmsg
```
**Effect**:
1.  NPD detects log line -> Sets `KernelDeadlock=True`.
2.  NHC Operator sees condition -> Creates `NodeRemediation` CR.
3.  SNR Operator -> Cordons Node -> Drains Pods -> **Reboots Node**.

**2. Maintenance Mode (Prevent Reboot):**
If you need to perform work without triggering reboots:
```bash
kubectl label node <node-name> maintenance.mode=true
```

---

## 8. Troubleshooting

### Job Stuck in "ContainerCreating"
*   **Cause**: Missing ConfigMap or Secret.
*   **Fix**: Check `kubectl get cm -n proactive-maintenance`. Ensure `maintenance-scripts.yaml` was applied.

### Velero Backup Failed
*   **Cause**: MinIO not reachable.
*   **Fix**: Check `kubectl get pods -n proactive-maintenance`. Ensure `minio` pod is Running. Verify credentials in `velero-secret`.

### Node Not Rebooting
*   **Cause**: `minHealthy` budget prevented it.
*   **Fix**: Check NHC status. `kubectl describe nodehealthcheck`. If too many nodes are down, remediation pauses to save the cluster.
