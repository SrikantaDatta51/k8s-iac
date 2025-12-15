# Kubernetes IaC: Strategic Reference Architecture
## Release Management, SSOT, and Self-Healing at Scale

---

# Agenda: 3 Core Use Cases

1. **Release Management w/ SSOT**
   - Ending the "Manual Config" Era.
   - The "Uber Bundle" Strategy.

2. **The SSOT Reference Pipeline**
   - Helm Charts & GitOps Workflow.
   - Network Management Foundation.

3. **Preactive & Proactive Maintenance**
   - Automated Health & Self-Healing.
   - "Disconnecting" from legacy manual ops.

---

# Use Case 1: Release Management w/ SSOT

### The Problem: Legacy Operations (BCM Era)
*   **SSOT BCM State**: "Manual configs from all clusters."
    *   Configuration is hidden in scripts, wikis, or engineers' heads.
    *   High "Drift": Production does not match Staging.
    *   **Goal**: Disconnect K8s from legacy BCM (manual/external) management tools.

### The Solution: Git as the Single Source of Truth
*   **Philosophy**: "Git is God."
    *   If it's not in Git, it doesn't exist.
    *   If it exists in the cluster but not in Git, it is deleted.
*   **The Mechanism**:
    *   **Desired State**: Defined in the Repo.
    *   **Actual State**: Enforced by ArgoCD.
    *   **Result**: Immutable Infrastructure.

---

# Use Case 2: SSOT Reference Pipeline for Helm Charts

### The Architecture: "The Uber Bundle"
We do not manage 50 individual charts. We manage **1 Platform**.

1.  **Components** (`components/*`):
    *   Individual tools (Prometheus, Calico, GPU Operator).
    *   Versioned independently.
2.  **Uber Bundle** (`uber/*`):
    *   The "Meta-Chart". Contains **no templates**, only dependencies.
    *   Defines the "Platform Version" (e.g., `v1.2.0`).
3.  **Overlays** (`env/*`):
    *   Environment-specific values (Dev vs. Prod).
    *   **Zero Code Changes** allowed here. Only config.

### Network Management Foundation
To support this pipeline, we standardize the network layer:
*   **Host Networking**:
    *   Bridged KVM Networking (`br0`) allows VMs to look like physical hosts.
    *   Simplified ingress/egress without complex NAT.
*   **Container Networking**:
    *   **Calico CNI**: Provides Policy, Security, and Observability within the cluster.
    *   Ensures consistent behavior across Dev and Prod.

---

# Use Case 3: Preactive & Proactive Maintenance

### Moving Beyond "Break-Fix"
We replace "Pagers" with "Agents".

### 1. Proactive Maintenance ("The Janitor")
*   **Goal**: Prevent "Bit Rot" and degradation.
*   **Automated Tasks**:
    *   **Etcd Defrag**: Keeps API fast.
    *   **Log/Image Cleaning**: Prevents disk pressure.
    *   **Cert Auditing**: Alerts 30 days before expiration.
    *   **Utilization**: Logs GPU/Resource availability.

### 2. Preactive (Reactive) Maintenance ("The Healer")
*   **Goal**: Handle Hard Failures without Human Intervention.
*   **Mechanism**: **Node Problem Detector + Medik8s**.
*   **Use Cases**:
    *   **Kernel Deadlock**: Detects hung tasks > 120s -> **Reboot Node**.
    *   **Infiniband Failure**: Detects link down -> **Reset**.
    *   **OOM / Read-Only FS**: Immediate remediation.

---

# Summary: The Strategic Shift

| Feature | Legacy / BCM Approach | K8s IaC / SSOT Approach |
| :--- | :--- | :--- |
| **Config** | Manual / Scripted | GitOps (ArgoCD) |
| **Network** | Opaque / Host-based | Bridged Host + Calico CNI |
| **Release** | Ad-hoc Updates | Uber Bundle Pipeline |
| **Maintenance** | Reactive (Pager 3am) | Proactive + Self-Healing |

**Final Goal**: A Disconnected, Autonomous Kubernetes Platform.
