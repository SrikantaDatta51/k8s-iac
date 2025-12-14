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
5. [Release Management (SSOT)](#5-release-management-ssot)
    - [The Uber Chart Strategy](#51-the-uber-chart-strategy)
    - [Developer Workflow](#52-developer-workflow)
    - [Environment Promotion](#53-environment-promotion)
6. [Prerequisites](#6-prerequisites)
7. [Quick Start Guide](#7-quick-start-guide)
8. [Operational Manual](#8-operational-manual)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Executive Summary
This project provides a production-grade, on-premise Kubernetes infrastructure solution using **KVM** for virtualization and **GitOps** for configuration management. Unlike standard installers, this repo includes a sophisticated **Day-2 Operations Suite** pre-integrated.

**Key Capabilities**:
*   **Infrastructure**: Scripts to provision 9 VMs across 3 Clusters (Command, GPU, CPU) via `virsh/virt-install`.
*   **Proactive Maintenance**: A `proactive-maintenance` namespace running 10+ scheduled CronJobs to prevent rot (Etcd defrag, Cert audits, Log cleaning).
*   **Reactive Self-Healing**: A `reactive-maintenance` namespace using Medik8s (NHC/SNR) and Node Problem Detector to automatically reboot nodes upon detecting deeply embedded failures (Kernel deadlocks, Read-only filesystems).
*   **SSOT Release**: A "One Chart to Rule Them All" release strategy ensuring identical platform versions across all clusters.

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
        ChartMuseum[Helm Registry]
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
    
    Argo -->|Deploy Uber Chart| Command Cluster
    Argo -->|Deploy Uber Chart| GPU Cluster
    Argo -->|Deploy Uber Chart| CPU Cluster
```

### 2.2 GitOps Flow
1.  **Commit**: Changes are pushed to `main`.
2.  **CI Build**: `ci/build-and-publish-uber.sh` detects changes, bumps version, and pushes to **ChartMuseum**.
3.  **ArgoCD**: Detects new version or config change in `env/overlays/`.
4.  **Sync**: Applies the updated **Uber Chart** to target clusters.

---

## 3. Repository Structure

```tree
k8s-iac/
├── cluster-configs/         # Manifests & Charts for Day-2 Ops
├── cp-paas-iac-reference/   # REFERENCE ARCHITECTURE (The Core Logic)
│   ├── charts/              # Custom Helm Charts (Proactive/Reactive)
│   ├── components/          # Reusable component charts (CNI, GPU, Tenants)
│   ├── uber/                # THE SSOT: Aggregates everything above
│   │   └── cluster-addons-uber/  # The "One Chart"
│   └── env/                 # Environment Configuration (The Values)
│       └── overlays/
│           ├── dev/         # Values for Dev Cluster
│           ├── staging/     # Values for Staging
│           └── prod/        # Values for Prod
├── docs/                    # Architecture Designs
└── README.md                # This file
```

---

## 4. Core Features
*(See previous sections for details on Proactive/Reactive Management suites)*

---

## 5. Release Management (SSOT)

### 5.1 The Uber Chart Strategy
We strictly adhere to a **Single Source of Truth (SSOT)** model. We do not deploy individual components (like CNI, GPU driver, or Maintenance scripts) separately.
Instead, we package EVERYTHING into a single Helm Chart: **`cluster-addons-uber`**.

*   **Benefits**: Atomic upgrades. You verify `v0.2.0` in Dev, then promote exactly `v0.2.0` to Prod. No "version drift" where Prod has old CNI but new GPU driver.
*   **Registry**: ChartMuseum (Internal).
    *   URL: `http://chartmuseum.chartmuseum.svc.cluster.local:8080`

### 5.2 Developer Workflow

#### "I want to add a new tool (e.g., Keda)"
1.  **Create Chart**: Add the code in `cp-paas-iac-reference/components/addons/keda`.
2.  **Register**: Add it as a dependency in `cp-paas-iac-reference/uber/cluster-addons-uber/Chart.yaml`.
3.  **Build**: Run CI (or `build-and-publish-uber.sh`).
    *   Result: `cluster-addons-uber:0.3.0` is published.

#### "I want to update Proactive Scripts"
1.  **Edit**: Modify `charts/proactive-management/templates/maintenance-scripts.yaml`.
2.  **Bump**: Increment version in `charts/proactive-management/Chart.yaml`.
3.  **Commit**: Push to `main`.
    *   Result: CI rebuilds the Uber chart with the new Proactive sub-chart.

### 5.3 Environment Promotion
To promote changes from Dev -> Prod, you do **NOT** change code. You change **Values** in the Overlays.

*   **Dev**: `cp-paas-iac-reference/env/overlays/dev/argocd-app.yaml` points to `targetRevision: 0.2.0`.
*   **Prod**: `cp-paas-iac-reference/env/overlays/prod/argocd-app.yaml` points to `targetRevision: 0.1.0`.

**Promotion**:
1.  Verify v0.2.0 in Dev.
2.  Edit `env/overlays/prod/argocd-app.yaml` -> Set `0.2.0`.
3.  Merge PR. ArgoCD syncs Prod.

---

## 6. Prerequisites
*(Standard hardware requirements...)*

## 7. Quick Start Guide
*(Standard VM and Bootstrap steps...)*

## 8. Operational Manual
*(Velero UI and Troubleshooting guides...)*

## 9. Troubleshooting
*(Standard FAQs...)*
