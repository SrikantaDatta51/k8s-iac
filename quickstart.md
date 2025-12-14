# KVM Kubernetes Quickstart & Validation Guide

This guide provides a copy-paste workflow to get your entire KVM-based Kubernetes infrastructure up and running, validated, and ready for use.

![Architecture](/home/user/.gemini/antigravity/brain/8ca12fc2-fb02-4cb8-bb61-29e961d57eaa/kvm_k8s_architecture_diagram_1765067962574.png)

## 0. Prerequisites
Run this on your Linux Host (Precision-5820).

```bash
# 1. Install KVM/Libvirt & Utils
sudo apt update
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virtinst genisoimage netcat-openbsd

# 2. Add user to libvirt group (requires logout/login or new shell)
sudo usermod -aG libvirt $USER
newgrp libvirt
```

## 1. Infrastructure (VMs & Network)
Navigate to `vm-provisioning` and run the script.

```bash
cd ~/k8s-iac/vm-provisioning
sudo ./02-provision-all.sh
```

### ✅ Validation
```bash
# Check VMs are running and have IPs
sudo ./03-check-status.sh

# Expected Result:
# cmd-master        running         192.168.100.10
# gpu-master        running         192.168.100.20
# cpu-master        running         192.168.100.30
```

## 2. Cluster Bootstrapping
Navigate to `cluster-bootstrap` to initialize K8s on all nodes.

```bash
cd ~/k8s-iac/cluster-bootstrap
./01-bootstrap-clusters.sh
```

### ✅ Validation
```bash
# Check Command Cluster Nodes
kubectl --kubeconfig ~/.kube/config-command-cluster get nodes
# Check GPU Cluster Nodes
kubectl --kubeconfig ~/.kube/config-gpu-cluster get nodes
# Check CPU Cluster Nodes
kubectl --kubeconfig ~/.kube/config-cpu-cluster get nodes
```

## 3. Tool Installation (ArgoCD, Karmada, Calico)
Install the management plane tools.

```bash
cd ~/k8s-iac/cluster-configs
./install-tools.sh
```

### ✅ Validation
```bash
# Check Pods on Command Cluster (ArgoCD, Karmada, Calico)
kubectl --kubeconfig ~/.kube/config-command-cluster get pods -A

# Check Karmada Clusters
kubectl --kubeconfig /etc/karmada/karmada-apiserver.config get clusters
# Should see: gpu-cluster, cpu-cluster (Ready)
```

## 4. Deploy Local GitHub (Gitea) & Sample App
Deploy Gitea to the Command Cluster to act as your local Git server.

```bash
# Deploy Gitea
kubectl --kubeconfig ~/.kube/config-command-cluster apply -f ~/k8s-iac/cluster-configs/command-cluster/gitea.yaml

# Push Sample App to GitOps Repo (Manual Step for now, or use provided script)
cd ~/k8s-iac/gitops-repo
# ... (Initialize and push to Gitea/GitHub)
```

## 5. Access & Passwords

### ArgoCD
*   **URL**: `https://192.168.100.10:<NodePort>`
*   **Username**: `admin`
*   **Get Password**:
    ```bash
    # Ensure you use the correct kubeconfig path
    kubectl --kubeconfig ~/.kube/config-command-cluster -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
    ```

### Karmada Dashboard
*   **URL**: `http://192.168.100.10:<NodePort>`
*   **To find NodePort**:
    ```bash
    kubectl --kubeconfig ~/.kube/config-command-cluster -n karmada-system get svc karmada-dashboard
    ```

### Gitea (Local Git)
*   **URL**: `http://192.168.100.10:30300`
*   **Setup**: Visit URL to finish install (use SQLite for simplicity).

### Calico (Whisker/Viz)
> [!NOTE]
> **"Whisker" UI** is often confused with Tigera's commercial offerings or experimental projects. The open-source Calico installed here (v3.28+) does not bundle a standalone UI.
> We validate policies using the CLI below.

**Demo Policy (Deny/Allow):**
A `NetworkPolicy` ([netpol.yaml](file:///home/user/.gemini/antigravity/scratch/srtumkur/2025/k8s-iac/gitops-repo/apps/base/nginx/netpol.yaml)) is included in the sample app `apps/base/nginx`.
*   **Deny**: Traffic from pods without `access: granted` label.
*   **Allow**: Traffic from pods with `access: granted`.

### Karmada Propagation
The [propagation.yaml](file:///home/user/.gemini/antigravity/scratch/srtumkur/2025/k8s-iac/gitops-repo/apps/base/nginx/propagation.yaml) in the sample app directs the `nginx` deployment to both `gpu-cluster` (weight 1) and `cpu-cluster` (weight 1).
*   Check propagation:
    ```bash
    # Use the Karmada Apiserver config
    karmadactl --kubeconfig /etc/karmada/karmada-apiserver.config get deployment
    ```

## 6. Hello World GitOps Workflow
1.  **Repo**: Push `gitops-repo` to Gitea (http://192.168.100.10:30300).
2.  **ArgoCD**: Create App pointing to Gitea repo path `apps/base/nginx`.
3.  **Sync**: ArgoCD applies manifest to Karmada (on Command Cluster).
4.  **Propagate**: Karmada detects `PropagationPolicy` and schedules Pods to GPU/CPU clusters.
5.  **Verify**:
    ```bash
    kubectl --kubeconfig ~/.kube/config-gpu-cluster get pods
    kubectl --kubeconfig ~/.kube/config-cpu-cluster get pods
    ```
